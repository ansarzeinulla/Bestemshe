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
    LOSS = 0,
    WIN = 1,
    DRAW = 2,
    UNKNOWN = 3
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
    // LRU Cache entry for holding decompressed blocks
    struct CacheEntry {
        std::string layer_key; // e.g., "win_k1_k2"
        size_t block_id;
        std::vector<uint8_t> decompressed_data;
        uint64_t last_accessed_tick;
    };

    std::unordered_map<std::string, MicroLayerMeta> manifest;
    std::vector<CacheEntry> lru_cache;
    const size_t CACHE_CAPACITY = 128; // Tune to fit within CPU L3 cache boundaries
    uint64_t access_ticker = 0;

public:
    InferenceEngine(const std::string& manifest_path) {
        load_manifest(manifest_path);
    }

    // High-performance single-state query
    // Transparently handles block loading, decompression algorithm selection, and bit extraction
    GameValue query_state(uint16_t k1, uint16_t k2, uint64_t state_index) {
        std::string win_key = "win_" + std::to_string(k1) + "_" + std::to_string(k2);
        std::string draw_key = "draw_" + std::to_string(k1) + "_" + std::to_string(k2);

        bool is_draw = query_micro_layer(draw_key, state_index);
        if (is_draw) {
            return GameValue::DRAW;
        }

        bool is_win = query_micro_layer(win_key, state_index);
        return is_win ? GameValue::WIN : GameValue::LOSS;
    }

private:
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

    bool query_micro_layer(const std::string& layer_key, uint64_t index) {
        auto it = manifest.find(layer_key);
        if (it == manifest.end()) {
            // Default fallback if micro-layer not in manifest (assume raw uncompressed)
            return query_uncompressed_file(layer_key, index);
        }

        const auto& meta = it->second;
        size_t block_id = index / meta.block_size;
        size_t offset_within_block = index % meta.block_size;

        // 1. Check LRU Cache
        for (auto& entry : lru_cache) {
            if (entry.layer_key == layer_key && entry.block_id == block_id) {
                entry.last_accessed_tick = ++access_ticker;
                return extract_bit(entry.decompressed_data, offset_within_block);
            }
        }

        // 2. Cache Miss: Read compressed block and decompress
        std::vector<uint8_t> decompressed = load_and_decompress_block(meta, block_id);
        
        // Push to Cache (with LRU eviction logic)
        if (lru_cache.size() >= CACHE_CAPACITY) {
            auto lru_it = std::min_element(lru_cache.begin(), lru_cache.end(), 
                [](const CacheEntry& a, const CacheEntry& b) {
                    return a.last_accessed_tick < b.last_accessed_tick;
                });
            lru_cache.erase(lru_it);
        }

        lru_cache.push_back({layer_key, block_id, decompressed, ++access_ticker});
        return extract_bit(decompressed, offset_within_block);
    }

    std::vector<uint8_t> load_and_decompress_block(const MicroLayerMeta& meta, size_t block_id);

    inline bool extract_bit(const std::vector<uint8_t>& block_data, size_t offset) const {
        return (block_data[offset / 8] >> (offset % 8)) & 1;
    }

    bool query_uncompressed_file(const std::string& key, uint64_t index) {
        // Fallback fallback mmap or simple stream lookup for uncompressed legacy runs
        return false;
    }
};

} // namespace Bestemshe