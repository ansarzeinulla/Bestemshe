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
              << "  ./bestemshe --split <M> <input_dir> <output_dir>\n"
              << "  ./bestemshe --compress <input_raw> <output_bin> <algo(LZ4/RLE)> <block_size>\n"
              << "  ./bestemshe --decompress <input_bin> <output_raw> <algo(LZ4/RLE/ZSTD)> <block_size> <expected_raw_size>\n"
              << "  ./bestemshe --verify <M>\n"
              << "  ./bestemshe --selftest <M>   (bijection + board-odometer check; use small high-M layers)\n"
              << "  ./bestemshe --inference <manifest_path> <k1> <k2> <state_index>\n";
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
    else {
        PrintUsage();
        return 1;
    }

    return 0;
}
