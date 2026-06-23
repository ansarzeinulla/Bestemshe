#pragma once
#include "Inference.h"
#include <vector>
#include <string>
#include <queue>
#include <mutex>
#include <atomic>

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

    // Fast-access state value vectors
    // 0x00: UNKNOWN, 0x01: WIN, 0x02: LOSS, 0x03: DRAW (repetition loop)
    std::vector<uint8_t> state_values;

    // Remaining dynamic moves that stay within layer M
    std::vector<uint8_t> dependency_counters; 

    // Tracks if a state has a transition that results in a static draw in a higher layer
    std::vector<bool> can_force_static_draw;

    // Thread-safe lock-free propagation queues
    std::queue<uint64_t> propagation_queue;
    std::mutex queue_mutex;

public:
    RetrogradeSolver(uint8_t target_M, InferenceEngine* db) 
        : layer_M(target_M), inference_engine(db) {
        num_states = GetLayerSize(layer_M);
        state_values.resize(num_states, static_cast<uint8_t>(GameValue::UNKNOWN));
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
};

} // namespace Bestemshe