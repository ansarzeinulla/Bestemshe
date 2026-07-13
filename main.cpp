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
    }else if (mode == "--analyze") {
        State s;
        // Accept either a custom board, or default to the starting position
        if (argc == 14) {
            s.K_self = static_cast<uint8_t>(std::stoi(argv[2]));
            s.K_opp  = static_cast<uint8_t>(std::stoi(argv[3]));
            s.M      = s.K_self + s.K_opp;
            for (int i = 0; i < 10; ++i) s.board[i] = static_cast<uint8_t>(std::stoi(argv[4 + i]));
        } else if (argc == 2) {
            s.M = 0; s.K_self = 0; s.K_opp = 0;
            for (int i = 0; i < 10; ++i) s.board[i] = 5;
        } else {
            std::cout << "Usage: ./bestemshe --analyze  [OR]  ./bestemshe --analyze K1 K2 p0..p9\n";
            return 1;
        }

        InferenceEngine db;
        int ply = 0;

        while (true) {
            bool is_p1_turn = (ply % 2 == 0);
            std::string current_player = is_p1_turn ? "Player 1 (White)" : "Player 2 (Black)";

            // 1. Construct Absolute Board for Fixed Human Perspective
            uint8_t abs_board[10];
            int abs_k1, abs_k2;
            if (is_p1_turn) {
                for (int i = 0; i < 10; ++i) abs_board[i] = s.board[i];
                abs_k1 = s.K_self;
                abs_k2 = s.K_opp;
            } else {
                for (int i = 0; i < 5; ++i) {
                    abs_board[i] = s.board[i + 5];   // P1's pits are in 5-9 of canonical state
                    abs_board[i + 5] = s.board[i];   // P2's pits are in 0-4 of canonical state
                }
                abs_k1 = s.K_opp;
                abs_k2 = s.K_self;
            }

            std::cout << "\n========================================================\n"
                      << "   BESTEMSHE ORACLE: PLY " << ply << " | " << current_player << " to move\n"
                      << "========================================================\n";
                      
            std::cout << "                 [P2 Kazan (Black): " << abs_k2 << "]\n\n";
            std::cout << "        (9)   (8)   (7)   (6)   (5)    <- P2 Pits\n       ";
            for (int i = 9; i >= 5; --i) printf("[%2d]  ", (int)abs_board[i]);
            std::cout << "\n\n       ";
            for (int i = 0; i < 5; ++i) printf("[%2d]  ", (int)abs_board[i]);
            std::cout << "\n        (0)   (1)   (2)   (3)   (4)    <- P1 Pits\n\n";
            std::cout << "                 [P1 Kazan (White): " << abs_k1 << "]\n";
            std::cout << "--------------------------------------------------------\n";
            std::cout << "EVALUATING MOVES (1-0 = P1 Wins, 0-1 = P2 Wins)\n";

            int start_move = is_p1_turn ? 0 : 5;
            int end_move   = is_p1_turn ? 4 : 9;
            bool has_moves = false;

            for (int abs_move = start_move; abs_move <= end_move; ++abs_move) {
                int canonical_move = is_p1_turn ? abs_move : (abs_move - 5);

                if (s.board[canonical_move] == 0) {
                    std::cout << "Move " << abs_move << ": INVALID (Empty pit)\n";
                    continue;
                }
                has_moves = true;
                
                State next_s;
                bool empties;
                ExecuteMoveAndFlip(s, canonical_move, next_s, empties);
                
                std::string result_str;
                
                if (empties || next_s.K_opp >= 26) {
                    if (is_p1_turn) result_str = "\033[1;32m1-0 (P1 forces WIN - Immediate)\033[0m";
                    else            result_str = "\033[1;31m0-1 (P2 forces WIN - Immediate)\033[0m";
                } else {
                    uint64_t next_idx = StateIndex::IndexState(next_s);
                    GameValue val = db.query_state(next_s.M, next_s.K_opp, next_idx);
                    
                    if (val == GameValue::DRAW) {
                        result_str = "\033[1;33m0.5-0.5 (Forced DRAW)\033[0m";
                    } else if (val == GameValue::UNKNOWN) {
                        result_str = "\033[1;31mUNKNOWN (Error: Layer missing)\033[0m";
                    } else {
                        bool next_player_wins = (val == GameValue::WIN);
                        bool p1_wins = is_p1_turn ? !next_player_wins : next_player_wins;
                        
                        if (p1_wins) result_str = "\033[1;32m1-0 (P1 forces WIN)\033[0m";
                        else         result_str = "\033[1;31m0-1 (P2 forces WIN)\033[0m";
                    }
                }
                std::cout << "Move " << abs_move << ": " << result_str << "\n";
            }

            if (!has_moves) {
                std::cout << "\n*** No valid moves. Game Over. ***\n";
                break;
            }

            std::cout << "--------------------------------------------------------\n";
            int chosen_abs_move = -1;
            int chosen_canonical = -1;
            while (true) {
                std::cout << "Enter move (" << start_move << "-" << end_move << ") or 'q' to quit: ";
                std::string input;
                if (!(std::cin >> input) || input == "q") {
                    std::cout << "Exiting Oracle.\n";
                    return 0;
                }
                try {
                    chosen_abs_move = std::stoi(input);
                    if (chosen_abs_move >= start_move && chosen_abs_move <= end_move) {
                        chosen_canonical = is_p1_turn ? chosen_abs_move : (chosen_abs_move - 5);
                        if (s.board[chosen_canonical] > 0) break;
                    }
                } catch (...) {}
                std::cout << "Invalid move. Try again.\n";
            }

            // Execute chosen move and update canonical state
            bool empties;
            ExecuteMoveAndFlip(s, chosen_canonical, s, empties);

            if (empties || s.K_opp >= 26) {
                std::cout << "\n========================================================\n";
                std::cout << "*** GAME OVER: " << current_player << " Wins! ***\n";
                std::cout << "========================================================\n";
                break;
            }
            ply++;
        }
    }
    else {
        PrintUsage();
        return 1;
    }

    return 0;
}