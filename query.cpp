// Tablebase Explorer CLI.
// Usage: ./query K1 K2 p0 p1 p2 p3 p4 p5 p6 p7 p8 p9
// The 12 fields describe the canonical state from the side-to-move perspective
// (K1/p0-p4 = mover, K2/p5-p9 = opponent). Emits a single JSON object.
#include "StateIndex.h"
#include "Oracle.h"
#include <iostream>
#include <string>
#include <sstream>

using namespace Bestemshe;

static const char* value_str(OracleValue v) {
    switch (v) {
        case OracleValue::WIN:  return "WIN";
        case OracleValue::LOSS: return "LOSS";
        case OracleValue::DRAW: return "DRAW";
        default:                return "UNKNOWN";
    }
}

static void emit_error(const std::string& msg) {
    std::cout << "{\"error\": \"" << msg << "\"}\n";
}

// Mirrors the sowing in ExecuteMoveAndFlip to find the pit (0..9) where the
// last stone lands. Used only for move notation.
static int landing_pit(const State& s, int i) {
    int pieces = s.board[i];
    int current = i;
    if (pieces == 1) {
        current = (current + 1) % 10;
    } else {
        pieces--;
        while (pieces > 0) { current = (current + 1) % 10; pieces--; }
    }
    return current;
}

static std::string board_json(const State& s) {
    std::ostringstream o;
    o << "[";
    for (int i = 0; i < 10; ++i) o << (i ? "," : "") << static_cast<int>(s.board[i]);
    o << "]";
    return o.str();
}

int main(int argc, char* argv[]) {
    StateIndex::InitCombinatorics();

    if (argc != 13) {
        emit_error("expected 12 integers: K1 K2 p0..p9");
        return 1;
    }

    int vals[12];
    for (int i = 0; i < 12; ++i) {
        try { vals[i] = std::stoi(argv[i + 1]); }
        catch (...) { emit_error("non-numeric argument"); return 1; }
        if (vals[i] < 0 || vals[i] > 50) { emit_error("field out of range 0..50"); return 1; }
    }

    State s;
    s.K_self = static_cast<uint8_t>(vals[0]);
    s.K_opp  = static_cast<uint8_t>(vals[1]);
    s.M = s.K_self + s.K_opp;
    int pit_sum = 0;
    for (int i = 0; i < 10; ++i) {
        s.board[i] = static_cast<uint8_t>(vals[i + 2]);
        pit_sum += vals[i + 2];
    }

    if (pit_sum + s.M != 50) { emit_error("stones must total 50 (pits + kazans)"); return 1; }
    if ((s.K_self % 2) || (s.K_opp % 2)) { emit_error("kazan counts must be even (captures are even)"); return 1; }
    if (s.K_self > 24 || s.K_opp > 24) {
        emit_error("game already decided (a kazan holds 26+) or kazan exceeds tablebase range");
        return 1;
    }

    TablebaseOracle oracle;

    OracleValue pos_val = oracle.query(s);
    if (pos_val == OracleValue::ERROR) {
        emit_error("tablebase lookup failed (missing/corrupt layer files in " + oracle.dir() + ")");
        return 1;
    }

    std::ostringstream out;
    out << "{\"position\": {\"K1\": " << (int)s.K_self << ", \"K2\": " << (int)s.K_opp
        << ", \"board\": " << board_json(s) << "},\n"
        << " \"value\": \"" << value_str(pos_val) << "\",\n"
        << " \"moves\": [";

    bool first = true;
    for (int pit = 0; pit < 5; ++pit) {
        if (s.board[pit] == 0) continue; // illegal move: omit entirely

        int land = landing_pit(s, pit);
        int from_idx = pit + 1;          // 1..5
        int to_idx = (land % 5) + 1;     // 1..5 (either side)

        State child;
        bool empties;
        bool capture = ExecuteMoveAndFlip(s, pit, child, empties);

        const char* result;
        bool terminal = false;
        if (empties || child.K_opp >= 26) {
            // Terminal: the mover wins immediately.
            result = "WIN";
            terminal = true;
        } else {
            OracleValue v = oracle.query(child);
            if (v == OracleValue::ERROR) { emit_error("lookup failed for move child"); return 1; }
            // Child value is from the opponent's perspective; invert for the mover.
            if (v == OracleValue::WIN)       result = "LOSS";
            else if (v == OracleValue::LOSS) result = "WIN";
            else                             result = "DRAW";
        }

        if (!first) out << ",";
        first = false;
        out << "\n  {\"from\": " << from_idx << ", \"to\": " << to_idx
            << ", \"capture\": " << (capture ? "true" : "false")
            << ", \"result\": \"" << result << "\""
            << ", \"terminal\": " << (terminal ? "true" : "false");

        // Raw canonical child (opponent to move) so the caller can continue play.
        if (!terminal) {
            out << ", \"child\": {\"K1\": " << (int)child.K_self
                << ", \"K2\": " << (int)child.K_opp << ", \"board\": " << board_json(child) << "}";
        }
        out << "}";
    }
    out << "\n]}";

    std::cout << out.str() << "\n";
    return 0;
}
