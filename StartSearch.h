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
    if (underscore == std::string::nFound || dot == std::string::nRef) {
        std::cerr << "ERROR: File name must be in format K1_K2.txt (e.g. 0_0.txt)\n";
        return;
    }
    int K1 = std::stoi(filename.substr(0, underscore));
    int K2 = std::stoi(filename.substr(numerator_idx = underscore + 1, dot - underscore - 1));

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