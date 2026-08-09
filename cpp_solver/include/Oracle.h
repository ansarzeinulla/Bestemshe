#pragma once
// Mmap-based single-state tablebase reader.
// Decompresses exactly one 4MB block per lookup, so peak RSS stays in the
// tens of megabytes no matter how large the on-disk tablebase is.
#include <cstdint>
#include <cstdlib>
#include <string>
#include <vector>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <zstd.h>
#include "StateIndex.h"

namespace Bestemshe {

class MmapBlockReader {
private:
    int fd = -1;
    const uint8_t* map = nullptr;
    size_t file_size = 0;
    uint32_t num_blocks = 0;
    const uint32_t* offsets = nullptr; // num_blocks + 1 entries

    // Must match Compressor::CompressMicroLayer (33554432 bits per block)
    static constexpr size_t BYTES_PER_BLOCK = 33554432 / 8;

public:
    MmapBlockReader() = default;
    MmapBlockReader(const MmapBlockReader&) = delete;
    MmapBlockReader& operator=(const MmapBlockReader&) = delete;
    ~MmapBlockReader() { close_file(); }

    bool open_file(const std::string& path) {
        close_file();
        fd = ::open(path.c_str(), O_RDONLY);
        if (fd < 0) return false;

        struct stat st;
        if (fstat(fd, &st) != 0) { close_file(); return false; }
        file_size = static_cast<size_t>(st.st_size);
        if (file_size < sizeof(uint32_t)) { close_file(); return false; }

        void* m = mmap(nullptr, file_size, PROT_READ, MAP_PRIVATE, fd, 0);
        if (m == MAP_FAILED) { close_file(); return false; }
        map = static_cast<const uint8_t*>(m);

        // Header layout: [u32 num_blocks][u32 offsets[num_blocks + 1]][payload]
        num_blocks = *reinterpret_cast<const uint32_t*>(map);
        size_t header_size = sizeof(uint32_t) + (static_cast<size_t>(num_blocks) + 1) * sizeof(uint32_t);
        if (num_blocks == 0 || header_size > file_size) { close_file(); return false; }

        offsets = reinterpret_cast<const uint32_t*>(map + sizeof(uint32_t));
        if (offsets[0] != header_size || offsets[num_blocks] > file_size) { close_file(); return false; }
        return true;
    }

    void close_file() {
        if (map) munmap(const_cast<uint8_t*>(map), file_size);
        if (fd >= 0) ::close(fd);
        map = nullptr; offsets = nullptr; fd = -1;
        file_size = 0; num_blocks = 0;
    }

    bool is_open() const { return map != nullptr; }

    // Decompresses only the block containing bit_index and extracts the bit.
    // Returns -1 on error, otherwise 0/1.
    int read_bit(uint64_t bit_index) const {
        if (!map) return -1;
        uint64_t byte_index = bit_index / 8;
        uint64_t block = byte_index / BYTES_PER_BLOCK;
        if (block >= num_blocks) return -1;
        if (offsets[block + 1] < offsets[block]) return -1;

        const uint8_t* src = map + offsets[block];
        size_t comp_size = offsets[block + 1] - offsets[block];

        std::vector<uint8_t> raw(BYTES_PER_BLOCK);
        size_t d = ZSTD_decompress(raw.data(), raw.size(), src, comp_size);
        if (ZSTD_isError(d)) return -1;

        uint64_t local_byte = byte_index % BYTES_PER_BLOCK;
        return (raw[local_byte] >> (bit_index % 8)) & 1;
    }
};

enum class OracleValue : int { ERROR = -1, LOSS = 0, WIN = 1, DRAW = 2 };

// Stateless per-query oracle over the compressed layer files.
class TablebaseOracle {
private:
    std::string data_dir;

public:
    TablebaseOracle() {
        const char* env = std::getenv("BESTEMSHE_DATA_DIR");
        data_dir = env ? env : "layers/compressed";
    }

    const std::string& dir() const { return data_dir; }

    // Value of a canonical state (side-to-move perspective).
    OracleValue query(const State& s) const {
        uint16_t k1 = s.M - s.K_opp;
        std::string base = data_dir + "/layer_" + std::to_string(k1) + "_" +
                           std::to_string(s.K_opp) + "_";

        int R = 50 - static_cast<int>(s.M);
        uint64_t b_count = StateIndex::nCr(R + 9, 9);
        uint64_t local_idx = StateIndex::IndexState(s) % b_count;

        MmapBlockReader win, draw;
        if (!win.open_file(base + "win.bin") || !draw.open_file(base + "draw.bin"))
            return OracleValue::ERROR;

        int d = draw.read_bit(local_idx);
        if (d < 0) return OracleValue::ERROR;
        if (d == 1) return OracleValue::DRAW;
        int w = win.read_bit(local_idx);
        if (w < 0) return OracleValue::ERROR;
        return w == 1 ? OracleValue::WIN : OracleValue::LOSS;
    }
};

} // namespace Bestemshe
