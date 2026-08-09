// ============================================================================
// generateTasks — Bestemshe custom task extractor (schema v3)
//
// Samples random positions from a solved (K1,K2) layer and keeps only the ones
// that satisfy a task goal plus a set of position filters.
//
// Task types:
//   mate            forced win in EXACTLY N of our moves (DB-backed, DTM 2N-1)
//   atsyrau         force the opponent's row empty in <= N of our moves
//   capture_total   our kazan gains >= K stones in total within <= N moves
//   capture_single  one single move of ours captures >= K stones within <= N
//   loop            position is a DRAW; optimal play repeats a FEN within <= N
//
// Positions are mover-relative: board[0..4] / K_self = "white" (side to move),
// board[5..9] / K_opp = "black" (opponent).
// ============================================================================
#include "BestemsheCore.h"
#include "StateIndex.h"
#include "Inference.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <random>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using namespace Bestemshe;
namespace fs = std::filesystem;

static InferenceEngine g_db;

// ---------------------------------------------------------------------------
// Task configuration
// ---------------------------------------------------------------------------
enum class TaskType { Mate, Atsyrau, CaptureTotal, CaptureSingle, Loop };

static const char* TaskTypeName(TaskType t) {
    switch (t) {
        case TaskType::Mate:          return "mate";
        case TaskType::Atsyrau:       return "atsyrau";
        case TaskType::CaptureTotal:  return "capture_total";
        case TaskType::CaptureSingle: return "capture_single";
        case TaskType::Loop:          return "loop";
    }
    return "?";
}

struct Config {
    TaskType type = TaskType::Mate;
    int moves = 1;              // N
    int minMoves = 1;           // reject goals reachable in fewer than this many moves
    int captureK = 0;           // K (capture_* only)
    long long branching = -1;   // b: max total leaf variations; -1 = unlimited
    bool allowMultiple = false; // keep every qualifying root move
};
static Config g_cfg;

// ---------------------------------------------------------------------------
// Move generation (shared with generateVictory)
// ---------------------------------------------------------------------------
struct MoveInfo {
    int pit;          // canonical pit 0..4 of the side to move
    int landing;      // pit where the last stone lands (0..9, mover's frame)
    bool capture;
    bool empties;     // move leaves the opponent's side empty
    bool terminal;    // immediate win: empties opponent or kazan reaches 26+
    int gain;         // stones this move added to the mover's kazan
    State flipped;    // resulting state from the opponent's perspective
};

// Two-digit notation "<from><to>": from = mover's cell 1-5; to = cell 1-5 in
// the perspective of the side where the last stone lands.
static std::string Notation(const MoveInfo& m) {
    int to = (m.landing <= 4) ? m.landing + 1 : m.landing - 4;
    std::string s = std::to_string(m.pit + 1) + std::to_string(to);
    if (m.capture) s += "+";
    if (m.terminal) s += "#";
    return s;
}

static std::vector<MoveInfo> LegalMoves(const State& s) {
    std::vector<MoveInfo> out;
    for (int i = 0; i < 5; ++i) {
        if (s.board[i] == 0) continue;
        MoveInfo m;
        m.pit = i;
        int pieces = s.board[i];
        m.landing = (pieces == 1) ? (i + 1) % 10 : (i + pieces - 1) % 10;
        m.capture = ExecuteMoveAndFlip(s, i, m.flipped, m.empties);
        // The frame flips, so the mover's kazan is K_opp after the move.
        m.gain = static_cast<int>(m.flipped.K_opp) - static_cast<int>(s.K_self);
        m.terminal = m.empties || m.flipped.K_opp >= 26;
        out.push_back(m);
    }
    return out;
}

// A non-terminal move wins iff the resulting position is a LOSS for the
// opponent (side to move in `flipped`).
static bool MoveWins(const MoveInfo& m) {
    if (m.terminal) return true;
    uint64_t idx = StateIndex::IndexState(m.flipped);
    return g_db.query_state(m.flipped.M, m.flipped.K_opp, idx) == GameValue::LOSS;
}

static std::string FenOf(const State& s) {
    std::ostringstream f;
    for (int i = 0; i < 5; ++i) f << (i ? "," : "") << (int)s.board[i];
    f << "/";
    for (int i = 5; i < 10; ++i) f << (i > 5 ? "," : "") << (int)s.board[i];
    f << " " << (int)s.K_self << "," << (int)s.K_opp << " w " << (int)s.M;
    return f.str();
}

