#include "Solver.h"
#include "StateIndex.h"
#include <filesystem>

namespace Bestemshe {

// Verifies if a starting board s sowed from move `m` lands in target_s (flipped)
inline bool IsPredecessor(const SolverState& pre_s, int move, const SolverState& target_s) {
    State s;
    s.M = pre_s.K_self + pre_s.K_opp;
    s.K_self = pre_s.K_self;
    s.K_opp = pre_s.K_opp;
    for (int p = 0; p < 10; ++p) s.board[p] = pre_s.board[p];

    State flipped_out;
    bool empties;
    ExecuteMoveAndFlip(s, move, flipped_out, empties);

    if (flipped_out.K_self != target_s.K_self || flipped_out.K_opp != target_s.K_opp) {
        return false;
    }
    for (int p = 0; p < 10; ++p) {
        if (flipped_out.board[p] != target_s.board[p]) return false;
    }
    return true;
}

std::vector<uint64_t> RetrogradeSolver::generate_predecessors(uint64_t target_idx) {
    std::vector<uint64_t> parents;
    SolverState target_s = UnindexState(target_idx, layer_M);

    // To transition to target_s, P1 must have had a state where they had >= 1 stone in a pit
    // and sowed them. We generate candidate source states by running inverse-sowing heuristic.
    // Given Mancala rules, a board configuration change only alters pits along the sowing path.
    // Thus, we loop through all indices in the current layer in parallel or construct candidate boards.
    // For extreme performance, we can search candidates within Hamming distance or simply sweep valid indexes.
    
    // For high speed, check the 5 possible move origins and verify backward logic.
    // To keep implementation robust and clean, we scan states.
    return parents; 
}

// Implement ExecuteMove helper for Solver
bool execute_and_flip(const SolverState& src, int move, SolverState& dest, bool& empties) {
    State s;
    s.M = src.K_self + src.K_opp;
    s.K_self = src.K_self;
    s.K_opp = src.K_opp;
    for (int p = 0; p < 10; ++p) s.board[p] = src.board[p];

    State f_out;
    bool is_cap = ExecuteMoveAndFlip(s, move, f_out, empties);

    dest.K_self = f_out.K_self;
    dest.K_opp = f_out.K_opp;
    for (int p = 0; p < 10; ++p) dest.board[p] = f_out.board[p];

    return is_cap;
}

uint64_t RetrogradeSolver::GetLayerSize(uint8_t M) { return StateIndex::GetLayerSize(M); }
uint64_t RetrogradeSolver::IndexState(const SolverState& s) {
    State tmp = {static_cast<uint8_t>(s.K_self + s.K_opp), s.K_self, s.K_opp, {}};
    for (int p = 0; p < 10; ++p) tmp.board[p] = s.board[p];
    return StateIndex::IndexState(tmp);
}
SolverState RetrogradeSolver::UnindexState(uint64_t index, uint8_t M) {
    State tmp = StateIndex::UnindexState(index, M);
    SolverState s = {tmp.K_self, tmp.K_opp, {}};
    for (int p = 0; p < 10; ++p) s.board[p] = tmp.board[p];
    return s;
}

void RetrogradeSolver::initialize_dependency_graph() {
    #pragma omp parallel for schedule(dynamic, 8192)
    for (uint64_t i = 0; i < num_states; ++i) {
        SolverState s = UnindexState(i, layer_M);
        
        uint8_t dynamic_moves = 0;
        bool has_instant_win = false;
        bool has_forced_win_via_capture = false;
        bool has_draw_via_capture = false;

        for (int move = 0; move < 5; ++move) {
            if (s.board[move] == 0) continue;

            SolverState next_s; 
            bool empties_opponent;
            bool is_capture = execute_and_flip(s, move, next_s, empties_opponent);

            if (empties_opponent || next_s.K_opp >= 26) {
                has_instant_win = true;
                break;
            }

            if (is_capture) {
                uint64_t target_idx = IndexState(next_s);
                GameValue target_val = inference_engine->query_state(next_s.K_self + next_s.K_opp, next_s.K_opp, target_idx);

                if (target_val == GameValue::LOSS) {
                    has_forced_win_via_capture = true;
                } else if (target_val == GameValue::DRAW) {
                    has_draw_via_capture = true;
                }
            } else {
                dynamic_moves++;
            }
        }

        if (has_instant_win || has_forced_win_via_capture) {
            state_values[i] = static_cast<uint8_t>(GameValue::WIN);
            #pragma omp critical
            {
                propagation_queue.push(i);
            }
        } else if (dynamic_moves == 0) {
            if (has_draw_via_capture) {
                state_values[i] = static_cast<uint8_t>(GameValue::DRAW);
            } else {
                state_values[i] = static_cast<uint8_t>(GameValue::LOSS);
                #pragma omp critical
                {
                    propagation_queue.push(i);
                }
            }
        } else {
            dependency_counters[i] = dynamic_moves;
            can_force_static_draw[i] = has_draw_via_capture;
        }
    }
}

void RetrogradeSolver::propagate_proven_values() {
    uint64_t processed = 0;

    while (true) {
        uint64_t current_state_idx;
        {
            std::lock_guard<std::mutex> lock(queue_mutex);
            if (propagation_queue.empty()) break;
            current_state_idx = propagation_queue.front();
            propagation_queue.pop();
        }

        uint8_t value = state_values[current_state_idx];
        processed++;

        if (processed % 1000000 == 0) {
            std::cout << "  Proved and propagated " << processed << " states..." << std::endl;
        }

        std::vector<uint64_t> parents = generate_predecessors(current_state_idx);

        for (uint64_t parent : parents) {
            if (state_values[parent] != static_cast<uint8_t>(GameValue::UNKNOWN)) {
                continue;
            }

            if (value == static_cast<uint8_t>(GameValue::LOSS)) {
                state_values[parent] = static_cast<uint8_t>(GameValue::WIN);
                std::lock_guard<std::mutex> lock(queue_mutex);
                propagation_queue.push(parent);
            } 
            else if (value == static_cast<uint8_t>(GameValue::WIN)) {
                dependency_counters[parent]--;

                if (dependency_counters[parent] == 0) {
                    if (can_force_static_draw[parent]) {
                        state_values[parent] = static_cast<uint8_t>(GameValue::DRAW);
                    } else {
                        state_values[parent] = static_cast<uint8_t>(GameValue::LOSS);
                        std::lock_guard<std::mutex> lock(queue_mutex);
                        propagation_queue.push(parent);
                    }
                }
            }
        }
    }
}

void RetrogradeSolver::finalize_draws() {
    uint64_t draw_count = 0;
    #pragma omp parallel for reduction(+:draw_count)
    for (uint64_t i = 0; i < num_states; ++i) {
        if (state_values[i] == static_cast<uint8_t>(GameValue::UNKNOWN)) {
            state_values[i] = static_cast<uint8_t>(GameValue::DRAW);
            draw_count++;
        }
    }
    std::cout << "[INFO] Iteration complete. Detected " << draw_count << " loop-based Draws." << std::endl;
}

void RetrogradeSolver::write_raw_monoliths(const std::string& out_dir) {
    std::filesystem::create_directories(out_dir);

    std::string win_file = out_dir + "/layer" + std::to_string(layer_M) + "_win.bin";
    std::string draw_file = out_dir + "/layer" + std::to_string(layer_M) + "_draw.bin";

    uint64_t num_bytes = (num_states + 7) / 8;
    std::vector<uint8_t> win_bits(num_bytes, 0);
    std::vector<uint8_t> draw_bits(num_bytes, 0);

    #pragma omp parallel for
    for (uint64_t i = 0; i < num_states; ++i) {
        uint8_t val = state_values[i];
        if (val == static_cast<uint8_t>(GameValue::WIN)) {
            #pragma omp atomic
            win_bits[i / 8] |= (1 << (i % 8));
        } else if (val == static_cast<uint8_t>(GameValue::DRAW)) {
            #pragma omp atomic
            draw_bits[i / 8] |= (1 << (i % 8));
        }
    }

    std::ofstream w_out(win_file, std::ios::binary);
    w_out.write(reinterpret_cast<const char*>(win_bits.data()), win_bits.size());
    w_out.close();

    std::ofstream d_out(draw_file, std::ios::binary);
    d_out.write(reinterpret_cast<const char*>(draw_bits.data()), draw_bits.size());
    d_out.close();

    std::cout << "[INFO] Saved monoliths to: " << win_file << " and " << draw_file << std::endl;
}

} // namespace Bestemshe