#include "Splitter.h"
#include "StateIndex.h"
#include <fstream>
#include <iostream>
#include <filesystem>

namespace Bestemshe {

void Splitter::SplitMonolith(uint8_t M, const std::string& input_dir, const std::string& output_dir) {
    std::string win_monolith = input_dir + "/layer" + std::to_string(M) + "_win.bin";
    std::string draw_monolith = input_dir + "/layer" + std::to_string(M) + "_draw.bin";

    std::ifstream win_f(win_monolith, std::ios::binary);
    std::ifstream draw_f(draw_monolith, std::ios::binary);

    if (!win_f || !draw_f) {
        std::cerr << "FAIL: Monolith source files not found." << std::endl;
        return;
    }

    std::filesystem::create_directories(output_dir);

    int min_K = StateIndex::GetMinK(M);
    int k_count = StateIndex::GetKCount(M);
    int R = 50 - M;
    uint64_t b_count = StateIndex::nCr(R + 9, 9);
    uint64_t b_bytes = (b_count + 7) / 8; // Pack bits into bytes for saving

    std::vector<uint8_t> buffer(b_bytes);

    for (int k_idx = 0; k_idx < k_count; ++k_idx) {
        uint16_t k1 = min_K + k_idx * 2;
        uint16_t k2 = M - k1;

        std::string win_out_name = output_dir + "/layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_win.raw";
        std::string draw_out_name = output_dir + "/layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_draw.raw";

        std::ofstream win_out(win_out_name, std::ios::binary);
        std::ofstream draw_out(draw_out_name, std::ios::binary);

        // Read specific segment for this micro-layer from the raw monolith files
        win_f.read(reinterpret_cast<char*>(buffer.data()), b_bytes);
        win_out.write(reinterpret_cast<const char*>(buffer.data()), b_bytes);

        draw_f.read(reinterpret_cast<char*>(buffer.data()), b_bytes);
        draw_out.write(reinterpret_cast<const char*>(buffer.data()), b_bytes);
    }
}

} // namespace Bestemshe