#pragma once
#include "Inference.h"
#include <vector>
#include <string>
#include <queue>
#include <mutex>
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
private:
    uint8_t layer_M;
    uint64_t num_states;
    InferenceEngine* inference_engine;

    // 2-bit packed state values:
    // 00 UNKNOWN, 01 WIN, 10 LOSS, 11 DRAW
    std::vector<std::atomic<uint8_t>> state_values_2bit;

    // Remaining dynamic moves that stay within layer M
    std::vector<uint8_t> dependency_counters; 

    // Tracks if a state has a transition that results in a static draw in a higher layer
    std::vector<bool> can_force_static_draw;

    // Thread-safe lock-free propagation queues
    std::queue<uint64_t> propagation_queue;
    std::mutex queue_mutex;

public:
    RetrogradeSolver(uint8_t target_M, InferenceEngine* db) 
        : layer_M(target_M), inference_engine(db), state_values_2bit((GetLayerSize(target_M) + 3) / 4) {
        num_states = GetLayerSize(layer_M);
        for (auto& byte : state_values_2bit) {
            byte.store(0, std::memory_order_relaxed);
        }
        dependency_counters.resize(num_states, 0);
        can_force_static_draw.resize(num_states, false);
    }

    // Main pipeline execution
    void solve_layer() {
        std::cout << "[INFO] Initializing Dependency Graph..." << std::endl;
        initialize_dependency_graph();

        std::cout << "[INFO] Executing Queue Propagation (Linear-Time Cycle Resolution)..." << std::endl;
        propagate_proven_values();

        std::cout << "[INFO] Resolving Leftover States as Loop-Based Draws..." << std::endl;
        finalize_draws();
    }

    void solve_layer_lock_free();
    void verify_layer_consistency();
    bool load_layer_from_monoliths(const std::string& out_dir);

    // Save final partitions in raw format for ./split
    void write_raw_monoliths(const std::string& out_dir);

private:
    // Phase 0 & Graph Init: Computes initial out-degrees and pre-resolves capturing moves
    void initialize_dependency_graph();

    // Core solver loop: Cascades proved values back to parents
    void propagate_proven_values();

    // Resolves circular dependencies into Draws
    void finalize_draws();

    // Reverse Move Generation: Finds all predecessor states (parents) in Layer M
    std::vector<uint64_t> generate_predecessors(uint64_t index);

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
    inline GameValue ReadState2Bit(uint64_t idx) const {
        uint64_t byte_idx = idx / 4;
        uint8_t bit_shift = static_cast<uint8_t>((idx % 4) * 2);
        uint8_t byte_val = state_values_2bit[byte_idx].load(std::memory_order_relaxed);
        return DecodeGameValue((byte_val >> bit_shift) & 0x03);
    }
    inline void WriteState2Bit(uint64_t idx, GameValue val) {
        uint64_t byte_idx = idx / 4;
        uint8_t bit_shift = static_cast<uint8_t>((idx % 4) * 2);
        uint8_t mask = static_cast<uint8_t>(~(0x03u << bit_shift));
        uint8_t new_bits = static_cast<uint8_t>(EncodeGameValue(val) << bit_shift);
        uint8_t current = state_values_2bit[byte_idx].load(std::memory_order_relaxed);
        while (!state_values_2bit[byte_idx].compare_exchange_weak(
            current, static_cast<uint8_t>((current & mask) | new_bits),
            std::memory_order_relaxed, std::memory_order_relaxed)) {
        }
    }
};

} // namespace Bestemshe
