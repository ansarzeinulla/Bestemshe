#include "StateIndex.h"
#include "Solver.h"
#include "Splitter.h"
#include "Compressor.h"
#include <iostream>
#include <string>


using namespace Bestemshe;

void PrintUsage() {
    std::cout << "Bestemshe Solved-Engine CLI Pipeline Tool\n"
              << "Usage:\n"
              << "  ./bestemshe --solve <M> <manifest_path>\n"
              << "  ./bestemshe --solve-pair <M> <K1> <K2> <manifest_path>   (solves only the given symmetric pair)\n"
              << "  ./bestemshe --split <M> <input_dir> <output_dir>\n"
              << "  ./bestemshe --compress <input_raw> <output_bin> <algo(LZ4/RLE)> <block_size>\n"
              << "  ./bestemshe --decompress <input_bin> <output_raw> <algo(LZ4/RLE/ZSTD)> <block_size> <expected_raw_size>\n"
              << "  ./bestemshe --verify <M>\n"
              << "  ./bestemshe --selftest <M>   (bijection + board-odometer check; use small high-M layers)\n"
              << "  ./bestemshe --inference <manifest_path> <k1> <k2> <state_index>\n"
              << "  ./bestemshe --solveBegin <k1_k2_filepath>   (expands variations and routes captures to higher files)\n";
}

// Exhaustively validates, for layer M, that:
//   (1) IndexState/UnindexState are bijective and obey the sum/kazan invariants, and
//   (2) the StateIndex::AdvanceBoard odometer reproduces UnindexState(i) for every i.
// Intended for small (high-M) layers since it scans the entire layer.
static void AdvanceStateFull(State& s, int R) {
    if (!StateIndex::AdvanceBoard(s.board)) {
        s.K_self += 2;
        s.K_opp  -= 2;
        for (int p = 0; p < 9; ++p) s.board[p] = 0;
        s.board[9] = static_cast<uint8_t>(R);
    }
}

int RunSelfTest(int M) {
    int R = 50 - M;
    int min_K = StateIndex::GetMinK(static_cast<uint8_t>(M));
    int max_K = std::min(24, M);
    uint64_t size = StateIndex::GetLayerSize(static_cast<uint8_t>(M));
    std::cout << "[SELFTEST] M=" << M << " R=" << R << " states=" << size << "\n";

    uint64_t errors = 0;

    // 1) Bijection + invariants.
    for (uint64_t i = 0; i < size; ++i) {
        State s = StateIndex::UnindexState(i, static_cast<uint8_t>(M));
        uint64_t back = StateIndex::IndexState(s);
        int sum = 0;
        for (int p = 0; p < 10; ++p) sum += s.board[p];
        bool ok = (back == i)
               && (sum == R)
               && (s.K_self % 2 == 0)
               && (s.K_self >= min_K && s.K_self <= max_K)
               && (s.K_self + s.K_opp == M);
        if (!ok) {
            if (errors < 10)
                std::cerr << "  BIJECTION FAIL i=" << i << " back=" << back
                          << " sum=" << sum << " K_self=" << static_cast<int>(s.K_self) << "\n";
            ++errors;
        }
    }

    // 2) Odometer matches UnindexState across the whole layer (including K-dimension carries).
    if (size > 0) {
        State s = StateIndex::UnindexState(0, static_cast<uint8_t>(M));
        for (uint64_t i = 1; i < size; ++i) {
            AdvanceStateFull(s, R);
            State ref = StateIndex::UnindexState(i, static_cast<uint8_t>(M));
            bool match = (s.K_self == ref.K_self) && (s.K_opp == ref.K_opp);
            for (int p = 0; p < 10 && match; ++p)
                if (s.board[p] != ref.board[p]) match = false;
            if (!match) {
                if (errors < 20)
                    std::cerr << "  ODOMETER FAIL at i=" << i << "\n";
                ++errors;
            }
        }
    }

    if (errors == 0) {
        std::cout << "[SELFTEST PASS] M=" << M << ": bijection + odometer verified over "
                  << size << " states.\n";
        return 0;
    }
    std::cerr << "[SELFTEST FAIL] M=" << M << ": " << errors << " errors.\n";
    return 1;
}

//# Compress the wins database with LZ4
//./bestemshe --compress layers/layer_24_24_win.raw layers/layer_24_24_win.bin LZ4 4096

//# Compress the draws database with RLE
//./bestemshe --compress layers/layer_24_24_draw.raw layers/layer_24_24_draw.bin RLE 4096



// Add these helper functions in main.cpp before main()

#include <filesystem>
#include <sstream>

namespace fs = std::filesystem;

