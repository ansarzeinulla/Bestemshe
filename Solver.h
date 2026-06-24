#pragma once
#include "Inference.h"
#include <vector>
#include <string>
#include <atomic>
#include <cstddef>
#include <omp.h>

namespace Bestemshe {

// In-memory representations of active game states for retrograde evaluation
struct SolverState {
    uint8_t K_self;
    uint8_t K_opp;
    uint8_t board[10];
};

class RetrogradeSolver {
public:
    void solve_pair_lock_free(uint16_t K1, uint16_t K2);
private:
    uint8_t layer_M;
    uint64_t num_states;
    InferenceEngine* inference_engine;

    // 2-bit packed state values:
    // 00 UNKNOWN, 01 WIN, 10 LOSS, 11 DRAW
    std::vector<std::atomic<uint8_t>> state_values_2bit;

public:
    RetrogradeSolver(uint8_t target_M, InferenceEngine* db)
        : layer_M(target_M), inference_engine(db), state_values_2bit((GetLayerSize(target_M) + 3) / 4) {
        num_states = GetLayerSize(layer_M);
        for (auto& byte : state_values_2bit) byte.store(0, std::memory_order_relaxed);
    }

    void solve_layer_lock_free();
    void verify_layer_consistency();
    bool load_layer_from_monoliths(const std::string& out_dir);

    // Save final partitions in raw format for ./split
    void write_raw_monoliths(const std::string& out_dir);

private:
    // Resolves any state still UNKNOWN after value-iteration convergence into a DRAW
    // (those states form inescapable, capture-free cycles within layer M).
    void finalize_draws();

    // Helpers from your original implementation
    uint64_t GetLayerSize(uint8_t M);
    uint64_t IndexState(const SolverState& s);
    SolverState UnindexState(uint64_t index, uint8_t M);
    static inline uint8_t EncodeGameValue(GameValue v) {
        return static_cast<uint8_t>(v) & 0x03;
    }
    static inline GameValue DecodeGameValue(uint8_t v) {
        return static_cast<GameValue>(v & 0x03);
    }
public:
    inline GameValue ReadState2Bit(uint64_t idx) const {
        uint64_t byte_idx = idx / 4;
        uint8_t bit_shift = static_cast<uint8_t>((idx % 4) * 2);
        uint8_t byte_val = state_values_2bit[byte_idx].load(std::memory_order_acquire);
        return DecodeGameValue((byte_val >> bit_shift) & 0x03);
    }
    inline void WriteState2Bit(uint64_t idx, GameValue val) {
        uint64_t byte_idx = idx / 4;
        uint8_t bit_shift = static_cast<uint8_t>((idx % 4) * 2);
        uint8_t mask = static_cast<uint8_t>(~(0x03u << bit_shift));
        uint8_t new_bits = static_cast<uint8_t>(EncodeGameValue(val) << bit_shift);
        uint8_t current = state_values_2bit[byte_idx].load(std::memory_order_acquire);
        while (!state_values_2bit[byte_idx].compare_exchange_weak(
            current, static_cast<uint8_t>((current & mask) | new_bits),
            std::memory_order_release, std::memory_order_acquire)) {
        }
    }
};

} // namespace Bestemshe
