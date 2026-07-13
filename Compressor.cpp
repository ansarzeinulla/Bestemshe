#include "Compressor.h"
#include <fstream>
#include <iostream>
#include <limits>
#include <zstd.h> // Link -lzstd

namespace Bestemshe {

// -----------------------------------------------------------------------------
// Core Compression Hardware
// -----------------------------------------------------------------------------
static std::vector<uint8_t> CompressBlockZSTD(const uint8_t* src, size_t src_size) {
    size_t bound = ZSTD_compressBound(src_size);
    std::vector<uint8_t> comp_buf(bound);
    
    // Level 19 is maximum compression. Decompression speed remains O(1) regarding level.
    size_t comp_size = ZSTD_compress(
        comp_buf.data(), bound,
        src, src_size,
        19 
    );
    
    if (ZSTD_isError(comp_size)) {
        std::cerr << "[FATAL] ZSTD Compression failed: " << ZSTD_getErrorName(comp_size) << std::endl;
        return {};
    }
    comp_buf.resize(comp_size);
    return comp_buf;
}

static bool DecompressBlockZSTD(const uint8_t* src, size_t src_size, uint8_t* dest, size_t dest_size) {
    size_t d_size = ZSTD_decompress(dest, dest_size, src, src_size);
    if (ZSTD_isError(d_size)) {
        std::cerr << "[FATAL] ZSTD Decompression failed: " << ZSTD_getErrorName(d_size) << std::endl;
        return false;
    }
    return true;
}

// -----------------------------------------------------------------------------
// Blocked I/O Pipeline
// -----------------------------------------------------------------------------
void Compressor::CompressMicroLayer(const std::string& input_raw_path, 
                                    const std::string& output_bin_path, 
                                    size_t block_size) {
    std::ifstream in(input_raw_path, std::ios::binary | std::ios::ate);
    if (!in.is_open()) {
        std::cerr << "[ERROR] Could not open raw input: " << input_raw_path << "\n";
        return;
    }

    size_t total_size = in.tellg();
    in.seekg(0, std::ios::beg);
    std::vector<uint8_t> raw_data(total_size);
    in.read(reinterpret_cast<char*>(raw_data.data()), total_size);
    in.close();

    size_t bytes_per_block = block_size / 8;
    if (bytes_per_block == 0) {
        std::cerr << "[FATAL] block_size " << block_size << " too small (< 8 bits).\n";
        return;
    }
    size_t num_blocks = (raw_data.size() + bytes_per_block - 1) / bytes_per_block;

    std::vector<std::vector<uint8_t>> compressed_blocks(num_blocks);
    std::vector<uint32_t> block_offsets(num_blocks + 1, 0);

    for (size_t b = 0; b < num_blocks; ++b) {
        size_t start_idx = b * bytes_per_block;
        size_t size = std::min(bytes_per_block, raw_data.size() - start_idx);

        std::vector<uint8_t> block_tmp(bytes_per_block, 0); // zero padded for alignment
        std::copy(raw_data.begin() + start_idx, raw_data.begin() + start_idx + size, block_tmp.begin());

        compressed_blocks[b] = CompressBlockZSTD(block_tmp.data(), bytes_per_block);
    }

    // Write architecture: [Num Blocks] [Offsets Header Table] [Compressed Payload]
    std::ofstream out(output_bin_path, std::ios::binary);
    uint32_t num_blocks_u32 = static_cast<uint32_t>(num_blocks);
    out.write(reinterpret_cast<const char*>(&num_blocks_u32), sizeof(uint32_t));

    uint32_t header_bytes_size = sizeof(uint32_t) + (num_blocks_u32 + 1) * sizeof(uint32_t);
    uint64_t current_offset = header_bytes_size;
    
    for (size_t b = 0; b < num_blocks; ++b) {
        block_offsets[b] = static_cast<uint32_t>(current_offset);
        current_offset += compressed_blocks[b].size();
    }
    
    // Bounds check to guarantee file fits in uint32 offset layout
    if (current_offset > std::numeric_limits<uint32_t>::max()) {
        std::cerr << "[FATAL] Compressed file exceeds 4GB uint32 offset limit: " << output_bin_path << "\n";
        out.close();
        return;
    }
    block_offsets[num_blocks] = static_cast<uint32_t>(current_offset);

    out.write(reinterpret_cast<const char*>(block_offsets.data()), block_offsets.size() * sizeof(uint32_t));
    for (size_t b = 0; b < num_blocks; ++b) {
        out.write(reinterpret_cast<const char*>(compressed_blocks[b].data()), compressed_blocks[b].size());
    }
    out.close();
}

std::vector<uint8_t> Compressor::DecompressMicroLayer(const std::string& input_bin_path,
                                                      size_t bytes_per_block,
                                                      size_t expected_raw_size) {
    std::ifstream in(input_bin_path, std::ios::binary);
    if (!in.is_open()) {
        std::cerr << "[ERROR] Could not open compressed input: " << input_bin_path << "\n";
        return {};
    }
    if (bytes_per_block == 0) {
        std::cerr << "[FATAL] bytes_per_block == 0\n";
        return {};
    }

    uint32_t num_blocks = 0;
    in.read(reinterpret_cast<char*>(&num_blocks), sizeof(uint32_t));
    if (!in) return {};

    // Prevent malicious or corrupt header OOM attacks
    size_t max_plausible_blocks = (expected_raw_size / bytes_per_block) + 2;
    if (num_blocks == 0 || num_blocks > max_plausible_blocks) {
        std::cerr << "[FATAL] Implausible block count " << num_blocks << " in " << input_bin_path << "\n";
        return {};
    }

    std::vector<uint32_t> block_offsets(num_blocks + 1);
    in.read(reinterpret_cast<char*>(block_offsets.data()), (num_blocks + 1) * sizeof(uint32_t));
    if (!in) return {};

    uint32_t header_size = sizeof(uint32_t) + (num_blocks + 1) * sizeof(uint32_t);
    uint32_t total_size = block_offsets.back();
    
    if (total_size < header_size || block_offsets[0] != header_size) {
        std::cerr << "[FATAL] Corrupt offset table in " << input_bin_path << "\n";
        return {};
    }
    for (size_t b = 0; b < num_blocks; ++b) {
        if (block_offsets[b + 1] < block_offsets[b]) {
            std::cerr << "[FATAL] Non-monotonic offsets in " << input_bin_path << "\n";
            return {};
        }
    }

    std::vector<uint8_t> compressed_blob(total_size - header_size);
    in.read(reinterpret_cast<char*>(compressed_blob.data()), compressed_blob.size());
    if (!in) return {};

    std::vector<uint8_t> raw_out;
    raw_out.reserve(static_cast<size_t>(num_blocks) * bytes_per_block);
    
    for (size_t b = 0; b < num_blocks; ++b) {
        uint32_t start = block_offsets[b] - header_size;
        uint32_t end = block_offsets[b + 1] - header_size;
        uint32_t comp_size = end - start;
        
        std::vector<uint8_t> block_raw(bytes_per_block, 0);
        const uint8_t* src = compressed_blob.data() + start;
        
        if (!DecompressBlockZSTD(src, comp_size, block_raw.data(), block_raw.size())) {
            std::cerr << "[FATAL] Block " << b << " decompression failed in " << input_bin_path << "\n";
            return {};
        }
        raw_out.insert(raw_out.end(), block_raw.begin(), block_raw.end());
    }

    if (raw_out.size() > expected_raw_size) raw_out.resize(expected_raw_size);
    return raw_out;
}

} // namespace Bestemshe