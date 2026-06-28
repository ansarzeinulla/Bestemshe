#pragma once
#include "Inference.h"
#include "StateIndex.h"
#include <vector>
#include <atomic>
#include <cstdint>
#include <string>

namespace Bestemshe {

class RetrogradeSolver {
public:
    RetrogradeSolver(uint8_t target_M, InferenceEngine* db) 
        : layer_M(target_M), inference_engine(db) {}

    // Generates the absolute game-theoretic truth for a specific symmetric pair
    void solve_pair_lock_free(uint16_t K1, uint16_t K2);
    
    // Verifies the pair is mathematically sound against the disk files
    void verify_pair_consistency(uint16_t K1, uint16_t K2);

private:
    uint8_t layer_M;
    InferenceEngine* inference_engine;

    static inline uint8_t EncodeGameValue(GameValue v) { return static_cast<uint8_t>(v) & 0x03; }
    static inline GameValue DecodeGameValue(uint8_t v) { return static_cast<GameValue>(v & 0x03); }

    // -------------------------------------------------------------------------
    // HOT LOOP HARDWARE: Zero-Allocation Move Generator
    // -------------------------------------------------------------------------
    static inline void execute_move_and_flip(const uint8_t src[10], int pit, 
                                             uint8_t dest[10], bool& is_capture, 
                                             bool& empties_opp, uint8_t& captured) 
    {
        uint8_t temp[10];
        for (int i = 0; i < 10; ++i) temp[i] = src[i];

        int pieces = temp[pit];
        temp[pit] = 0;

        int current = pit;
        if (pieces == 1) {
            current = (current + 1) % 10;
            temp[current]++;
        } else {
            temp[pit] = 1;
            pieces--;
            while (pieces > 0) {
                current = (current + 1) % 10;
                temp[current]++;
                pieces--;
            }
        }

        is_capture = false;
        captured = 0;
        // Even Parity Capture on opponent's side (pits 5..9)
        if (current >= 5 && current <= 9 && (temp[current] % 2) == 0) {
            captured = temp[current];
            temp[current] = 0;
            is_capture = true;
        }

        empties_opp = true;
        for (int i = 5; i <= 9; ++i) {
            if (temp[i] > 0) {
                empties_opp = false;
                break;
            }
        }

        // Fast flip perspective for the opponent
        for (int i = 0; i < 5; ++i) {
            dest[i] = temp[i + 5];
            dest[i + 5] = temp[i];
        }
    }

    // $O(1)$ amortized local offset generation (ignores K invariants)
    static inline uint64_t IndexBoard(const uint8_t board[10]) {
        uint64_t I_B = 0;
        int sum = 0;
        for (int i = 0; i < 9; ++i) {
            sum += board[i];
            I_B += StateIndex::nCr(i + sum, i + 1);
        }
        return I_B;
    }
};

} // namespace Bestemshe