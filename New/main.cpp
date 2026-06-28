#include "StateIndex.h"
#include "Solver.h"
#include "Compressor.h"
#include "Inference.h"
#include <iostream>
#include <fstream> 
#include <string>
#include <filesystem>
#include <chrono>

using namespace Bestemshe;

void PrintUsage() {
    std::cout << "========================================================\n"
              << "   BESTEMSHE HPC ENGINE (God Algorithm / ZSTD Edition)  \n"
              << "========================================================\n"
              << "Usage:\n"
              << "  ./bestemshe --solve-pair <M> <K1> <K2>\n"
              << "  ./bestemshe --verify-pair <M> <K1> <K2>\n"
              << "  ./bestemshe --compress <input.raw> <output.bin>\n"
              << "  ./bestemshe --decompress <input.bin> <output.raw> <expected_bytes>\n"
              << "  ./bestemshe --root\n"
              << "========================================================\n";
}

int main(int argc, char* argv[]) {
    StateIndex::InitCombinatorics();

    if (argc < 2) {
        PrintUsage();
        return 1;
    }

    std::string mode = argv[1];

    if (mode == "--solve-pair" && argc == 5) {
        uint8_t M = std::stoi(argv[2]);
        uint16_t K1 = std::stoi(argv[3]);
        uint16_t K2 = std::stoi(argv[4]);
        std::cout << "[RUNNING] Solving Pair (" << K1 << "," << K2 << ") in Layer M = " << static_cast<int>(M) << "...\n";
        
        InferenceEngine db;
        RetrogradeSolver solver(M, &db);
        solver.solve_pair_lock_free(K1, K2);
    }
    else if (mode == "--verify-pair" && argc == 5) {
        uint8_t M = std::stoi(argv[2]);
        uint16_t K1 = std::stoi(argv[3]);
        uint16_t K2 = std::stoi(argv[4]);
        std::cout << "[RUNNING] Verifying Pair (" << K1 << "," << K2 << ") in Layer M = " << static_cast<int>(M) << "...\n";
        
        InferenceEngine db;
        RetrogradeSolver solver(M, &db);
        solver.verify_pair_consistency(K1, K2);
    }
    else if (mode == "--compress" && argc == 4) {
        std::string in_raw = argv[2];
        std::string out_bin = argv[3];
        std::cout << "[RUNNING] Compressing " << in_raw << " -> " << out_bin << " (ZSTD L19)...\n";
        Compressor::CompressMicroLayer(in_raw, out_bin); // Defaults to 32MB blocks
    } 
    else if (mode == "--decompress" && argc == 5) {
        std::string in_bin = argv[2];
        std::string out_raw = argv[3];
        size_t expected_bytes = std::stoull(argv[4]);
        std::cout << "[RUNNING] Decompressing " << in_bin << " -> " << out_raw << "...\n";
        
        // 33554432 bits = 4194304 bytes per block
        std::vector<uint8_t> raw = Compressor::DecompressMicroLayer(in_bin, 4194304, expected_bytes);
        if (!raw.empty()) {
            std::ofstream out(out_raw, std::ios::binary);
            out.write(reinterpret_cast<const char*>(raw.data()), raw.size());
            std::cout << "[SUCCESS] Decompressed.\n";
        }
    }
    else if (mode == "--root" && argc == 2) {
        std::cout << "========================================================\n"
                  << "   BESTEMSHE GAME-THEORETIC SOLUTION FINDER             \n"
                  << "========================================================\n";
        
        // Define the exact starting board of Bestemshe
        State root;
        root.M = 0; root.K_self = 0; root.K_opp = 0;
        for (int i = 0; i < 10; ++i) root.board[i] = 5;

        uint64_t root_idx = StateIndex::IndexState(root);
        
        InferenceEngine db;
        auto t_start = std::chrono::high_resolution_clock::now();
        GameValue result = db.query_state(0, 0, root_idx);
        auto t_end = std::chrono::high_resolution_clock::now();

        std::chrono::duration<double> d_query = t_end - t_start;

        std::cout << "Result for First Player (Player 1): ";
        if (result == GameValue::WIN)       std::cout << "\033[1;32mWIN (P1 forces a win)\033[0m\n";
        else if (result == GameValue::LOSS) std::cout << "\033[1;31mLOSS (P2 forces a win)\033[0m\n";
        else if (result == GameValue::DRAW) std::cout << "\033[1;33mDRAW (Perfect play is a draw)\033[0m\n";
        else                                std::cout << "\033[1;31mUNKNOWN (Error: Layer 0 not fully solved/loaded!)\033[0m\n";
        
        std::cout << "--------------------------------------------------------\n";
        std::cout << "Root Query Execution Time: " << d_query.count() << " seconds\n";
        std::cout << "========================================================\n";
    }
    else {
        PrintUsage();
        return 1;
    }

    return 0;
}