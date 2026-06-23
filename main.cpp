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
              << "  ./bestemshe --inference <manifest_path> <k1> <k2> <state_index>\n";
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
        std::string manifest = "layers/compressed/compression_map.txt";
        std::cout << "[RUNNING] Verifying Layer M = " << static_cast<int>(M) << "...\n";
        InferenceEngine db(manifest);
        RetrogradeSolver solver(M, &db);
        solver.verify_layer_consistency();
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
