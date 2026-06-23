#include "Inference.h"
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <lz4.h> // Ensure you link -llz4 during compilation
#include <zstd.h> // Ensure you link -lzstd during compilation

namespace Bestemshe {

// Simple, hyper-fast RLE Decompressor for draw files
void DecompressRLE(const uint8_t* src, size_t src_size, uint8_t* dest, size_t dest_size) {
    size_t src_idx = 0;
    size_t dest_idx = 0;

    while (src_idx < src_size && dest_idx < dest_size) {
        uint8_t value = src[src_idx++];
        uint32_t count = 0;
        // Read variable-length count
        uint8_t shift = 0;
        while (true) {
            uint8_t byte = src[src_idx++];
            count |= (byte & 0x7F) << shift;
            if (!(byte & 0x80)) break;
            shift += 7;
        }
        for (uint32_t c = 0; c < count && dest_idx < dest_size; ++c) {
            dest[dest_idx++] = value;
        }
    }
}

std::vector<uint8_t> InferenceEngine::load_and_decompress_block(const MicroLayerMeta& meta, size_t block_id) {
    std::vector<uint8_t> decompressed_data(meta.block_size / 8, 0);

    int fd = open(meta.file_path.c_str(), O_RDONLY);
    if (fd < 0) {
        // Safe fallback: if file does not exist, assume UNKNOWN state parameters
        return decompressed_data;
    }

    // 1. Read block offset headers
    uint32_t num_blocks;
    read(fd, &num_blocks, sizeof(uint32_t));

    std::vector<uint32_t> block_offsets(num_blocks + 1);
    read(fd, block_offsets.data(), (num_blocks + 1) * sizeof(uint32_t));

    if (block_id >= num_blocks) {
        close(fd);
        return decompressed_data;
    }

    uint32_t start_offset = block_offsets[block_id];
    uint32_t end_offset = block_offsets[block_id + 1];
    uint32_t compressed_size = end_offset - start_offset;

    std::vector<uint8_t> compressed_buffer(compressed_size);
    lseek(fd, start_offset, SEEK_SET);
    read(fd, compressed_buffer.data(), compressed_size);
    close(fd);

    // 2. Decompress based on meta registry setting
    if (meta.compression == CompressionType::NONE) {
        decompressed_data = compressed_buffer;
    } 
    else if (meta.compression == CompressionType::LZ4) {
        LZ4_decompress_safe(
            reinterpret_cast<const char*>(compressed_buffer.data()),
            reinterpret_cast<char*>(decompressed_data.data()),
            compressed_size,
            decompressed_data.size()
        );
    } 
    else if (meta.compression == CompressionType::RLE) {
        DecompressRLE(
            compressed_buffer.data(), 
            compressed_size, 
            decompressed_data.data(), 
            decompressed_data.size()
        );
    } else if (meta.compression == CompressionType::ZSTD) {
        size_t d_size = ZSTD_decompress(
            decompressed_data.data(), decompressed_data.size(),
            compressed_buffer.data(), compressed_size
        );
        if (ZSTD_isError(d_size)) {
            std::cerr << "ZSTD Decompression failed!" << std::endl;
        }
    }
    return decompressed_data;
}

} // namespace Bestemshe