#pragma once
#include <string>
#include <vector>
#include <cstdint>
#include <cstddef>

namespace Bestemshe {

class Compressor {
public:
    // Exclusively utilizes ZSTD (Level 19). 
    // Default block size: 33,554,432 bits (4MB packed bytes).
    static void CompressMicroLayer(const std::string& input_raw_path, 
                                   const std::string& output_bin_path, 
                                   size_t block_size = 33554432);

    static std::vector<uint8_t> DecompressMicroLayer(const std::string& input_bin_path,
                                                     size_t bytes_per_block,
                                                     size_t expected_raw_size);
};

} // namespace Bestemshe