// ============================================================================
// generateVictory — Bestemshe "Narrow Path" puzzle extractor
//
// Samples random positions from a solved (K1,K2) layer and keeps only
// positions where EXACTLY ONE legal move wins (at every player-to-move node
// of the solution tree), with a controllable opponent branching factor.
//
// Usage:
//   ./generateVictory --layer <K1>_<K2> --moves <N>
//                     --variationsMin <a> --variationsMax <b>
//                     [--count <n>] [--seed <s>] [--out <dir>] [--maxAttempts <n>]
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
static int g_vmin = 1, g_vmax = 9;

struct MoveInfo {
    int pit;          // canonical pit 0..4 of the side to move
    int landing;      // pit where the last stone lands (0..9, mover's frame)
    bool capture;
    bool empties;     // move leaves the opponent's side empty
    bool terminal;    // immediate win: empties opponent or kazan reaches 26+
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

// Disjoint win-type of a terminal winning move.
static std::string WinTypeOf(const MoveInfo& m) {
    bool k26 = m.flipped.K_opp >= 26;   // mover's kazan after the move
    if (!m.capture && m.empties) return "atsyrau";
    if (m.capture && k26 && !m.empties) return "kazan26";
    if (m.capture && m.empties && !k26) return "capture_atsyrau";
    return "double";                     // excluded when a winType filter is set
}

// All legal moves of the side to move in canonical state s.
static std::vector<MoveInfo> LegalMoves(const State& s) {
    std::vector<MoveInfo> out;
    for (int i = 0; i < 5; ++i) {
        if (s.board[i] == 0) continue;
        MoveInfo m;
        m.pit = i;
        int pieces = s.board[i];
        m.landing = (pieces == 1) ? (i + 1) % 10 : (i + pieces - 1) % 10;
        m.capture = ExecuteMoveAndFlip(s, i, m.flipped, m.empties);
        // After the flip, K_opp is the mover's kazan.
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

struct SolveResult {
    bool ok = false;
    int dtm = 0;            // plies to win against best defense
    std::string moveStr;    // our unique winning move, e.g. "54+#"
    std::string varJson;    // JSON of opponent variations; empty if terminal
    MoveInfo rootMove;      // the unique winning move at this node
};

static SolveResult SolveOur(const State& s, int budget);

// Opponent to move (canonical state from the opponent's perspective).
// Returns ok only if every legal reply is refuted by a unique winning move,
// and the reply count is within [g_vmin, g_vmax].
struct OppResult {
    bool ok = false;
    int dtm = 0;
    std::string json;   // {"<reply>": <our follow-up>, ...}
};

static OppResult SolveOpp(const State& s, int budget) {
    OppResult r;
    auto replies = LegalMoves(s);
    int n = static_cast<int>(replies.size());
    if (n == 0 || n < g_vmin || n > g_vmax) return r;

    std::ostringstream json;
    json << "{";
    int maxChild = 0;
    bool first = true;
    for (const auto& rep : replies) {
        // s is a LOSS for the opponent, so no reply can be terminal for them.
        if (rep.terminal) return r;
        SolveResult child = SolveOur(rep.flipped, budget - 1);
        if (!child.ok) return r;
        maxChild = std::max(maxChild, child.dtm);
        if (!first) json << ", ";
        first = false;
        json << "\"" << Notation(rep) << "\": ";
        if (child.varJson.empty())
            json << "\"" << child.moveStr << "\"";
        else
            json << "{\"move\": \"" << child.moveStr << "\", \"variations\": "
                 << child.varJson << "}";
    }
    json << "}";
    r.ok = true;
    r.dtm = 1 + maxChild;
    r.json = json.str();
    return r;
}

// Our side to move. Requires exactly one winning move among ALL legal moves,
// which forces a win within `budget` plies (odd).
static SolveResult SolveOur(const State& s, int budget) {
    SolveResult r;
    auto moves = LegalMoves(s);
    if (moves.empty()) return r;

    const MoveInfo* winner = nullptr;
    for (const auto& m : moves) {
        if (MoveWins(m)) {
            if (winner) return r;  // more than one winning move — not a puzzle
            winner = &m;
        }
    }
    if (!winner) return r;

    r.rootMove = *winner;
    if (winner->terminal) {
        r.ok = true;
        r.dtm = 1;
        r.moveStr = Notation(*winner);
        return r;
    }
    if (budget < 3) return r;  // needs more plies than we have
    OppResult opp = SolveOpp(winner->flipped, budget - 1);
    if (!opp.ok) return r;
    r.ok = true;
    r.dtm = 1 + opp.dtm;
    r.moveStr = Notation(*winner);
    r.varJson = opp.json;
    return r;
}

static std::string FenOf(const State& s, int K1, int K2) {
    std::ostringstream f;
    for (int i = 0; i < 5; ++i) f << (i ? "," : "") << (int)s.board[i];
    f << "/";
    for (int i = 5; i < 10; ++i) f << (i > 5 ? "," : "") << (int)s.board[i];
    f << " " << K1 << "," << K2 << " w " << (int)s.M;
    return f.str();
}

static std::string CategoryOf(int moves, int vmax) {
    if (moves == 1) return "win_in_1";
    if (moves == 2) return vmax <= 2 ? "win_in_2_easy" : "win_in_2_medium";
    if (moves == 3) return vmax <= 3 ? "win_in_3_normal" : "win_in_3_hard";
    return "win_in_" + std::to_string(moves);
}

// Count existing puzzles in the master file to continue id numbering.
static int CountExistingIds(const std::string& path) {
    std::ifstream f(path);
    if (!f) return 0;
    std::string content((std::istreambuf_iterator<char>(f)),
                        std::istreambuf_iterator<char>());
    int count = 0;
    size_t pos = 0;
    while ((pos = content.find("\"id\"", pos)) != std::string::npos) {
        ++count;
        pos += 4;
    }
    return count;
}

// Append entries to the master JSON array (creates it if missing).
static void AppendMaster(const std::string& path,
                         const std::vector<std::string>& entries) {
    std::string existing;
    if (fs::exists(path)) {
        std::ifstream f(path);
        existing.assign((std::istreambuf_iterator<char>(f)),
                        std::istreambuf_iterator<char>());
        size_t close = existing.rfind(']');
        if (close != std::string::npos) existing.erase(close);
        // Trim trailing whitespace
        while (!existing.empty() && isspace((unsigned char)existing.back()))
            existing.pop_back();
        if (!existing.empty() && existing.back() != '[') existing += ",";
    }
    if (existing.empty()) existing = "[";
    std::ofstream out(path, std::ios::trunc);
    out << existing;
    for (size_t i = 0; i < entries.size(); ++i)
        out << "\n" << entries[i] << (i + 1 < entries.size() ? "," : "");
    out << "\n]\n";
}

static void PrintUsage() {
    std::cout <<
        "Usage:\n"
        "  ./generateVictory --layer <K1>_<K2> --moves <N> \\\n"
        "                    --variationsMin <a> --variationsMax <b> \\\n"
        "                    [--count <n>=50] [--seed <s>] [--out <dir>=puzzles] \\\n"
        "                    [--maxAttempts <n>=2000000]\n\n"
        "  --layer          Layer to sample, e.g. 2_8 (K_self=2, K_opp=8).\n"
        "                   A path like layers/compressed/layer_2_8_win.bin also works.\n"
        "  --moves          Win in N moves (N=1 -> DTM 1, N=2 -> DTM 3, N=3 -> DTM 5).\n"
        "  --variationsMin  Min legal opponent replies at every opponent node.\n"
        "  --variationsMax  Max legal opponent replies at every opponent node.\n";
}

int main(int argc, char* argv[]) {
    StateIndex::InitCombinatorics();

    std::string layerArg, outDir = "puzzles", winType, jsonOut;
    int moves = -1, vmin = 1, vmax = 9, count = 50, fromPit = -1;
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
        if (a == "--layer") layerArg = next("--layer");
        else if (a == "--moves") moves = std::stoi(next("--moves"));
        else if (a == "--variationsMin") vmin = std::stoi(next("--variationsMin"));
        else if (a == "--variationsMax") vmax = std::stoi(next("--variationsMax"));
        else if (a == "--count") count = std::stoi(next("--count"));
        else if (a == "--seed") seed = std::stoull(next("--seed"));
        else if (a == "--out") outDir = next("--out");
        else if (a == "--maxAttempts") maxAttempts = std::stoull(next("--maxAttempts"));
        else if (a == "--fromPit") fromPit = std::stoi(next("--fromPit"));
        else if (a == "--winType") winType = next("--winType");
        else if (a == "--jsonOut") jsonOut = next("--jsonOut");
        else { PrintUsage(); return 1; }
    }

    if (layerArg.empty() || moves < 1) { PrintUsage(); return 1; }

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

    g_vmin = vmin;
    g_vmax = vmax;
    const int targetDtm = 2 * moves - 1;
    const std::string category = CategoryOf(moves, vmax);
    const std::string layerName = std::to_string(K1) + "_" + std::to_string(K2);

    int R = 50 - M;
    uint64_t bCount = StateIndex::nCr(R + 9, 9);
    uint64_t iK = (uint64_t)(K1 - StateIndex::GetMinK(M)) / 2;

    std::cout << "[INFO] Layer (" << K1 << "," << K2 << "), M=" << (int)M
              << ", boards=" << bCount << ", target DTM=" << targetDtm
              << ", replies in [" << vmin << "," << vmax << "], category="
              << category << ", seed=" << seed << "\n";

    if (jsonOut.empty()) fs::create_directories(fs::path(outDir) / category);
    std::string masterPath = (fs::path(outDir) / "bestemshe_puzzles_master.json").string();
    int nextId = jsonOut.empty() ? CountExistingIds(masterPath) + 1 : 1;

    std::mt19937_64 rng(seed);
    std::uniform_int_distribution<uint64_t> dist(0, bCount - 1);
    std::set<uint64_t> seen;
    std::vector<std::string> masterEntries;

    int accepted = 0;
    uint64_t attempts = 0;
    for (; attempts < maxAttempts && accepted < count; ++attempts) {
        uint64_t iB = dist(rng);
        if (!seen.insert(iB).second) continue;

        State s = StateIndex::UnindexState(iK * bCount + iB, M);

        // Side to move must have stones and the position must be a forced win.
        bool hasMove = false;
        for (int i = 0; i < 5; ++i) if (s.board[i]) { hasMove = true; break; }
        if (!hasMove) continue;
        if (g_db.query_state(M, (uint8_t)K2, iB) != GameValue::WIN) continue;

        SolveResult res = SolveOur(s, targetDtm);
        if (!res.ok || res.dtm != targetDtm) continue;

        const MoveInfo& wm = res.rootMove;
        if (fromPit != -1 && wm.pit + 1 != fromPit) continue;
        std::string wt = WinTypeOf(wm);
        if (!winType.empty() && wt != winType) continue;
        int toCell = (wm.landing <= 4) ? wm.landing + 1 : wm.landing - 4;

        // Build the puzzle JSON
        std::ostringstream pj;
        char idBuf[16];
        snprintf(idBuf, sizeof(idBuf), "%04d", nextId);
        pj << "  {\n"
           << "    \"id\": \"" << idBuf << "\",\n"
           << "    \"category\": \"" << category << "\",\n"
           << "    \"layer\": \"" << layerName << "\",\n"
           << "    \"fen\": \"" << FenOf(s, K1, K2) << "\",\n"
           << "    \"moves_to_win\": " << moves << ",\n"
           << "    \"from_cell\": " << wm.pit + 1 << ",\n"
           << "    \"to_cell\": " << toCell << ",\n"
           << "    \"win_type\": \"" << wt << "\",\n"
           << "    \"notation\": \"" << res.moveStr << "\",\n"
           << "    \"solution\": {\n"
           << "      \"first_move\": \"" << res.moveStr << "\"";
        if (!res.varJson.empty())
            pj << ",\n      \"variations\": " << res.varJson;
        pj << "\n    }\n  }";

        std::string entry = pj.str();
        masterEntries.push_back(entry);

        if (jsonOut.empty()) {
            std::ofstream single(fs::path(outDir) / category / (std::string(idBuf) + ".json"));
            single << entry.substr(2) << "\n";  // drop the array indent
        }

        ++accepted;
        ++nextId;
        std::cout << "[FOUND] #" << idBuf << " fen=\"" << FenOf(s, K1, K2)
                  << "\" first_move=" << res.moveStr << "\n";
    }

    if (!jsonOut.empty()) {
        std::ofstream out(jsonOut, std::ios::trunc);
        out << "[";
        for (size_t k = 0; k < masterEntries.size(); ++k)
            out << "\n" << masterEntries[k] << (k + 1 < masterEntries.size() ? "," : "");
        out << "\n]\n";
    } else if (!masterEntries.empty()) {
        AppendMaster(masterPath, masterEntries);
    }

    std::cout << "[DONE] Accepted " << accepted << "/" << count << " puzzles after "
              << attempts << " attempts.\n"
              << "       Master: " << masterPath << "\n"
              << "       Folder: " << (fs::path(outDir) / category).string() << "\n";
    return accepted > 0 ? 0 : 2;
}
