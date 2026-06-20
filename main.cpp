#include <iostream>
#include <vector>
#include <string>
#include <filesystem>
#include <fstream>
#include <cstdint>
#include <algorithm>
#include <unordered_map>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

namespace fs = std::filesystem;

// ========================================================================
// 1. Math & Combinatorics (Stars and Bars)
// ========================================================================
uint64_t NCR_TABLE[60][10];

void InitCombinatorics() {
    for (int n = 0; n < 60; ++n) {
        for (int k = 0; k < 10; ++k) {
            if (k == 0 || n == k) NCR_TABLE[n][k] = 1;
            else if (k > n)       NCR_TABLE[n][k] = 0;
            else                  NCR_TABLE[n][k] = NCR_TABLE[n-1][k-1] + NCR_TABLE[n-1][k];
        }
    }
}

inline uint64_t nCr(int n, int k) {
    if (n < 0 || k < 0 || k > 10 || n < k) return 0;
    return NCR_TABLE[n][k];
}

// ========================================================================
// 2. Bit Arrays (Thread-Safe RAM & Zero-Copy Memory Map)
// ========================================================================

class RamBitArray {
    std::vector<uint8_t> data;
public:
    RamBitArray(uint64_t num_states, bool initial_value) {
        uint64_t bytes = (num_states + 7) / 8;
        data.resize(bytes, initial_value ? 0xFF : 0x00);
    }
    
    inline bool get_bit(uint64_t index) const {
        return (data[index / 8] >> (index % 8)) & 1;
    }
    
    inline void set_bit_atomic(uint64_t index, bool value) {
        uint64_t byte_idx = index / 8;
        uint8_t bit_mask = 1 << (index % 8);
        if (value) {
            #pragma omp atomic
            data[byte_idx] |= bit_mask;
        } else {
            #pragma omp atomic
            data[byte_idx] &= ~bit_mask;
        }
    }

    void save_to_file(const std::string& filepath) {
        std::ofstream file(filepath, std::ios::binary);
        file.write(reinterpret_cast<const char*>(data.data()), data.size());
    }
};

class MmapBitArray {
    uint8_t* data;
    size_t length;
    int fd;
public:
    MmapBitArray(const std::string& path, uint64_t num_states) {
        fd = open(path.c_str(), O_RDONLY);
        if (fd < 0) throw std::runtime_error("Failed to open " + path);
        length = (num_states + 7) / 8;
        data = (uint8_t*)mmap(nullptr, length, PROT_READ, MAP_PRIVATE, fd, 0);
        if (data == MAP_FAILED) throw std::runtime_error("mmap failed for " + path);
    }
    ~MmapBitArray() {
        if (data != MAP_FAILED) munmap(data, length);
        if (fd >= 0) close(fd);
    }
    inline bool get_bit(uint64_t index) const {
        return (data[index / 8] >> (index % 8)) & 1;
    }
};

// ========================================================================
// 3. Game Logic & Perfect Hashing
// ========================================================================
struct State {
    uint8_t M;
    uint8_t K_self;
    uint8_t K_opp;
    uint8_t board[10];
};

inline int GetMinK(uint8_t M) { return std::max(0, (int)M - 24); }
inline int GetKCount(uint8_t M) { return (std::min(24, (int)M) - GetMinK(M)) / 2 + 1; }

uint64_t GetLayerSize(uint8_t M) {
    uint64_t k_count = GetKCount(M);
    int R = 50 - M;
    uint64_t b_count = nCr(R + 9, 9);
    return k_count * b_count;
}

uint64_t IndexState(const State& s) {
    int min_K = GetMinK(s.M);
    uint64_t I_K = (s.K_self - min_K) / 2;

    uint64_t I_B = 0;
    int sum = 0;
    for (int i = 0; i < 9; ++i) {
        sum += s.board[i];
        int p_i = i + sum;
        I_B += nCr(p_i, i + 1);
    }

    int R = 50 - s.M;
    return I_K * nCr(R + 9, 9) + I_B;
}

State UnindexState(uint64_t index, uint8_t M) {
    State s;
    s.M = M;
    int R = 50 - M;
    uint64_t b_count = nCr(R + 9, 9);

    uint64_t I_K = index / b_count;
    uint64_t I_B = index % b_count;

    s.K_self = GetMinK(M) + I_K * 2;
    s.K_opp = M - s.K_self;

    int current_p = 0;
    for (int i = 8; i >= 0; --i) {
        int p = i;
        while (nCr(p + 1, i + 1) <= I_B) {
            p++;
        }
        I_B -= nCr(p, i + 1);
        if (i == 8) s.board[9] = R + 8 - p;
        else s.board[i + 1] = current_p - p - 1;
        current_p = p;
    }
    s.board[0] = current_p;
    return s;
}

// ========================================================================
// 4. Move Generation & Mechanics
// ========================================================================
struct MoveResult {
    State next_s;
    bool empties_opponent;
};

std::vector<MoveResult> GenerateMoves(const State& s) {
    std::vector<MoveResult> moves;
    moves.reserve(5);

    for (int i = 0; i < 5; ++i) {
        if (s.board[i] == 0) continue;
        
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

        // Even Parity Capture
        if (current_pit >= 5 && current_pit <= 9) {
            if (next_s.board[current_pit] % 2 == 0) {
                next_s.K_self += next_s.board[current_pit];
                next_s.M += next_s.board[current_pit];
                next_s.board[current_pit] = 0;
            }
        }

        // Check instant win (opponent side empty)
        bool opp_empty = true;
        for (int p = 5; p <= 9; ++p) {
            if (next_s.board[p] > 0) { opp_empty = false; break; }
        }

        // Flip board for opponent's perspective
        State flipped_s;
        flipped_s.M = next_s.M;
        flipped_s.K_self = next_s.K_opp;
        flipped_s.K_opp = next_s.K_self;
        for (int p = 0; p < 5; ++p) {
            flipped_s.board[p] = next_s.board[p + 5];
            flipped_s.board[p + 5] = next_s.board[p];
        }

        moves.push_back({flipped_s, opp_empty});
    }
    return moves;
}

