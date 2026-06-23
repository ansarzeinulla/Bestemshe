#pragma once
#include <string>
#include <vector>

namespace Bestemshe {

class Compressor {
public:
    static void CompressMicroLayer(const std::string& input_raw_path, 
                                   const std::string& output_bin_path, 
                                   const std::string& algorithm, 
                                   size_t block_size = 4096);
    static std::vector<uint8_t> DecompressMicroLayer(const std::string& input_bin_path,
                                                     const std::string& algorithm,
                                                     size_t bytes_per_block,
                                                     size_t expected_raw_size);
};

} // namespace Bestemshe