// Simulates a variation from the start board and tracks absolute Kazan scores
bool PlayOpeningVariation(const std::string& line, State& out_state, int& k_p1, int& k_p2) {
    // Initialize starting board: 50 stones total, 5 per pit, Kazan scores 0-0
    out_state.M = 0;
    out_state.K_self = 0;
    out_state.K_opp = 0;
    for (int p = 0; p < 10; ++p) {
        out_state.board[p] = 5;
    }

    k_p1 = 0;
    k_p2 = 0;

    for (size_t i = 0; i < line.length(); ++i) {
        int move_1based = line[i] - '0';
        if (move_1based < 1 || move_1based > 5) return false;
        int move_0based = move_1based - 1;

        if (out_state.board[move_0based] == 0) return false; // Illegal move

        State next_state;
        bool empties_opponent;
        ExecuteMoveAndFlip(out_state, move_0based, next_state, empties_opponent);

        // Track absolute Kazan scores based on which player made the move
        if (i % 2 == 0) {
            // Player 1's turn
            k_p1 = next_state.K_opp; // next_state.K_opp holds P1's score after flip
        } else {
            // Player 2's turn
            k_p2 = next_state.K_opp; // next_state.K_opp holds P2's score after flip
        }

        out_state = next_state;

        // If a player reaches terminal scores, stop simulating
        if (empties_opponent || k_p1 >= 26 || k_p2 >= 26) {
            if (k_p1 >= 26) k_p1 = 26;
            if (k_p2 >= 26) k_p2 = 26;
            break;
        }
    }
    return true;
}

void ProcessOpeningFile(const std::string& filepath) {
    fs::path p(filepath);
    std::string filename = p.filename().string(); // e.g. "0_0.txt"
    std::string dir = p.parent_path().string();
    if (dir.empty()) dir = ".";

    // Extract K1 and K2 from filename "K1_K2.txt"
    size_t underscore = filename.find('_');
    size_t dot = filename.find(".txt");
    if (underscore == std::string::npos || dot == std::string::npos) {
        std::cerr << "ERROR: File name must be in format K1_K2.txt (e.g. 0_0.txt)\n";
        return;
    }
    int K1 = std::stoi(filename.substr(0, underscore));
    int K2 = std::stoi(filename.substr(underscore + 1, dot - underscore - 1));

    std::ifstream in(filepath);
    if (!in.is_open()) {
        std::cerr << "ERROR: Could not open file: " << filepath << std::endl;
        return;
    }

    std::string next_filepath = filepath + ".next";
    std::ofstream next_out(next_filepath);

    std::string line;
    uint64_t expanded_nodes = 0;

    // We will append capturing variations dynamically to their respective files
    // Keep a map of open file streams to avoid reopening files repeatedly
    std::unordered_map<std::string, std::shared_ptr<std::ofstream>> open_streams;

    auto get_append_stream = [&](int k1, int k2) -> std::ofstream& {
        std::string key = std::to_string(k1) + "_" + std::to_string(k2);
        if (open_streams.find(key) == open_streams.end()) {
            std::string out_path = dir + "/" + key + ".txt";
            auto stream = std::make_shared<std::ofstream>(out_path, std::ios::app);
            open_streams[key] = stream;
        }
        return *(open_streams[key]);
    };

    while (std::getline(in, line)) {
        // Trim whitespace/carriage returns
        line.erase(std::remove_if(line.begin(), line.end(), ::isspace), line.end());
        if (line.empty() || line[0] == '#') continue;

        State s;
        int current_k1, current_k2;
        if (!PlayOpeningVariation(line, s, current_k1, current_k2)) continue;

        // Verify the variation actually matches this file's Kazan scores
        if (current_k1 != K1 || current_k2 != K2) {
            std::cerr << "WARNING: Variation " << line << " has Kazan scores (" 
                      << current_k1 << "," << current_k2 << ") but was inside " << filename << ". Routing it correctly...\n";
            get_append_stream(current_k1, current_k2) << line << "\n";
            continue;
        }

        // Try all 5 possible next moves
        for (int move = 0; move < 5; ++move) {
            if (s.board[move] == 0) continue;

            State next_s;
            bool empties_opponent;
            ExecuteMoveAndFlip(s, move, next_s, empties_opponent);

            // Calculate new absolute Kazan scores
            int new_k1 = K1;
            int new_k2 = K2;
            size_t ply = line.length();

            if (ply % 2 == 0) {
                // Player 1's turn
                new_k1 = next_s.K_opp;
            } else {
                // Player 2's turn
                new_k2 = next_s.K_opp;
            }

            if (empties_opponent || new_k1 >= 26 || new_k2 >= 26) {
                if (new_k1 >= 26) new_k1 = 26;
                if (new_k2 >= 26) new_k2 = 26;
            }

            std::string new_line = line + std::to_string(move + 1);
            expanded_nodes++;

            if (new_k1 == K1 && new_k2 == K2) {
                // No capture occurred: remains in the same file
                next_out << new_line << "\n";
            } else {
                // Capture occurred: drains out into a higher score file!
                get_append_stream(new_k1, new_k2) << new_line << "\n";
            }
        }
    }

    in.close();
    next_out.close();
    for (auto& pair : open_streams) {
        pair.second->close();
    }

    // Clean up original file and replace it with the remaining uncaptured variations
    fs::remove(filepath);
    if (fs::file_size(next_filepath) > 0) {
        fs::rename(next_filepath, filepath);
        std::cout << "[SUCCESS] Expanded file. Generated " << expanded_nodes 
                  << " moves. Non-capturing lines written back to " << filename << std::endl;
    } else {
        fs::remove(next_filepath);
        std::cout << "[SUCCESS] File fully drained! All lines transitioned to higher layers. " << filename << " deleted." << std::endl;
    }
}