// ========================================================================
// 5. Retrograde Analysis Engine
// ========================================================================
void SolveLayer(uint8_t M) {
    uint64_t num_states = GetLayerSize(M);
    std::cout << "Solving Layer " << (int)M << " (" << num_states << " states).\n";

    std::string layer_file = "layers/layer" + std::to_string(M) + ".bin";
    std::string known_file = "layers_known/layer" + std::to_string(M) + "_known.bin";

    RamBitArray current_layer(num_states, false);
    RamBitArray known_mask(num_states, false);

    // Map higher layers dynamically using mmap (Zero RAM consumption footprint)
    std::unordered_map<uint8_t, MmapBitArray*> higher_layers;
    for (uint8_t hM = M + 2; hM <= 48; hM += 2) {
        std::string hFile = "layers/layer" + std::to_string(hM) + ".bin";
        higher_layers[hM] = new MmapBitArray(hFile, GetLayerSize(hM));
    }

    bool changed = true;
    int pass = 1;

    while (changed) {
        bool local_changed = false;
        std::cout << "  Starting Value Iteration Pass " << pass << "...\n";

        // Multi-Threading the Retrograde search
        #pragma omp parallel for schedule(dynamic, 8192) reduction(|:local_changed)
        for (uint64_t i = 0; i < num_states; ++i) {
            if (known_mask.get_bit(i)) continue;

            State s = UnindexState(i, M);
            std::vector<MoveResult> moves = GenerateMoves(s);

            bool found_winning_move = false;
            bool all_moves_known_as_loss = true;

            for (const auto& move : moves) {
                if (move.empties_opponent) {
                    found_winning_move = true;
                    break;
                }
                if (move.next_s.K_opp >= 26) {
                    found_winning_move = true;
                    break;
                }

                bool is_next_known = false;
                bool is_next_win_for_opp = false; // 1 = Win for opponent (player to move next)

                if (move.next_s.M > M) {
                    is_next_known = true;
                    uint64_t next_idx = IndexState(move.next_s);
                    is_next_win_for_opp = higher_layers[move.next_s.M]->get_bit(next_idx);
                } else {
                    uint64_t next_idx = IndexState(move.next_s);
                    is_next_known = known_mask.get_bit(next_idx);
                    if (is_next_known) {
                        is_next_win_for_opp = current_layer.get_bit(next_idx);
                    }
                }

                if (is_next_known) {
                    if (!is_next_win_for_opp) {
                        // Found a move where the opponent loses! So we win!
                        found_winning_move = true;
                        break;
                    }
                } else {
                    all_moves_known_as_loss = false;
                }
            }

            if (found_winning_move) {
                current_layer.set_bit_atomic(i, true);  
                known_mask.set_bit_atomic(i, true);    
                local_changed = true;
            } else if (all_moves_known_as_loss) {
                current_layer.set_bit_atomic(i, false); 
                known_mask.set_bit_atomic(i, true);     
                local_changed = true;
            }
        }
        changed = local_changed;
        pass++;
    }

    // ========================================================================
    // 6. Best Practices: Exporting Unknown States / Infinite Loops
    // ========================================================================
    std::cout << "  Writing unresolved states to error.txt (if any)...\n";
    std::ofstream err_file("error.txt", std::ios::app);
    uint64_t unknown_count = 0;
    
    for (uint64_t i = 0; i < num_states; ++i) {
        if (!known_mask.get_bit(i)) {
            err_file << "Layer " << (int)M << " Index " << i << " unresolved (infinite loop / draw logic).\n";
            unknown_count++;
        }
    }
    err_file.close();

    if (unknown_count > 0) {
        std::cerr << "  WARNING: " << unknown_count << " states left unresolved! Appended to error.txt.\n";
        // NOTE: They naturally stay 0 (Loss) in current_layer per the draw logic rule.
    }

    // Finalize and clean memory
    current_layer.save_to_file(layer_file);
    for (auto& pair : higher_layers) delete pair.second;
    
    std::cout << "Layer " << (int)M << " completely saved to " << layer_file << "\n";
    fs::remove(known_file); // Ensure tmp is cleared
}

// ========================================================================
// 7. CLI & Validation entry
// ========================================================================
int main(int argc, char* argv[]) {
    if (argc < 3 || std::string(argv[1]) != "--level") {
        std::cerr << "Usage: ./solve --level <M>\n";
        return 1;
    }

    int M_input = std::stoi(argv[2]);
    if (M_input < 0 || M_input > 48 || M_input % 2 != 0) {
        std::cerr << "Error: M must be an even integer between 0 and 48.\n";
        return 1;
    }
    uint8_t M = static_cast<uint8_t>(M_input);

    InitCombinatorics();
    fs::create_directories("layers");
    fs::create_directories("layers_known");

    // File Validation: Ensure ALL upper layers exist
    for (uint8_t hM = M + 2; hM <= 48; hM += 2) {
        std::string expected = "layers/layer" + std::to_string(hM) + ".bin";
        if (!fs::exists(expected)) {
            std::cerr << "FATAL: Cannot solve layer " << (int)M << ". Missing dependency: " << expected << "\n";
            std::cerr << "Please run: ./solve --level " << (int)hM << " first.\n";
            return 1;
        }
    }

    SolveLayer(M);
    return 0;
}