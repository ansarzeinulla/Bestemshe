#pragma once
#include <string>
#include <vector>
#include <unordered_map>
#include <memory>
#include <fstream>
#include <sstream>
#include <iostream>
#include <algorithm>

namespace Bestemshe {

enum class CompressionType {
    NONE,
    LZ4,
    RLE,
    BPE,
    ZSTD
};

enum class GameValue : uint8_t {
    UNKNOWN = 0,
    WIN = 1,
    LOSS = 2,
    DRAW = 3
};

// Represents metadata for a specific micro-layer (K1, K2)
struct MicroLayerMeta {
    uint16_t k1;
    uint16_t k2;
    std::string db_type; // "win" or "draw"
    CompressionType compression;
    size_t block_size;
    std::string file_path;
};

class InferenceEngine {
private:
    struct RawLayerCacheEntry {
        std::vector<uint8_t> win_bits;
        std::vector<uint8_t> draw_bits;
        bool loaded = false;
    };

    std::unordered_map<std::string, MicroLayerMeta> manifest;
    std::unordered_map<std::string, RawLayerCacheEntry> raw_layer_cache;

public:
    InferenceEngine(const std::string& manifest_path) {
        load_manifest(manifest_path);
    }

    // High-performance single-state query.
    // The caller passes the target layer M and the target state's k2 coordinate.
    GameValue query_state(uint8_t M, uint8_t k2, uint64_t state_index) {
        if (k2 > M) {
            return GameValue::UNKNOWN;
        }
        if (!preload_uncompressed_layer(M, k2)) {
            return GameValue::UNKNOWN;
        }

        const std::string layer_key = layer_cache_key(M, k2);
        const auto& entry = raw_layer_cache.find(layer_key)->second;
        if (extract_bit(entry.draw_bits, state_index)) {
            return GameValue::DRAW;
        }
        if (extract_bit(entry.win_bits, state_index)) {
            return GameValue::WIN;
        }
        return GameValue::LOSS;
    }

private:
    static std::string layer_cache_key(uint8_t M, uint8_t k2) {
        return std::to_string(M) + "_" + std::to_string(k2);
    }

    void load_manifest(const std::string& manifest_path) {
        std::ifstream file(manifest_path);
        if (!file.is_open()) {
            std::cerr << "WARNING: No compression manifest found. Assuming uncompressed defaults." << std::endl;
            return;
        }
        std::string line;
        while (std::getline(file, line)) {
            if (line.empty() || line[0] == '#') continue;
            std::stringstream ss(line);
            uint16_t k1, k2;
            std::string db_type, comp_str;
            size_t block_size;
            ss >> k1 >> k2 >> db_type >> comp_str >> block_size;

            CompressionType comp = CompressionType::NONE;
            if (comp_str == "LZ4")  comp = CompressionType::LZ4;
            else if (comp_str == "RLE")  comp = CompressionType::RLE;
            else if (comp_str == "BPE")  comp = CompressionType::BPE;
            else if (comp_str == "ZSTD") comp = CompressionType::ZSTD;

            std::string key = db_type + "_" + std::to_string(k1) + "_" + std::to_string(k2);
            std::string path = "layers/layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_" + db_type + ".bin";
            
            manifest[key] = {k1, k2, db_type, comp, block_size, path};
        }
    }

    bool preload_uncompressed_layer(uint8_t M, uint8_t k2) {
        const std::string cache_key = layer_cache_key(M, k2);
        auto cache_it = raw_layer_cache.find(cache_key);
        if (cache_it != raw_layer_cache.end() && cache_it->second.loaded) {
            return true;
        }

        uint16_t k1 = static_cast<uint16_t>(M) - static_cast<uint16_t>(k2);
        std::string win_path = "layers/layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_win.raw";
        std::string draw_path = "layers/layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_draw.raw";

        std::ifstream win_file(win_path, std::ios::binary | std::ios::ate);
        std::ifstream draw_file(draw_path, std::ios::binary | std::ios::ate);
        if (!win_file.is_open() || !draw_file.is_open()) {
            return false;
        }

        size_t win_size = static_cast<size_t>(win_file.tellg());
        size_t draw_size = static_cast<size_t>(draw_file.tellg());
        win_file.seekg(0, std::ios::beg);
        draw_file.seekg(0, std::ios::beg);

        RawLayerCacheEntry entry;
        entry.win_bits.resize(win_size);
        entry.draw_bits.resize(draw_size);
        win_file.read(reinterpret_cast<char*>(entry.win_bits.data()), static_cast<std::streamsize>(win_size));
        draw_file.read(reinterpret_cast<char*>(entry.draw_bits.data()), static_cast<std::streamsize>(draw_size));
        entry.loaded = true;

        if (!win_file || !draw_file) {
            return false;
        }

        raw_layer_cache[cache_key] = std::move(entry);
        return true;
    }

    inline bool extract_bit(const std::vector<uint8_t>& block_data, size_t offset) const {
        return (block_data[offset / 8] >> (offset % 8)) & 1;
    }
};

} // namespace Bestemshe