int main(int argc, char* argv[]) {
    StateIndex::InitCombinatorics();

    if (argc < 2) {
        PrintUsage();
        return 1;
    }

    std::string mode = argv[1];

    if (mode == "--solve" && argc == 4) {
        uint8_t M = std::stoi(argv[2]);
        std::string manifest = argv[3];
        std::cout << "[RUNNING] Solving Layer M = " << static_cast<int>(M) << "...\n";
        InferenceEngine db(manifest);
        RetrogradeSolver solver(M, &db);
        solver.solve_layer_lock_free();
        solver.write_raw_monoliths("layers");
        std::cout << "[SUCCESS] Monoliths written for Layer M = " << static_cast<int>(M) << "\n";
    } 
    else if (mode == "--split" && argc == 5) {
        uint8_t M = std::stoi(argv[2]);
        std::string in_dir = argv[3];
        std::string out_dir = argv[4];
        Splitter::SplitMonolith(M, in_dir, out_dir);
    } 
    else if (mode == "--compress" && argc == 6) {
        std::string in_raw = argv[2];
        std::string out_bin = argv[3];
        std::string algo = argv[4];
        size_t block_size = std::stoull(argv[5]);
        Compressor::CompressMicroLayer(in_raw, out_bin, algo, block_size);
    } 
    else if (mode == "--decompress" && argc == 7) {
        std::string in_bin = argv[2];
        std::string out_raw = argv[3];
        std::string algo = argv[4];
        size_t block_size = std::stoull(argv[5]);
        size_t expected_raw_size = std::stoull(argv[6]);
        size_t bytes_per_block = block_size / 8;
        std::vector<uint8_t> raw = Compressor::DecompressMicroLayer(in_bin, algo, bytes_per_block, expected_raw_size);
        std::ofstream out(out_raw, std::ios::binary);
        out.write(reinterpret_cast<const char*>(raw.data()), raw.size());
    }
    else if (mode == "--verify" && argc == 3) {
        uint8_t M = std::stoi(argv[2]);
        std::cout << "[RUNNING] Verifying Layer M = " << static_cast<int>(M) << "...\n";
        std::string manifest = "layers/compressed/compression_map.txt";
        InferenceEngine db(manifest);
        RetrogradeSolver solver(M, &db);
        if (!solver.load_layer_from_monoliths("layers")) {
            std::cerr << "ERROR: Could not load layers/layer" << static_cast<int>(M)
                      << "_win.bin and _draw.bin. Run solve before verify, or keep the monoliths around.\n";
            return 1;
        }
        solver.verify_layer_consistency();
    }
    else if (mode == "--selftest" && argc == 3) {
        int M = std::stoi(argv[2]);
        return RunSelfTest(M);
    }
    else if (mode == "--inference" && argc == 6) {
        std::string manifest = argv[2];
        uint16_t k1 = std::stoi(argv[3]);
        uint16_t k2 = std::stoi(argv[4]);
        uint64_t idx = std::stoull(argv[5]);
        InferenceEngine engine(manifest);
        GameValue val = engine.query_state(k1, k2, idx);
        std::cout << "State Value: " << static_cast<int>(val) << std::endl;
    }
    else if (mode == "--solveBegin" && argc == 3) {
        std::string filepath = argv[2];
        std::cout << "[RUNNING] Expanding variations from file: " << filepath << "...\n";
        ProcessOpeningFile(filepath);
    }
    else if (mode == "--solve-pair" && argc == 6) {
        uint8_t M = std::stoi(argv[2]);
        uint16_t K1 = std::stoi(argv[3]);
        uint16_t K2 = std::stoi(argv[4]);
        std::string manifest = argv[5];
        std::cout << "[RUNNING] Solving Pair (" << K1 << "," << K2 << ") in Layer M = " << static_cast<int>(M) << "...\n";
        InferenceEngine db(manifest);
        RetrogradeSolver solver(M, &db);
        solver.solve_pair_lock_free(K1, K2);
    }
    else {
        PrintUsage();
        return 1;
    }

    return 0;
}
