#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <functional>
#include <unordered_map>
#include <string>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace fs = std::filesystem;

uint64_t NCR_TABLE[60][10];

void InitCombinatorics() {
    for (int n = 0; n < 60; ++n) {
        for (int k = 0; k < 10; ++k) {
            if (k == 0 || n == k) NCR_TABLE[n][k] = 1;
            else if (k > n) NCR_TABLE[n][k] = 0;
            else NCR_TABLE[n][k] = NCR_TABLE[n - 1][k - 1] + NCR_TABLE[n - 1][k];
        }
    }
}

inline uint64_t nCr(int n, int k) {
    if (n < 0 || k < 0 || k > 10 || n < k) return 0;
    return NCR_TABLE[n][k];
}

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
    return k_count * nCr(R + 9, 9);
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
    State s{};
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
        while (nCr(p + 1, i + 1) <= I_B) ++p;
        I_B -= nCr(p, i + 1);
        if (i == 8) s.board[9] = R + 8 - p;
        else s.board[i + 1] = current_p - p - 1;
        current_p = p;
    }
    s.board[0] = current_p;
    return s;
}

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

        if (current_pit >= 5 && current_pit <= 9) {
            if (next_s.board[current_pit] % 2 == 0) {
                next_s.K_self += next_s.board[current_pit];
                next_s.M += next_s.board[current_pit];
                next_s.board[current_pit] = 0;
            }
        }

        bool opp_empty = true;
        for (int p = 5; p <= 9; ++p) {
            if (next_s.board[p] > 0) {
                opp_empty = false;
                break;
            }
        }

        State flipped_s{};
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

struct LayerFiles {
    MmapBitArray* win;
    MmapBitArray* draw;
};

static void PrintState(const State& s) {
    std::cout << "M=" << int(s.M)
              << " K_self=" << int(s.K_self)
              << " K_opp=" << int(s.K_opp) << '\n';
    std::cout << "self side: ";
    for (int i = 0; i < 5; ++i) std::cout << int(s.board[i]) << (i < 4 ? ' ' : '\n');
    std::cout << "opp  side: ";
    for (int i = 5; i < 10; ++i) std::cout << int(s.board[i]) << (i < 9 ? ' ' : '\n');
}

static std::string StateKey(const State& s) {
    std::string key;
    key.reserve(13);
    key.push_back(char(s.M));
    key.push_back(char(s.K_self));
    key.push_back(char(s.K_opp));
    for (int i = 0; i < 10; ++i) key.push_back(char(s.board[i]));
    return key;
}

static bool LoadLayerFiles(uint8_t M, std::unordered_map<uint8_t, LayerFiles>& layers) {
    for (uint8_t hM = M; hM <= 48; hM += 2) {
        std::string win_file = "layers/layer" + std::to_string(hM) + ".bin";
        std::string draw_file = "layers/layer" + std::to_string(hM) + "_draw.bin";
        if (!fs::exists(win_file) || !fs::exists(draw_file)) return false;
        layers[hM] = {
            new MmapBitArray(win_file, GetLayerSize(hM)),
            new MmapBitArray(draw_file, GetLayerSize(hM))
        };
    }
    return true;
}

static bool IsDrawState(const State& s, const std::unordered_map<uint8_t, LayerFiles>& layers) {
    auto it = layers.find(s.M);
    if (it == layers.end()) return false;
    uint64_t idx = IndexState(s);
    return it->second.draw->get_bit(idx);
}

static std::vector<State> FindCycleFromStart(
    const State& start,
    const std::unordered_map<uint8_t, LayerFiles>& layers,
    int max_depth = 64
) {
    std::vector<State> path;
    std::unordered_map<std::string, bool> on_path;

    std::function<bool(const State&, int)> dfs = [&](const State& cur, int depth) -> bool {
        path.push_back(cur);
        on_path[StateKey(cur)] = true;

        if (depth > 0 && StateKey(cur) == StateKey(start)) {
            return true;
        }
        if (depth >= max_depth) {
            on_path.erase(StateKey(cur));
            path.pop_back();
            return false;
        }

        auto moves = GenerateMoves(cur);
        for (const auto& move : moves) {
            const State& nxt = move.next_s;
            if (!IsDrawState(nxt, layers)) continue;

            std::string key = StateKey(nxt);
            if (key != StateKey(start) && on_path.count(key)) continue;

            if (dfs(nxt, depth + 1)) return true;
        }

        on_path.erase(StateKey(cur));
        path.pop_back();
        return false;
    };

    if (dfs(start, 0) && path.size() > 1 && StateKey(path.front()) == StateKey(path.back())) {
        return path;
    }
    return {};
}

int main(int argc, char* argv[]) {
    if (argc != 3) {
        std::cerr << "Usage: ./board <layer> <loop_order>\n";
        return 1;
    }

    int layer_in = std::stoi(argv[1]);
    int loop_order = std::stoi(argv[2]);
    if (layer_in < 0 || layer_in > 48 || layer_in % 2 != 0 || loop_order <= 0) {
        std::cerr << "Error: layer must be even in [0,48] and loop_order must be positive.\n";
        return 1;
    }

    InitCombinatorics();

    std::unordered_map<uint8_t, LayerFiles> layers;
    if (!LoadLayerFiles(static_cast<uint8_t>(layer_in), layers)) {
        std::cerr << "Missing layer files. Make sure both layerM.bin and layerM_draw.bin exist for M >= " << layer_in << ".\n";
        return 1;
    }

    uint8_t M = static_cast<uint8_t>(layer_in);
    uint64_t num_states = GetLayerSize(M);
    uint64_t found = 0;

    for (uint64_t i = 0; i < num_states; ++i) {
        State start = UnindexState(i, M);
        if (!IsDrawState(start, layers)) continue;

        auto cycle = FindCycleFromStart(start, layers);
        if (cycle.empty()) continue;

        ++found;
        if (found != static_cast<uint64_t>(loop_order)) continue;

        std::cout << "Loop #" << loop_order << " in layer " << layer_in << " starting at index " << i << "\n";
        std::cout << "Cycle length: " << (cycle.size() - 1) << "\n\n";
        for (size_t step = 0; step < cycle.size(); ++step) {
            std::cout << "Step " << step << ":\n";
            PrintState(cycle[step]);
            if (step + 1 < cycle.size()) std::cout << '\n';
        }
        if (StateKey(cycle.front()) == StateKey(cycle.back())) {
            std::cout << "\nReturned to the original position.\n";
        }

        for (auto& [_, lf] : layers) {
            delete lf.win;
            delete lf.draw;
        }
        return 0;
    }

    std::cerr << "Could not find loop order " << loop_order << " in layer " << layer_in << ".\n";
    for (auto& [_, lf] : layers) {
        delete lf.win;
        delete lf.draw;
    }
    return 1;
}