// ---------------------------------------------------------------------------
// AND/OR goal search (atsyrau / capture_total / capture_single)
// ---------------------------------------------------------------------------
// Returns true when the move itself completes the goal.
static bool GoalMet(const MoveInfo& m, int accumulatedGain) {
    switch (g_cfg.type) {
        case TaskType::Atsyrau:
            return m.empties;
        case TaskType::CaptureTotal:
            return accumulatedGain + m.gain >= g_cfg.captureK;
        case TaskType::CaptureSingle:
            return m.gain >= g_cfg.captureK;
        default:
            return false;
    }
}

struct Node {
    bool ok = false;
    long long leaves = 0;   // number of complete variations below (and incl.) this node
    std::string moveStr;    // our move at this node
    std::string varJson;    // opponent replies below it; empty when the move is a leaf
};

// Renders a node as either "54+#" or {"move": "54+", "variations": {...}}.
static std::string RenderNode(const std::string& moveStr, const std::string& varJson) {
    if (varJson.empty()) return "\"" + moveStr + "\"";
    return "{\"move\": \"" + moveStr + "\", \"variations\": " + varJson + "}";
}

static Node SolveOurGoal(const State& s, int depth, int gain);

// Opponent to move: the goal must hold after EVERY legal reply.
static Node SolveOppGoal(const State& s, int depth, int gain) {
    Node r;
    auto replies = LegalMoves(s);
    if (replies.empty()) return r;   // opponent has no move; goal not forced here

    std::ostringstream json;
    json << "{";
    long long leaves = 0;
    bool first = true;
    for (const auto& rep : replies) {
        // A reply that ends the game (empties our row / reaches kazan 26) means
        // we never get to move again, so the goal cannot be forced.
        if (rep.terminal) return Node{};
        Node child = SolveOurGoal(rep.flipped, depth, gain);
        if (!child.ok) return Node{};
        leaves += child.leaves;
        if (g_cfg.branching >= 0 && leaves > g_cfg.branching) return Node{};
        if (!first) json << ", ";
        first = false;
        json << "\"" << Notation(rep) << "\": " << RenderNode(child.moveStr, child.varJson);
    }
    json << "}";
    r.ok = true;
    r.leaves = leaves;
    r.varJson = json.str();
    return r;
}

// Our side to move. `depth` = how many of our moves remain.
// Collects every qualifying move; the caller enforces the uniqueness rule.
static std::vector<std::pair<MoveInfo, Node>> QualifyingMoves(const State& s, int depth,
                                                              int gain) {
    std::vector<std::pair<MoveInfo, Node>> out;
    if (depth <= 0) return out;
    for (const auto& m : LegalMoves(s)) {
        if (GoalMet(m, gain)) {
            Node leaf;
            leaf.ok = true;
            leaf.leaves = 1;
            leaf.moveStr = Notation(m);
            out.emplace_back(m, leaf);
            continue;
        }
        // A move that ends the game without meeting the goal is a dead end.
        if (m.terminal) continue;
        if (depth == 1) continue;
        Node sub = SolveOppGoal(m.flipped, depth - 1, gain + m.gain);
        if (!sub.ok) continue;
        Node n;
        n.ok = true;
        n.leaves = sub.leaves;
        n.moveStr = Notation(m);
        n.varJson = sub.varJson;
        out.emplace_back(m, n);
    }
    return out;
}

static Node SolveOurGoal(const State& s, int depth, int gain) {
    auto q = QualifyingMoves(s, depth, gain);
    if (q.empty()) return Node{};
    if (!g_cfg.allowMultiple && q.size() > 1) return Node{};
    // Deeper nodes always take the first qualifying move (cheapest tree).
    return q.front().second;
}

// ---------------------------------------------------------------------------
// mate: DB-backed, exactly N moves (DTM 2N-1) — same rule as generateVictory
// ---------------------------------------------------------------------------
struct MateNode {
    bool ok = false;
    int dtm = 0;
    long long leaves = 0;
    std::string moveStr;
    std::string varJson;
};

static MateNode SolveOurMate(const State& s, int budget);

