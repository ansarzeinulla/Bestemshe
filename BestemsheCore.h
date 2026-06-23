#pragma once
#include <cstdint>
#include <vector>
#include <algorithm>
#include <iostream>

namespace Bestemshe {

struct State {
    uint8_t M;        // Total stones captured (K_self + K_opp)
    uint8_t K_self;   // Active player's Kazan
    uint8_t K_opp;    // Opponent's Kazan
    uint8_t board[10]; // Pits 0-4 (Self), 5-9 (Opponent)
};

// Sows from pit `i` (0..4) and returns if a capture occurred.
// If valid, writes results to `next_s`.
inline bool ExecuteMoveAndFlip(const State& s, int i, State& flipped_out, bool& empties_opponent) {
    if (s.board[i] == 0) return false;

    State next_s = s;
    int pieces = next_s.board[i];
    next_s.board[i] = 0;

    int current_pit = i;
    if (pieces == 1) {
        current_pit = (current_pit + 1) % 10;
        next_s.board[current_pit]++;
    } else {
        next_s.board[i] = 1;
        pieces--;
        while (pieces > 0) {
            current_pit = (current_pit + 1) % 10;
            next_s.board[current_pit]++;
            pieces--;
        }
    }

    bool is_capture = false;
    // Even Parity Capture on opponent's side (pits 5..9)
    if (current_pit >= 5 && current_pit <= 9) {
        if (next_s.board[current_pit] % 2 == 0) {
            uint8_t captured = next_s.board[current_pit];
            next_s.K_self += captured;
            next_s.M += captured;
            next_s.board[current_pit] = 0;
            is_capture = true;
        }
    }

    // Evaluate if opponent is completely emptied
    empties_opponent = true;
    for (int p = 5; p <= 9; ++p) {
        if (next_s.board[p] > 0) {
            empties_opponent = false;
            break;
        }
    }

    // Flip board for opponent's turn perspective
    flipped_out.M = next_s.M;
    flipped_out.K_self = next_s.K_opp;
    flipped_out.K_opp = next_s.K_self;
    for (int p = 0; p < 5; ++p) {
        flipped_out.board[p] = next_s.board[p + 5];
        flipped_out.board[p + 5] = next_s.board[p];
    }

    return is_capture;
}

} // namespace Bestemshe