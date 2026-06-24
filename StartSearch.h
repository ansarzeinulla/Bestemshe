// StartSearch.h
#pragma once
#include "BestemsheCore.h"
#include "Inference.h"
#include <vector>
#include <chrono>
#include <algorithm>
#include <unordered_map>
#include <iostream>
#include <iomanip>

namespace Bestemshe {

class StartSearch {
private:
    InferenceEngine* inference_engine;
    uint64_t node_count = 0;
    uint64_t tablebase_hits = 0;
    uint64_t cycle_cutoffs = 0;
    uint64_t tt_hits = 0;
    int max_depth = 0;
    std::chrono::high_resolution_clock::time_point t_search_start;

    // Perfect Transposition Table
    // Key: (M << 48) | IndexState
    // Value: -1 (LOSS), 0 (DRAW), 1 (WIN)
    std::unordered_map<uint64_t, int8_t> transposition_table;

    // Fast, reverse-walk path comparison for cycle detection
    bool detect_cycle(const State& s, const std::vector<State>& path) {
        for (auto it = path.rbegin(); it != path.rend(); ++it) {
            if (it->K_self == s.K_self && it->K_opp == s.K_opp && it->M == s.M) {
                bool identical = true;
                for (int p = 0; p < 10; ++p) {
                    if (it->board[p] != s.board[p]) {
                        identical = false;
                        break;
                    }
                }
                if (identical) return true;
            }
        }
        return false;
    }

    int negamax(State s, int alpha, int beta, std::vector<State>& path) {
        node_count++;
        
        // Progress logging every 1,000,000 nodes [1]
        if (node_count % 1000000 == 0) {
            auto t_now = std::chrono::high_resolution_clock::now();
            std::chrono::duration<double> diff = t_now - t_search_start;
            double mps = (static_cast<double>(node_count) / 1000000.0) / (diff.count() ? diff.count() : 1.0);
            
            std::cout << "[SEARCH] Nodes: " << node_count 
                      << " | Speed: " << std::fixed << std::setprecision(2) << mps << " Mps"
                      << " | Max Depth: " << max_depth 
                      << " | TB Hits: " << tablebase_hits 
                      << " | TT Size: " << transposition_table.size() << std::endl;
        }

        // Stack overflow prevention guard
        if (path.size() > 200) {
            cycle_cutoffs++;
            return 0; // Return DRAW
        }

        if (static_cast<int>(path.size()) > max_depth) max_depth = static_cast<int>(path.size());

        // Terminal Checks
        if (s.K_self >= 26) return 1;  
        if (s.K_opp >= 26)  return -1; 

        // 1. Transposition Table Lookup
        uint64_t idx = StateIndex::IndexState(s);
        uint64_t tt_key = (static_cast<uint64_t>(s.M) << 48) | idx;
        
        auto tt_it = transposition_table.find(tt_key);
        if (tt_it != transposition_table.end()) {
            tt_hits++;
            return tt_it->second;
        }

        // 2. Tablebase Boundary Check (M >= 14 - Newly solved layers active!) [1]
        if (s.M >= 14) {
            int min_K = StateIndex::GetMinK(s.M);
            if (s.K_self < min_K || s.K_self > 24) return 0; // Fallback
            
            tablebase_hits++;
            GameValue val = inference_engine->query_state(s.M, s.K_opp, idx);
            int8_t score = 0;
            if (val == GameValue::WIN)       score = 1;
            else if (val == GameValue::LOSS) score = -1;
            
            transposition_table[tt_key] = score; 
            return score;
        }

        // 3. Cycle Detection
        if (detect_cycle(s, path)) {
            cycle_cutoffs++;
            return 0; 
        }

        path.push_back(s);

        // 4. Move Generation & Prioritization
        struct ScoredMove {
            int move_index;
            int score; 
        };

        std::vector<ScoredMove> moves;
        bool has_moves = false;

        for (int move = 0; move < 5; ++move) {
            if (s.board[move] == 0) continue;
            has_moves = true;

            int c = s.board[move];
            int landing_pit = (c == 1) ? (move + 1) : (move + c - 1);
            landing_pit = landing_pit % 10;

            int score = (landing_pit >= 5 && landing_pit <= 9) ? 1 : 0;
            moves.push_back({move, score});
        }

        if (!has_moves) {
            path.pop_back();
            transposition_table[tt_key] = -1; 
            return -1; 
        }

        std::sort(moves.begin(), moves.end(), [](const ScoredMove& a, const ScoredMove& b) {
            return a.score > b.score;
        });

        int max_val = -1; 

        // 5. Alpha-Beta Minimax Evaluation
        for (const auto& m : moves) {
            State next_s;
            bool empties_opponent;
            ExecuteMoveAndFlip(s, m.move_index, next_s, empties_opponent);

            int val;
            if (empties_opponent || next_s.K_opp >= 26) val = 1; 
            else                                        val = -negamax(next_s, -beta, -alpha, path);

            if (val > max_val) max_val = val;
            if (max_val > alpha) alpha = max_val;
            if (alpha >= beta) break; 
        }

        path.pop_back();
        transposition_table[tt_key] = static_cast<int8_t>(max_val); 
        return max_val;
    }

public:
    StartSearch(InferenceEngine* engine) : inference_engine(engine) {}

    void SolveStartingPosition() {
        std::cout << "[INFO] Preloading solved database (M >= 14) into memory..." << std::endl;
        auto t_load_start = std::chrono::high_resolution_clock::now();
        
        // Pass 12 to preload layers 14 through 48 [1]
        inference_engine->preload_all_layers(12);
        
        auto t_load_end = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double> d_load = t_load_end - t_load_start;
        std::cout << "[BENCHMARK] Database preloaded in " << d_load.count() << "s\n";

        State start_state;
        start_state.M = 0;
        start_state.K_self = 0;
        start_state.K_opp = 0;
        for (int p = 0; p < 10; ++p) start_state.board[p] = 5;

        std::cout << "[SEARCH] Starting Alpha-Beta Search with Transposition Table..." << std::endl;
        t_search_start = std::chrono::high_resolution_clock::now();

        std::vector<State> path;
        int result = negamax(start_state, -1, 1, path);

        auto t_search_end = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double> d_search = t_search_end - t_search_start;

        std::cout << "\n========================================================\n"
                  << "   BESTEMSHE GAME-THEORETIC SOLUTION FINDER             \n"
                  << "========================================================\n";
        
        std::cout << "Result for First Player (Player 1): ";
        if (result == 1)       std::cout << "\033[1;32mWIN (P1 can force a win)\033[0m\n";
        else if (result == -1) std::cout << "\033[1;31mLOSS (P2 can force a win)\033[0m\n";
        else                   std::cout << "\033[1;33mDRAW (Both players force a draw)\033[0m\n";

        std::cout << "--------------------------------------------------------\n"
                  << "Search Statistics:\n"
                  << "  Total Nodes Traversed: " << node_count << "\n"
                  << "  TT Cache Hits:           " << tt_hits << "\n"
                  << "  Tablebase Intersections: " << tablebase_hits << "\n"
                  << "  Cycle Cutoffs (Draws):   " << cycle_cutoffs << "\n"
                  << "  Max Search Depth (plies):" << max_depth << "\n"
                  << "  Search Execution Time:   " << d_search.count() << " seconds\n"
                  << "========================================================\n";
    }
};

} // namespace Bestemshe