static MateNode SolveOppMate(const State& s, int budget) {
    MateNode r;
    auto replies = LegalMoves(s);
    if (replies.empty()) return r;

    std::ostringstream json;
    json << "{";
    long long leaves = 0;
    int maxChild = 0;
    bool first = true;
    for (const auto& rep : replies) {
        if (rep.terminal) return MateNode{};  // s is a LOSS: no reply may be terminal
        MateNode child = SolveOurMate(rep.flipped, budget - 1);
        if (!child.ok) return MateNode{};
        leaves += child.leaves;
        if (g_cfg.branching >= 0 && leaves > g_cfg.branching) return MateNode{};
        maxChild = std::max(maxChild, child.dtm);
        if (!first) json << ", ";
        first = false;
        json << "\"" << Notation(rep) << "\": " << RenderNode(child.moveStr, child.varJson);
    }
    json << "}";
    r.ok = true;
    r.dtm = 1 + maxChild;
    r.leaves = leaves;
    r.varJson = json.str();
    return r;
}

// Collects every winning move at this node.
static std::vector<std::pair<MoveInfo, MateNode>> WinningMoves(const State& s, int budget) {
    std::vector<std::pair<MoveInfo, MateNode>> out;
    for (const auto& m : LegalMoves(s)) {
        if (!MoveWins(m)) continue;
        MateNode n;
        if (m.terminal) {
            n.ok = true;
            n.dtm = 1;
            n.leaves = 1;
            n.moveStr = Notation(m);
            out.emplace_back(m, n);
            continue;
        }
        if (budget < 3) continue;
        MateNode opp = SolveOppMate(m.flipped, budget - 1);
        if (!opp.ok) continue;
        n.ok = true;
        n.dtm = 1 + opp.dtm;
        n.leaves = opp.leaves;
        n.moveStr = Notation(m);
        n.varJson = opp.varJson;
        out.emplace_back(m, n);
    }
    return out;
}

static MateNode SolveOurMate(const State& s, int budget) {
    auto w = WinningMoves(s, budget);
    if (w.empty()) return MateNode{};
    if (w.size() > 1) return MateNode{};  // narrow path is mandatory inside the tree
    return w.front().second;
}

// ---------------------------------------------------------------------------
// loop: DRAW position, walk the principal draw line until a FEN repeats
// ---------------------------------------------------------------------------
static bool IsDraw(const State& s) {
    return g_db.query_state(s.M, s.K_opp, StateIndex::IndexState(s)) == GameValue::DRAW;
}

// A move holds the draw iff the resulting position is a DRAW for the opponent
// (neither side can force a win from there).
static bool HoldsDraw(const MoveInfo& m) {
    if (m.terminal) return false;
    return g_db.query_state(m.flipped.M, m.flipped.K_opp,
                            StateIndex::IndexState(m.flipped)) == GameValue::DRAW;
}

static uint64_t g_drawsSeen = 0;

struct LoopResult {
    bool ok = false;
    int loopAt = -1;              // index in `line` where the FEN repeated
    std::vector<std::string> line;
};

// FENs are mover-relative, so a position key must also record whose turn it
// is: the same board with the other side to move is a different position.
static std::string LoopKey(const State& st, int ply) {
    return FenOf(st) + (ply % 2 ? "|o" : "|u");
}

// Only draw-holding, capture-free moves can be part of a loop: a capture raises
// M permanently, so the position could never recur.
static std::vector<MoveInfo> LoopMoves(const State& s) {
    std::vector<MoveInfo> out;
    for (const auto& m : LegalMoves(s))
        if (m.gain == 0 && HoldsDraw(m)) out.push_back(m);
    return out;
}

