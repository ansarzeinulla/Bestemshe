#include "Solver.h"
#include "StateIndex.h"
#include "Compressor.h"
#include <filesystem>
#include <atomic>
#include <iostream>
#include <chrono>
#include <sstream>
#include <unordered_map>

namespace Bestemshe {

// Advance a full SolverState to the next global index in layer M (R = 50 - M on board).
// Uses the shared StateIndex::AdvanceBoard odometer and handles the K-dimension carry when
// the board composition (I_B) wraps. Verified against UnindexState by `--selftest` before
// it is relied on in the hot loop.
static inline void advance_solver_state(SolverState& s, int R) {
    if (!StateIndex::AdvanceBoard(s.board)) {
        s.K_self += 2;
        s.K_opp  -= 2;
        for (int p = 0; p < 9; ++p) s.board[p] = 0;
        s.board[9] = static_cast<uint8_t>(R);
    }
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

void RetrogradeSolver::solve_layer_lock_free() {
    auto t_init_start = std::chrono::high_resolution_clock::now();
    auto t_init_end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double> d_init = t_init_end - t_init_start;
    std::cout << "[BENCHMARK] Memory Alloc & Init: " << d_init.count() << "s\n";

    // Preload all higher layers to avoid concurrent hash map modification races.
    inference_engine->preload_all_layers(layer_M);

    auto t_sweep_start = std::chrono::high_resolution_clock::now();
    int iteration = 0;


    while (true) {
        auto t_iter_start = std::chrono::high_resolution_clock::now();
        iteration++;
        
        std::atomic<uint64_t> states_proven_this_iter{0};

        // Static, contiguous per-thread chunking (NOT dynamic): the board odometer
        // requires each thread to walk a contiguous index run. We decode the board once at
        // `begin` via UnindexState, then advance in O(1) amortized per state with
        // advance_solver_state, instead of a full combinadic decode on every state.
        const int R = 50 - static_cast<int>(layer_M);
        #pragma omp parallel
        {
            uint64_t threads = static_cast<uint64_t>(omp_get_num_threads());
            uint64_t tid = static_cast<uint64_t>(omp_get_thread_num());
            uint64_t chunk = (num_states + threads - 1) / threads;
            uint64_t begin = tid * chunk;
            uint64_t end = std::min(num_states, begin + chunk);

            if (begin < end) {
                SolverState s = UnindexState(begin, layer_M);
                for (uint64_t i = begin; i < end; ++i) {
                    uint8_t current_val = static_cast<uint8_t>(ReadState2Bit(i));
                    if (current_val == static_cast<uint8_t>(GameValue::UNKNOWN)) {
                        bool all_losses_for_me = true;
                        bool proved_win = false;

                        for (int move = 0; move < 5; ++move) {
                            if (s.board[move] == 0) continue;

                            SolverState next_s;
                            bool empties_opponent;
                            bool is_capture = execute_and_flip(s, move, next_s, empties_opponent);

                            GameValue target_val;

                            if (empties_opponent || next_s.K_opp >= 26) {
                                target_val = GameValue::LOSS;
                            } else if (is_capture) {
                                uint64_t target_idx = IndexState(next_s);
                                target_val = inference_engine->query_state(next_s.K_self + next_s.K_opp, next_s.K_opp, target_idx);
                            } else {
                                uint64_t target_idx = IndexState(next_s);
                                target_val = ReadState2Bit(target_idx);
                            }

                            if (target_val == GameValue::LOSS) {
                                proved_win = true;
                                break;
                            }
                            if (target_val == GameValue::DRAW || target_val == GameValue::UNKNOWN)
                                all_losses_for_me = false;
                        }

                        if (proved_win) {
                            WriteState2Bit(i, GameValue::WIN);
                            states_proven_this_iter.fetch_add(1, std::memory_order_acq_rel);
                        } else if (all_losses_for_me) {
                            WriteState2Bit(i, GameValue::LOSS);
                            states_proven_this_iter.fetch_add(1, std::memory_order_acq_rel);
                        }
                    }

                    if (i + 1 < end) advance_solver_state(s, R);
                }
            }
        }
        auto t_iter_end = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double> d_iter = t_iter_end - t_iter_start;
        std::cout << "  Iter " << iteration << ": Proven " << states_proven_this_iter.load(std::memory_order_acquire) 
                  << " states. Time: " << d_iter.count() << "s\n";

        // No states proven this iteration -> we have converged.
        // Any remaining UNKNOWN states form inescapable cycles -> they are true DRAW.
        if (states_proven_this_iter.load(std::memory_order_acquire) == 0) break;
    }
    auto t_sweep_end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double> d_sweep = t_sweep_end - t_sweep_start;
    std::cout << "[BENCHMARK] Total Value Iteration: " << d_sweep.count() << "s\n";
    // After convergence, any state still UNKNOWN is part of an inescapable cycle -> DRAW.
    finalize_draws();
}

void RetrogradeSolver::verify_layer_consistency() {
    uint64_t total_states = num_states;
    std::cout << "[INFO] Verifying layer " << static_cast<int>(layer_M) << " consistency with local retrograde validation...\n";

    // Allocate a thread-safe local buffer to run the verification sweep
    std::vector<std::atomic<uint8_t>> local_db((total_states + 3) / 4);
    for (auto& val : local_db) val.store(0, std::memory_order_relaxed);
    auto read_local = [&](uint64_t idx) -> GameValue {
        uint64_t byte_idx = idx / 4;
        uint8_t shift = static_cast<uint8_t>((idx % 4) * 2);
        uint8_t byte_val = local_db[byte_idx].load(std::memory_order_relaxed);
        return static_cast<GameValue>((byte_val >> shift) & 0x03);
    };
    auto write_local = [&](uint64_t idx, GameValue val) {
        uint64_t byte_idx = idx / 4;
        uint8_t shift = static_cast<uint8_t>((idx % 4) * 2);
        uint8_t mask = static_cast<uint8_t>(~(0x03u << shift));
        uint8_t new_bits = static_cast<uint8_t>((static_cast<uint8_t>(val) & 0x03u) << shift);
        uint8_t current = local_db[byte_idx].load(std::memory_order_relaxed);
        while (!local_db[byte_idx].compare_exchange_weak(
            current, static_cast<uint8_t>((current & mask) | new_bits),
            std::memory_order_relaxed, std::memory_order_relaxed)) {
        }
    };

    // Preload higher layers
    inference_engine->preload_all_layers(layer_M);

    // Solve locally from UNKNOWN
    int verification_iteration = 0;
    while (true) {
        auto t_iter_start = std::chrono::high_resolution_clock::now();
        verification_iteration++;
        std::atomic<uint64_t> states_proven{0};

        const int R = 50 - static_cast<int>(layer_M);
        #pragma omp parallel
        {
            uint64_t threads = static_cast<uint64_t>(omp_get_num_threads());
            uint64_t tid = static_cast<uint64_t>(omp_get_thread_num());
            uint64_t chunk = (total_states + threads - 1) / threads;
            uint64_t begin = tid * chunk;
            uint64_t end = std::min(total_states, begin + chunk);

            if (begin < end) {
                SolverState s = UnindexState(begin, layer_M);
                for (uint64_t i = begin; i < end; ++i) {
                    if (read_local(i) == GameValue::UNKNOWN) {
                        bool all_losses_for_me = true;
                        bool proved_win = false;
                        bool has_moves = false;

                        for (int move = 0; move < 5; ++move) {
                            if (s.board[move] == 0) continue;
                            has_moves = true;

                            SolverState next_s;
                            bool empties_opponent;
                            bool is_capture = execute_and_flip(s, move, next_s, empties_opponent);

                            GameValue target_val;
                            if (empties_opponent || next_s.K_opp >= 26) {
                                target_val = GameValue::LOSS;
                            } else if (is_capture) {
                                uint64_t target_idx = IndexState(next_s);
                                target_val = inference_engine->query_state(next_s.K_self + next_s.K_opp, next_s.K_opp, target_idx);
                            } else {
                                uint64_t target_idx = IndexState(next_s);
                                target_val = read_local(target_idx);
                            }

                            if (target_val == GameValue::LOSS) {
                                proved_win = true;
                                break;
                            }
                            if (target_val == GameValue::DRAW || target_val == GameValue::UNKNOWN)
                                all_losses_for_me = false;
                        }

                        if (!has_moves) {
                            write_local(i, GameValue::LOSS);
                            states_proven.fetch_add(1, std::memory_order_acq_rel);
                        } else if (proved_win) {
                            write_local(i, GameValue::WIN);
                            states_proven.fetch_add(1, std::memory_order_acq_rel);
                        } else if (all_losses_for_me) {
                            write_local(i, GameValue::LOSS);
                            states_proven.fetch_add(1, std::memory_order_acq_rel);
                        }
                    }

                    if (i + 1 < end) advance_solver_state(s, R);
                }
            }
        }

        auto t_iter_end = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double> d_iter = t_iter_end - t_iter_start;
        std::cout << "  [Verify] Iter " << verification_iteration << ": Proven " 
                  << states_proven.load(std::memory_order_acquire) << " states. Time: " << d_iter.count() << "s\n";

        if (states_proven.load(std::memory_order_acquire) == 0) break;
    }

    // Mark remaining UNKNOWN as DRAW in local verification DB
    #pragma omp parallel for schedule(static)
    for (uint64_t i = 0; i < total_states; ++i)
        if (read_local(i) == GameValue::UNKNOWN) write_local(i, GameValue::DRAW);

    // Now check for discrepancies against the stored database
    std::atomic<uint64_t> errors{0};
    #pragma omp parallel for schedule(dynamic, 8192)
    for (uint64_t i = 0; i < total_states; ++i) {
        GameValue stored_val = ReadState2Bit(i);
        GameValue computed_val = read_local(i);

        if (stored_val != computed_val) {
            uint64_t err_idx = errors.fetch_add(1, std::memory_order_relaxed);
            if (err_idx < 10) {
                std::cerr << "DISCREPANCY at index " << i
                          << ": Stored=" << static_cast<int>(stored_val)
                          << ", Computed=" << static_cast<int>(computed_val) << "\n";
            }
        }
    }

    uint64_t err_count = errors.load(std::memory_order_relaxed);
    if (err_count == 0) {
        std::cout << "[VERIFICATION SUCCESS] Layer " << static_cast<int>(layer_M)
                  << " is 100% self-consistent.\n";
    } else {
        std::cerr << "[VERIFICATION FAILURE] Found " << err_count
                  << " errors in Layer " << static_cast<int>(layer_M) << "\n";
    }
}

bool RetrogradeSolver::load_layer_from_monoliths(const std::string& out_dir) {
    std::string win_file = out_dir + "/layer" + std::to_string(layer_M) + "_win.bin";
    std::string draw_file = out_dir + "/layer" + std::to_string(layer_M) + "_draw.bin";

    std::ifstream w_in(win_file, std::ios::binary | std::ios::ate);
    std::ifstream d_in(draw_file, std::ios::binary | std::ios::ate);
    if (!w_in.is_open() || !d_in.is_open()) {
        std::cout << "[INFO] Monolith files not found for Layer " << static_cast<int>(layer_M)
                  << ". Attempting to load from micro-layer pair files..." << std::endl;
        
        int min_K = StateIndex::GetMinK(layer_M);
        int k_count = StateIndex::GetKCount(layer_M);
        int R = 50 - layer_M;
        uint64_t b_count = StateIndex::nCr(R + 9, 9);
        uint64_t b_bytes = (b_count + 7) / 8;

        std::unordered_map<std::string, std::pair<std::string, size_t>> comp_info;
        std::ifstream map_in("layers/compressed/compression_map.txt");
        if (!map_in.is_open()) map_in.open("layers/compression_map.txt");
        if (map_in.is_open()) {
            std::string line;
            while (std::getline(map_in, line)) {
                if (line.empty() || line[0] == '#') continue;
                std::stringstream ss(line);
                uint16_t k1, k2;
                std::string db_type, comp_str;
                size_t block_size;
                if (ss >> k1 >> k2 >> db_type >> comp_str >> block_size) {
                    std::string key = std::to_string(k1) + "_" + std::to_string(k2) + "_" + db_type;
                    comp_info[key] = {comp_str, block_size};
                }
            }
        }

        for (int k_idx = 0; k_idx < k_count; ++k_idx) {
            uint16_t k1 = min_K + k_idx * 2;
            uint16_t k2 = layer_M - k1;

            std::vector<uint8_t> win_bits(b_bytes, 0);
            std::vector<uint8_t> draw_bits(b_bytes, 0);

            for (const std::string& type : {"win", "draw"}) {
                std::string base_name = "layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_" + type;
                std::string raw_path = out_dir + "/" + base_name + ".raw";
                std::string bin_path = out_dir + "/compressed/" + base_name + ".bin";
                if (!std::filesystem::exists(bin_path)) bin_path = out_dir + "/" + base_name + ".bin";

                std::vector<uint8_t> data;
                std::ifstream raw_in(raw_path, std::ios::binary | std::ios::ate);
                if (raw_in.is_open()) {
                    size_t sz = raw_in.tellg();
                    raw_in.seekg(0, std::ios::beg);
                    data.resize(sz);
                    raw_in.read(reinterpret_cast<char*>(data.data()), sz);
                } else {
                    std::string key = std::to_string(k1) + "_" + std::to_string(k2) + "_" + type;
                    std::string comp_str = "ZSTD";
                    size_t block_size = 33554432;
                    if (comp_info.find(key) != comp_info.end()) {
                        comp_str = comp_info[key].first;
                        block_size = comp_info[key].second;
                    }
                    size_t bytes_per_block = block_size / 8;
                    data = Compressor::DecompressMicroLayer(bin_path, comp_str, bytes_per_block, b_bytes);
                }

                if (data.size() < b_bytes) {
                    std::cerr << "ERROR: Failed to load pair file for k1=" << k1 << ", k2=" << k2 << ", type=" << type << std::endl;
                    return false;
                }

                if (type == "win") win_bits = std::move(data);
                else draw_bits = std::move(data);
            }

            uint64_t base_idx = k_idx * b_count;
            for (uint64_t j = 0; j < b_count; ++j) {
                uint64_t i = base_idx + j;
                bool is_win = (win_bits[j / 8] >> (j % 8)) & 1;
                bool is_draw = (draw_bits[j / 8] >> (j % 8)) & 1;
                if (is_draw) WriteState2Bit(i, GameValue::DRAW);
                else if (is_win) WriteState2Bit(i, GameValue::WIN);
                else WriteState2Bit(i, GameValue::LOSS);
            }
        }
        std::cout << "[INFO] Successfully loaded all micro-layers for M = " << static_cast<int>(layer_M) << std::endl;
        return true;
    }

    size_t w_size = static_cast<size_t>(w_in.tellg());
    size_t d_size = static_cast<size_t>(d_in.tellg());
    w_in.seekg(0, std::ios::beg);
    d_in.seekg(0, std::ios::beg);

    std::vector<uint8_t> win_bits(w_size, 0);
    std::vector<uint8_t> draw_bits(d_size, 0);
    w_in.read(reinterpret_cast<char*>(win_bits.data()), static_cast<std::streamsize>(w_size));
    d_in.read(reinterpret_cast<char*>(draw_bits.data()), static_cast<std::streamsize>(d_size));
    if (!w_in || !d_in) return false;

    int min_K = StateIndex::GetMinK(layer_M);
    int k_count = StateIndex::GetKCount(layer_M);
    int R = 50 - layer_M;
    uint64_t b_count = StateIndex::nCr(R + 9, 9);
    uint64_t b_bytes = (b_count + 7) / 8;

    for (int k_idx = 0; k_idx < k_count; ++k_idx) {
        uint64_t base_idx = k_idx * b_count;
        uint64_t byte_offset = k_idx * b_bytes;
        for (uint64_t j = 0; j < b_count; ++j) {
            uint64_t i = base_idx + j;
            bool is_win = (win_bits[byte_offset + j / 8] >> (j % 8)) & 1;
            bool is_draw = (draw_bits[byte_offset + j / 8] >> (j % 8)) & 1;
            if (is_draw) WriteState2Bit(i, GameValue::DRAW);
            else if (is_win) WriteState2Bit(i, GameValue::WIN);
            else WriteState2Bit(i, GameValue::LOSS);
        }
    }
    return true;
}

void RetrogradeSolver::finalize_draws() {
    uint64_t draw_count = 0;
    #pragma omp parallel for reduction(+:draw_count)
    for (uint64_t i = 0; i < num_states; ++i) {
        if (ReadState2Bit(i) == GameValue::UNKNOWN) {
            WriteState2Bit(i, GameValue::DRAW);
            draw_count++;
        }
    }
    std::cout << "[INFO] Iteration complete. Detected " << draw_count << " loop-based Draws." << std::endl;
}

void RetrogradeSolver::write_raw_monoliths(const std::string& out_dir) {
    std::filesystem::create_directories(out_dir);

    std::string win_file = out_dir + "/layer" + std::to_string(layer_M) + "_win.bin";
    std::string draw_file = out_dir + "/layer" + std::to_string(layer_M) + "_draw.bin";

    int min_K = StateIndex::GetMinK(layer_M);
    int k_count = StateIndex::GetKCount(layer_M);
    int R = 50 - layer_M;
    uint64_t b_count = StateIndex::nCr(R + 9, 9);
    uint64_t b_bytes = (b_count + 7) / 8;

    uint64_t total_bytes = k_count * b_bytes;
    std::vector<uint8_t> win_bits(total_bytes, 0);
    std::vector<uint8_t> draw_bits(total_bytes, 0);

    #pragma omp parallel for
    for (int k_idx = 0; k_idx < k_count; ++k_idx) {
        uint64_t base_idx = k_idx * b_count;
        uint64_t byte_offset = k_idx * b_bytes;
        for (uint64_t j = 0; j < b_count; ++j) {
            uint64_t i = base_idx + j;
            uint8_t val = static_cast<uint8_t>(ReadState2Bit(i));
            if (val == static_cast<uint8_t>(GameValue::WIN)) win_bits[byte_offset + j / 8] |= (1 << (j % 8));
            else if (val == static_cast<uint8_t>(GameValue::DRAW)) draw_bits[byte_offset + j / 8] |= (1 << (j % 8));
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
