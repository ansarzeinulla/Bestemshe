#include "Compressor.h"
#include <fstream>
#include <iostream>
#include <lz4.h> // Link -llz4
#include <zstd.h>

namespace Bestemshe {

// Custom variable-length integer writer for RLE
void WriteVarint(uint32_t value, std::vector<uint8_t>& dest) {
    while (value >= 0x80) {
        dest.push_back(static_cast<uint8_t>((value & 0x7F) | 0x80));
        value >>= 7;
    }
    dest.push_back(static_cast<uint8_t>(value & 0x7F));
}

std::vector<uint8_t> CompressBlockLZ4(const uint8_t* src, size_t src_size) {
    std::vector<uint8_t> comp_buf(LZ4_compressBound(src_size));
    int comp_size = LZ4_compress_default(
        reinterpret_cast<const char*>(src),
        reinterpret_cast<char*>(comp_buf.data()),
        src_size,
        comp_buf.size()
    );
    comp_buf.resize(comp_size);
    return comp_buf;
}

std::vector<uint8_t> CompressBlockRLE(const uint8_t* src, size_t src_size) {
    std::vector<uint8_t> dest;
    if (src_size == 0) return dest;

    size_t i = 0;
    while (i < src_size) {
        uint8_t val = src[i];
        uint32_t count = 0;
        while (i < src_size && src[i] == val) {
            count++;
            i++;
        }
        dest.push_back(val);
        WriteVarint(count, dest);
    }
    return dest;
}

std::vector<uint8_t> CompressBlockZSTD(const uint8_t* src, size_t src_size) {
    size_t bound = ZSTD_compressBound(src_size);
    std::vector<uint8_t> comp_buf(bound);
    
    // Level 19 is maximum compression. It takes longer to compress, 
    // but decompression remains lightning fast!
    size_t comp_size = ZSTD_compress(
        comp_buf.data(), bound,
        src, src_size,
        19 
    );
    
    if (ZSTD_isError(comp_size)) {
        std::cerr << "ZSTD Compression failed!" << std::endl;
        return {};
    }
    comp_buf.resize(comp_size);
    return comp_buf;
}

void DecompressBlockLZ4(const uint8_t* src, size_t src_size, uint8_t* dest, size_t dest_size) {
    LZ4_decompress_safe(
        reinterpret_cast<const char*>(src),
        reinterpret_cast<char*>(dest),
        static_cast<int>(src_size),
        static_cast<int>(dest_size)
    );
}

void DecompressBlockRLE(const uint8_t* src, size_t src_size, uint8_t* dest, size_t dest_size) {
    size_t src_idx = 0;
    size_t dest_idx = 0;
    while (src_idx < src_size && dest_idx < dest_size) {
        uint8_t value = src[src_idx++];
        uint32_t count = 0;
        uint8_t shift = 0;
        while (src_idx < src_size) {
            uint8_t byte = src[src_idx++];
            count |= static_cast<uint32_t>(byte & 0x7F) << shift;
            if (!(byte & 0x80)) break;
            shift += 7;
        }
        for (uint32_t c = 0; c < count && dest_idx < dest_size; ++c) {
            dest[dest_idx++] = value;
        }
    }
}

void DecompressBlockZSTD(const uint8_t* src, size_t src_size, uint8_t* dest, size_t dest_size) {
    size_t d_size = ZSTD_decompress(dest, dest_size, src, src_size);
    if (ZSTD_isError(d_size)) {
        std::cerr << "ZSTD Decompression failed!" << std::endl;
    }
}

void Compressor::CompressMicroLayer(const std::string& input_raw_path, 
                                     const std::string& output_bin_path, 
                                     const std::string& algorithm, 
                                     size_t block_size) {
    std::ifstream in(input_raw_path, std::ios::binary | std::ios::ate);
    if (!in.is_open()) return;

    size_t total_size = in.tellg();
    in.seekg(0, std::ios::beg);
    std::vector<uint8_t> raw_data(total_size);
    in.read(reinterpret_cast<char*>(raw_data.data()), total_size);
    in.close();

    size_t bytes_per_block = block_size / 8; // Bit packing inside blocks
    size_t num_blocks = (raw_data.size() + bytes_per_block - 1) / bytes_per_block;

    std::vector<std::vector<uint8_t>> compressed_blocks(num_blocks);
    std::vector<uint32_t> block_offsets(num_blocks + 1, 0);

    for (size_t b = 0; b < num_blocks; ++b) {
        size_t start_idx = b * bytes_per_block;
        size_t size = std::min(bytes_per_block, raw_data.size() - start_idx);

        std::vector<uint8_t> block_tmp(bytes_per_block, 0); // zero padded
        std::copy(raw_data.begin() + start_idx, raw_data.begin() + start_idx + size, block_tmp.begin());

        if (algorithm == "LZ4") {
            compressed_blocks[b] = CompressBlockLZ4(block_tmp.data(), bytes_per_block);
        } else if (algorithm == "RLE") {
            compressed_blocks[b] = CompressBlockRLE(block_tmp.data(), bytes_per_block);
        } else if (algorithm == "ZSTD") { // <-- ADD THIS BRANCH
            compressed_blocks[b] = CompressBlockZSTD(block_tmp.data(), bytes_per_block);
        } else {
            compressed_blocks[b] = block_tmp; // Uncompressed fallback
        }
    }

    // Write structure: [Num Blocks] [Offsets Header Table] [Compressed Blocks...]
    std::ofstream out(output_bin_path, std::ios::binary);
    uint32_t num_blocks_u32 = static_cast<uint32_t>(num_blocks);
    out.write(reinterpret_cast<const char*>(&num_blocks_u32), sizeof(uint32_t));

    uint32_t header_bytes_size = sizeof(uint32_t) + (num_blocks_u32 + 1) * sizeof(uint32_t);
    uint32_t current_offset = header_bytes_size;

    for (size_t b = 0; b < num_blocks; ++b) {
        block_offsets[b] = current_offset;
        current_offset += compressed_blocks[b].size();
    }
    block_offsets[num_blocks] = current_offset;

    out.write(reinterpret_cast<const char*>(block_offsets.data()), block_offsets.size() * sizeof(uint32_t));
    for (size_t b = 0; b < num_blocks; ++b) {
        out.write(reinterpret_cast<const char*>(compressed_blocks[b].data()), compressed_blocks[b].size());
    }
    out.close();
}

std::vector<uint8_t> Compressor::DecompressMicroLayer(const std::string& input_bin_path,
                                                      const std::string& algorithm,
                                                      size_t bytes_per_block,
                                                      size_t expected_raw_size) {
    std::ifstream in(input_bin_path, std::ios::binary);
    if (!in.is_open()) {
        return {};
    }

    uint32_t num_blocks = 0;
    in.read(reinterpret_cast<char*>(&num_blocks), sizeof(uint32_t));
    if (!in) return {};

    std::vector<uint32_t> block_offsets(num_blocks + 1);
    in.read(reinterpret_cast<char*>(block_offsets.data()), (num_blocks + 1) * sizeof(uint32_t));
    if (!in) return {};

    uint32_t total_size = block_offsets.back();
    uint32_t header_size = sizeof(uint32_t) + (num_blocks + 1) * sizeof(uint32_t);
    std::vector<uint8_t> compressed_blob(total_size - header_size);
    in.read(reinterpret_cast<char*>(compressed_blob.data()), compressed_blob.size());
    if (!in) return {};

    std::vector<uint8_t> raw_out;
    for (size_t b = 0; b < num_blocks; ++b) {
        uint32_t start = block_offsets[b] - header_size;
        uint32_t end = block_offsets[b + 1] - header_size;
        uint32_t comp_size = end - start;
        std::vector<uint8_t> block_raw(bytes_per_block, 0);
        const uint8_t* src = compressed_blob.data() + start;
        if (algorithm == "LZ4") {
            DecompressBlockLZ4(src, comp_size, block_raw.data(), block_raw.size());
        } else if (algorithm == "RLE") {
            DecompressBlockRLE(src, comp_size, block_raw.data(), block_raw.size());
        } else {
            DecompressBlockZSTD(src, comp_size, block_raw.data(), block_raw.size());
        }
        raw_out.insert(raw_out.end(), block_raw.begin(), block_raw.end());
    }

    if (raw_out.size() > expected_raw_size) {
        raw_out.resize(expected_raw_size);
    }
    return raw_out;
}

} // namespace Bestemshe