// Depth-first search with backtracking for a repetition. `budget` counts plies.
// `path` is the move list so far, `seen` the positions on the current path.
static bool LoopDFS(const State& cur, int ply, int budget,
                    std::set<std::string>& seen,
                    std::vector<std::string>& path,
                    int& loopAt, uint64_t& nodes) {
    if (budget <= 0) return false;
    if (++nodes > 200000) return false;   // safety valve on pathological branches

    auto moves = LoopMoves(cur);
    if (moves.empty()) return false;
    // The puzzle is finding the ONE right first move, so uniqueness is required
    // only at the root; deeper in the line either side may have several
    // draw-holding options.
    if (ply == 0 && !g_cfg.allowMultiple && moves.size() > 1) return false;

    for (const auto& mv : moves) {
        State nxt = mv.flipped;
        std::string k = LoopKey(nxt, ply + 1);
        path.push_back(Notation(mv));
        if (seen.count(k)) {                  // position repeated -> loop closed
            loopAt = static_cast<int>(path.size()) - 1;
            return true;
        }
        seen.insert(k);
        if (LoopDFS(nxt, ply + 1, budget - 1, seen, path, loopAt, nodes)) return true;
        seen.erase(k);
        path.pop_back();
    }
    return false;
}

// Optimal (draw-preserving, capture-free) play for both sides until a position
// repeats. `N` bounds OUR moves, so the search gets 2N plies.
static LoopResult SolveLoop(const State& start, int N) {
    LoopResult r;
    if (!IsDraw(start)) return r;

    std::set<std::string> seen;
    seen.insert(LoopKey(start, 0));
    uint64_t nodes = 0;
    r.ok = LoopDFS(start, 0, 2 * N, seen, r.line, r.loopAt, nodes);
    if (!r.ok) r.line.clear();
    return r;
}

// ---------------------------------------------------------------------------
// Position filters (mover-relative frame)
// ---------------------------------------------------------------------------
struct Filters {
    int minKazanWhite = -1, maxKazanWhite = -1;
    int minKazanBlack = -1, maxKazanBlack = -1;
    int minStonesWhite = -1, maxStonesWhite = -1;
    int minStonesBlack = -1, maxStonesBlack = -1;
    int minEmptyWhite = -1, maxEmptyWhite = -1;
    int minEmptyBlack = -1, maxEmptyBlack = -1;
};
static Filters g_f;

static bool InRange(int v, int lo, int hi) {
    if (lo >= 0 && v < lo) return false;
    if (hi >= 0 && v > hi) return false;
    return true;
}

struct Counts { int stonesW, stonesB, emptyW, emptyB; };

static Counts CountBoard(const State& s) {
    Counts c{0, 0, 0, 0};
    for (int i = 0; i < 5; ++i) {
        c.stonesW += s.board[i];
        if (s.board[i] == 0) ++c.emptyW;
        c.stonesB += s.board[i + 5];
        if (s.board[i + 5] == 0) ++c.emptyB;
    }
    return c;
}

static bool PassesBoardFilters(const Counts& c) {
    return InRange(c.stonesW, g_f.minStonesWhite, g_f.maxStonesWhite) &&
           InRange(c.stonesB, g_f.minStonesBlack, g_f.maxStonesBlack) &&
           InRange(c.emptyW,  g_f.minEmptyWhite,  g_f.maxEmptyWhite) &&
           InRange(c.emptyB,  g_f.minEmptyBlack,  g_f.maxEmptyBlack);
}

// ---------------------------------------------------------------------------
static void PrintUsage() {
    std::cout <<
        "Usage:\n"
        "  ./generateTasks --layer <K1>_<K2> --taskType <type> --moves <N> [options]\n\n"
        "  --taskType       mate | atsyrau | capture_total | capture_single | loop\n"
        "  --moves N        mate: exactly N of our moves; others: at most N.\n"
        "  --minMoves m     Reject goals already forced in fewer than m moves.\n"
        "                   Set --minMoves N --moves N for 'exactly N'.\n"
        "  --captureK K     capture_total / capture_single threshold.\n"
        "  --branching b    Max TOTAL number of variations (leaf paths) in the solution.\n"
        "  --allowMultiple  Accept positions with several solutions (all are written).\n"
        "  Filters (mover-relative; omit for no constraint):\n"
        "    --minKazanWhite/--maxKazanWhite   --minKazanBlack/--maxKazanBlack\n"
        "    --minStonesWhite/--maxStonesWhite --minStonesBlack/--maxStonesBlack\n"
        "    --minEmptyWhite/--maxEmptyWhite   --minEmptyBlack/--maxEmptyBlack\n"
        "  --count <n>      --seed <s>  --maxAttempts <n>  --jsonOut <file>\n";
}

int main(int argc, char* argv[]) {
    StateIndex::InitCombinatorics();

    std::string layerArg, jsonOut, typeArg = "mate";
    int count = 50;
    uint64_t seed = std::random_device{}();
    uint64_t maxAttempts = 2000000;

    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        auto next = [&](const char* name) -> std::string {
            if (i + 1 >= argc) {
                std::cerr << "[ERROR] Missing value for " << name << "\n";
                exit(1);
            }
            return argv[++i];
        };
        auto nextInt = [&](const char* name) { return std::stoi(next(name)); };

        if      (a == "--layer")          layerArg = next("--layer");
        else if (a == "--taskType")       typeArg = next("--taskType");
        else if (a == "--moves")          g_cfg.moves = nextInt("--moves");
        else if (a == "--minMoves")       g_cfg.minMoves = nextInt("--minMoves");
        else if (a == "--captureK")       g_cfg.captureK = nextInt("--captureK");
        else if (a == "--branching")      g_cfg.branching = std::stoll(next("--branching"));
        else if (a == "--allowMultiple")  g_cfg.allowMultiple = true;
        else if (a == "--minKazanWhite")  g_f.minKazanWhite = nextInt(a.c_str());
        else if (a == "--maxKazanWhite")  g_f.maxKazanWhite = nextInt(a.c_str());
        else if (a == "--minKazanBlack")  g_f.minKazanBlack = nextInt(a.c_str());
        else if (a == "--maxKazanBlack")  g_f.maxKazanBlack = nextInt(a.c_str());
        else if (a == "--minStonesWhite") g_f.minStonesWhite = nextInt(a.c_str());
        else if (a == "--maxStonesWhite") g_f.maxStonesWhite = nextInt(a.c_str());
        else if (a == "--minStonesBlack") g_f.minStonesBlack = nextInt(a.c_str());
        else if (a == "--maxStonesBlack") g_f.maxStonesBlack = nextInt(a.c_str());
        else if (a == "--minEmptyWhite")  g_f.minEmptyWhite = nextInt(a.c_str());
        else if (a == "--maxEmptyWhite")  g_f.maxEmptyWhite = nextInt(a.c_str());
        else if (a == "--minEmptyBlack")  g_f.minEmptyBlack = nextInt(a.c_str());
        else if (a == "--maxEmptyBlack")  g_f.maxEmptyBlack = nextInt(a.c_str());
        else if (a == "--count")          count = nextInt("--count");
        else if (a == "--seed")           seed = std::stoull(next("--seed"));
        else if (a == "--maxAttempts")    maxAttempts = std::stoull(next("--maxAttempts"));
        else if (a == "--jsonOut")        jsonOut = next("--jsonOut");
        else { PrintUsage(); return 1; }
    }

    if      (typeArg == "mate")           g_cfg.type = TaskType::Mate;
    else if (typeArg == "atsyrau")        g_cfg.type = TaskType::Atsyrau;
    else if (typeArg == "capture_total")  g_cfg.type = TaskType::CaptureTotal;
    else if (typeArg == "capture_single") g_cfg.type = TaskType::CaptureSingle;
    else if (typeArg == "loop")           g_cfg.type = TaskType::Loop;
    else { std::cerr << "[ERROR] Unknown --taskType '" << typeArg << "'\n"; return 1; }

    if (layerArg.empty() || g_cfg.moves < 1) { PrintUsage(); return 1; }
    if ((g_cfg.type == TaskType::CaptureTotal || g_cfg.type == TaskType::CaptureSingle) &&
        g_cfg.captureK < 1) {
        std::cerr << "[ERROR] --captureK is required for " << typeArg << "\n";
        return 1;
    }

    // Parse K1_K2 out of "2_8" or "layers/compressed/layer_2_8_win.bin"
    std::string stem = fs::path(layerArg).filename().string();
    if (stem.rfind("layer_", 0) == 0) stem = stem.substr(6);
    for (auto suffix : {"_win.bin", "_draw.bin", "_win.raw", "_draw.raw", ".bin", ".raw"}) {
        size_t p = stem.rfind(suffix);
        if (p != std::string::npos && p + std::string(suffix).size() == stem.size())
            stem = stem.substr(0, p);
    }
    int K1, K2;
    {
        size_t us = stem.find('_');
        if (us == std::string::npos) {
            std::cerr << "[ERROR] Cannot parse layer '" << layerArg << "'. Expected K1_K2.\n";
            return 1;
        }
        K1 = std::stoi(stem.substr(0, us));
        K2 = std::stoi(stem.substr(us + 1));
    }

    uint8_t M = static_cast<uint8_t>(K1 + K2);
    if (K1 < StateIndex::GetMinK(M) || ((K1 - StateIndex::GetMinK(M)) % 2) != 0) {
        std::cerr << "[ERROR] Invalid kazan pair (" << K1 << "," << K2 << ").\n";
        return 1;
    }
    {
        std::string base = "layers/compressed/layer_" + std::to_string(K1) + "_" +
                           std::to_string(K2) + "_win.bin";
        std::string raw = "layers/layer_" + std::to_string(K1) + "_" +
                          std::to_string(K2) + "_win.raw";
        if (!fs::exists(base) && !fs::exists(raw)) {
            std::cerr << "[ERROR] Layer files for (" << K1 << "," << K2
                      << ") not found under layers/. Run from the project root.\n";
            return 1;
        }
    }

    // Kazan filters are layer-level: the whole file either matches or it doesn't.
    if (!InRange(K1, g_f.minKazanWhite, g_f.maxKazanWhite) ||
        !InRange(K2, g_f.minKazanBlack, g_f.maxKazanBlack)) {
        std::cout << "[SKIP] Layer (" << K1 << "," << K2 << ") fails the kazan filters.\n";
        if (!jsonOut.empty()) { std::ofstream out(jsonOut, std::ios::trunc); out << "[]\n"; }
        return 3;
    }

    const std::string layerName = std::to_string(K1) + "_" + std::to_string(K2);
    const int targetDtm = 2 * g_cfg.moves - 1;

    int R = 50 - M;
    uint64_t bCount = StateIndex::nCr(R + 9, 9);
    uint64_t iK = (uint64_t)(K1 - StateIndex::GetMinK(M)) / 2;

    std::cout << "[INFO] Layer (" << K1 << "," << K2 << "), M=" << (int)M
              << ", boards=" << bCount << ", type=" << TaskTypeName(g_cfg.type)
              << ", N=" << g_cfg.moves << ", K=" << g_cfg.captureK
              << ", branching<=" << g_cfg.branching << ", seed=" << seed << "\n";

    std::mt19937_64 rng(seed);
    std::uniform_int_distribution<uint64_t> dist(0, bCount - 1);
    std::set<uint64_t> seen;
    std::vector<std::string> entries;

    int accepted = 0;
    uint64_t attempts = 0;
    for (; attempts < maxAttempts && accepted < count; ++attempts) {
        uint64_t iB = dist(rng);
        if (!seen.insert(iB).second) continue;

        State s = StateIndex::UnindexState(iK * bCount + iB, M);

        bool hasMove = false;
        for (int i = 0; i < 5; ++i) if (s.board[i]) { hasMove = true; break; }
        if (!hasMove) continue;

        Counts cnt = CountBoard(s);
        // The opponent's row already being empty means the game is over: an
        // atsyrau has happened before the puzzle starts.
        if (cnt.stonesB == 0) continue;
        if (!PassesBoardFilters(cnt)) continue;

        std::string solutionsJson;
        long long leaves = 0;
        int depthUsed = 0;

        if (g_cfg.type == TaskType::Loop) {
            if (IsDraw(s)) ++g_drawsSeen;
            LoopResult lr = SolveLoop(s, g_cfg.moves);
            if (!lr.ok) continue;
            std::ostringstream sj;
            sj << "[{\"line\": [";
            for (size_t k = 0; k < lr.line.size(); ++k)
                sj << (k ? ", " : "") << "\"" << lr.line[k] << "\"";
            sj << "], \"loop_at\": " << lr.loopAt << "}]";
            solutionsJson = sj.str();
            leaves = 1;
            depthUsed = (lr.loopAt + 2) / 2;

        } else if (g_cfg.type == TaskType::Mate) {
            if (g_db.query_state(M, (uint8_t)K2, iB) != GameValue::WIN) continue;
            // Count winners independently: WinningMoves drops those whose
            // subtree fails the narrow-path rule, and such a move still counts
            // as an alternative solution for the solver.
            size_t rawWinners = 0;
            for (const auto& m : LegalMoves(s)) if (MoveWins(m)) ++rawWinners;
            auto w = WinningMoves(s, targetDtm);
            std::vector<std::pair<MoveInfo, MateNode>> good;
            for (auto& pr : w) if (pr.second.dtm == targetDtm) good.push_back(pr);
            // Any winning move that mates faster, or one we couldn't resolve,
            // breaks the "exactly N against best defense" rule.
            if (good.empty() || good.size() != rawWinners) continue;
            if (!g_cfg.allowMultiple && good.size() > 1) continue;
            std::ostringstream sj;
            sj << "[";
            for (size_t k = 0; k < good.size(); ++k) {
                if (k) sj << ", ";
                sj << "{\"first_move\": \"" << good[k].second.moveStr << "\"";
                if (!good[k].second.varJson.empty())
                    sj << ", \"variations\": " << good[k].second.varJson;
                sj << "}";
                leaves = std::max(leaves, good[k].second.leaves);
            }
            sj << "]";
            if (g_cfg.branching >= 0 && leaves > g_cfg.branching) continue;
            solutionsJson = sj.str();
            depthUsed = g_cfg.moves;

        } else {
            // Depth floor: reject if the goal is already forced in fewer moves.
            // Probed with the uniqueness rule relaxed, so we measure raw
            // achievability rather than "achievable by a unique move".
            if (g_cfg.minMoves > 1) {
                bool saved = g_cfg.allowMultiple;
                g_cfg.allowMultiple = true;
                bool tooFast = !QualifyingMoves(s, g_cfg.minMoves - 1, 0).empty();
                g_cfg.allowMultiple = saved;
                if (tooFast) continue;
            }
            auto q = QualifyingMoves(s, g_cfg.moves, 0);
            if (q.empty()) continue;
            if (!g_cfg.allowMultiple && q.size() > 1) continue;
            std::ostringstream sj;
            sj << "[";
            for (size_t k = 0; k < q.size(); ++k) {
                if (k) sj << ", ";
                sj << "{\"first_move\": \"" << q[k].second.moveStr << "\"";
                if (!q[k].second.varJson.empty())
                    sj << ", \"variations\": " << q[k].second.varJson;
                sj << "}";
                leaves = std::max(leaves, q[k].second.leaves);
            }
            sj << "]";
            if (g_cfg.branching >= 0 && leaves > g_cfg.branching) continue;
            solutionsJson = sj.str();
            depthUsed = g_cfg.moves;
        }

        std::ostringstream pj;
        pj << "  {\n"
           << "    \"layer\": \"" << layerName << "\",\n"
           << "    \"fen\": \"" << FenOf(s) << "\",\n"
           << "    \"task\": {\"type\": \"" << TaskTypeName(g_cfg.type)
           << "\", \"n\": " << g_cfg.moves << ", \"k\": " << g_cfg.captureK << "},\n"
           << "    \"kazan_white\": " << K1 << ",\n"
           << "    \"kazan_black\": " << K2 << ",\n"
           << "    \"stones_white\": " << cnt.stonesW << ",\n"
           << "    \"stones_black\": " << cnt.stonesB << ",\n"
           << "    \"empty_white\": " << cnt.emptyW << ",\n"
           << "    \"empty_black\": " << cnt.emptyB << ",\n"
           << "    \"leaf_variations\": " << leaves << ",\n"
           << "    \"depth\": " << depthUsed << ",\n"
           << "    \"solutions\": " << solutionsJson << "\n"
           << "  }";
        entries.push_back(pj.str());

        ++accepted;
        std::cout << "[FOUND] fen=\"" << FenOf(s) << "\" leaves=" << leaves << "\n";
    }

    if (!jsonOut.empty()) {
        std::ofstream out(jsonOut, std::ios::trunc);
        out << "[";
        for (size_t k = 0; k < entries.size(); ++k)
            out << "\n" << entries[k] << (k + 1 < entries.size() ? "," : "");
        out << "\n]\n";
    }

    std::cout << "[DONE] Accepted " << accepted << "/" << count << " after "
              << attempts << " attempts.\n";
    if (g_cfg.type == TaskType::Loop)
        std::cout << "       DRAW positions sampled: " << g_drawsSeen << "\n";
    return accepted > 0 ? 0 : 2;
}
