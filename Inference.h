#pragma once
#include <string>
#include <vector>
#include <unordered_map>
#include <memory>
#include <fstream>
#include <sstream>
#include <iostream>
#include <algorithm>
#include <filesystem>
#include <mutex>
#include <atomic>
#include "StateIndex.h"
#include "Compressor.h"

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
        std::atomic<int> loaded{0};

        // Define move constructor and assignment to handle the non-copyable/non-movable std::atomic
        RawLayerCacheEntry() = default;
        RawLayerCacheEntry(RawLayerCacheEntry&& other) noexcept {
            win_bits = std::move(other.win_bits);
            draw_bits = std::move(other.draw_bits);
            loaded.store(other.loaded.load(std::memory_order_relaxed), std::memory_order_relaxed);
        }
        RawLayerCacheEntry& operator=(RawLayerCacheEntry&& other) noexcept {
            if (this != &other) {
                win_bits = std::move(other.win_bits);
                draw_bits = std::move(other.draw_bits);
                loaded.store(other.loaded.load(std::memory_order_relaxed), std::memory_order_relaxed);
            }
            return *this;
        }

        // Disable copying
        RawLayerCacheEntry(const RawLayerCacheEntry&) = delete;
        RawLayerCacheEntry& operator=(const RawLayerCacheEntry&) = delete;
    };

    std::unordered_map<std::string, MicroLayerMeta> manifest;
    // raw_layer_cache entries are inserted once and never erased or modified.
    // Insertions are serialised by cache_mutex.  After a successful insert,
    // readers only need to observe loaded==1 (acquire) to safely read the data.
    std::unordered_map<std::string, RawLayerCacheEntry> raw_layer_cache;
    mutable std::mutex cache_mutex;

public:
    InferenceEngine(const std::string& manifest_path) {
        load_manifest(manifest_path);
    }

    // Pre-load all micro-layers for a given target_M into RAM sequentially.
    // Call this ONCE before starting any parallel solve so that query_state
    // never needs to modify raw_layer_cache during parallel execution.
    void preload_all_layers(uint8_t target_M) {
        // All capture moves from layer target_M lead to layers target_M+2, +4, ... 48.
        // We must load all micro-layer (k1,k2) pairs for each such M.
        for (int M = target_M + 2; M <= 48; M += 2) {
            int min_K = std::max(0, M - 24);
            int max_K = std::min(24, M);
            for (int k1 = min_K; k1 <= max_K; k1 += 2) {
                int k2 = M - k1;
                preload_uncompressed_layer(static_cast<uint8_t>(M), static_cast<uint8_t>(k2));
            }
        }
        std::cout << "[INFO] InferenceEngine: pre-loaded all higher layers for M=" 
                  << static_cast<int>(target_M) << ".\n";
    }

    // High-performance single-state query.
    // MUST only be called after preload_all_layers() has been invoked once on the
    // same thread (or preload_uncompressed_layer for the specific (M,k2) pair).
    // After preloading, the map is never modified, so reads are lock-free.
    GameValue query_state(uint8_t M, uint8_t k2, uint64_t state_index) {
        if (k2 > M) return GameValue::UNKNOWN;
        const std::string layer_key = layer_cache_key(M, k2);
        auto it = raw_layer_cache.find(layer_key);
        if (it == raw_layer_cache.end() || it->second.loaded.load(std::memory_order_relaxed) == 0) {
            // Fallback: shouldn't happen if preload_all_layers was called,
            // but handle gracefully.
            if (!preload_uncompressed_layer(M, k2)) return GameValue::UNKNOWN;
            it = raw_layer_cache.find(layer_key);
            if (it == raw_layer_cache.end()) return GameValue::UNKNOWN;
        }
        // state_index is the GLOBAL layer index: I_K * b_count + I_B.
        // Each micro-layer bitset stores only b_count = nCr(R+9,9) entries,
        // so we must strip the I_K component and use only the local offset I_B.
        int R = 50 - static_cast<int>(M);
        uint64_t b_count = StateIndex::nCr(R + 9, 9);
        uint64_t local_idx = state_index % b_count;

        const auto& entry = it->second;
        if (extract_bit(entry.draw_bits, local_idx)) return GameValue::DRAW;
        if (extract_bit(entry.win_bits, local_idx)) return GameValue::WIN;
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

        // Fast path: check the atomic flag with acquire ordering.
        // If another thread has already finished loading, we see a fully
        // initialised entry and can return immediately without the mutex.
        {
            std::lock_guard<std::mutex> lock(cache_mutex);
            auto it = raw_layer_cache.find(cache_key);
            if (it != raw_layer_cache.end() && it->second.loaded.load(std::memory_order_acquire) == 1)
                return true;
        }

        // Slow path: serialise the actual load so only one thread does it.
        std::lock_guard<std::mutex> lock(cache_mutex);
        // Double-check now that we hold the lock.
        auto it = raw_layer_cache.find(cache_key);
        if (it != raw_layer_cache.end() && it->second.loaded.load(std::memory_order_relaxed) == 1)
            return true;

        uint16_t k1 = static_cast<uint16_t>(M) - static_cast<uint16_t>(k2);
        std::string win_path = "layers/layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_win.raw";
        std::string draw_path = "layers/layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_draw.raw";

        std::ifstream win_file(win_path, std::ios::binary | std::ios::ate);
        std::ifstream draw_file(draw_path, std::ios::binary | std::ios::ate);
        
        std::vector<uint8_t> win_bits;
        std::vector<uint8_t> draw_bits;

        if (win_file.is_open() && draw_file.is_open()) {
            size_t win_size = static_cast<size_t>(win_file.tellg());
            size_t draw_size = static_cast<size_t>(draw_file.tellg());
            win_file.seekg(0, std::ios::beg);
            draw_file.seekg(0, std::ios::beg);
            win_bits.resize(win_size);
            draw_bits.resize(draw_size);
            win_file.read(reinterpret_cast<char*>(win_bits.data()), static_cast<std::streamsize>(win_size));
            draw_file.read(reinterpret_cast<char*>(draw_bits.data()), static_cast<std::streamsize>(draw_size));
            if (!win_file || !draw_file) return false;
        } else {
            int R = 50 - M;
            uint64_t b_count = StateIndex::nCr(R + 9, 9);
            uint64_t b_bytes = (b_count + 7) / 8;

            std::string win_key = "win_" + std::to_string(k1) + "_" + std::to_string(k2);
            std::string draw_key = "draw_" + std::to_string(k1) + "_" + std::to_string(k2);

            std::string comp_win = "ZSTD";
            size_t block_win = 33554432;
            std::string path_win = "layers/compressed/layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_win.bin";
            if (!std::filesystem::exists(path_win))
                path_win = "layers/layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_win.bin";

            if (manifest.find(win_key) != manifest.end()) {
                block_win = manifest[win_key].block_size;
                if (manifest[win_key].compression == CompressionType::LZ4) comp_win = "LZ4";
                else if (manifest[win_key].compression == CompressionType::RLE) comp_win = "RLE";
                else if (manifest[win_key].compression == CompressionType::ZSTD) comp_win = "ZSTD";
                else comp_win = "NONE";
            }

            std::string comp_draw = "ZSTD";
            size_t block_draw = 33554432;
            std::string path_draw = "layers/compressed/layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_draw.bin";
            if (!std::filesystem::exists(path_draw))
                path_draw = "layers/layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_draw.bin";

            if (manifest.find(draw_key) != manifest.end()) {
                block_draw = manifest[draw_key].block_size;
                if (manifest[draw_key].compression == CompressionType::LZ4) comp_draw = "LZ4";
                else if (manifest[draw_key].compression == CompressionType::RLE) comp_draw = "RLE";
                else if (manifest[draw_key].compression == CompressionType::ZSTD) comp_draw = "ZSTD";
                else comp_draw = "NONE";
            }

            win_bits = Compressor::DecompressMicroLayer(path_win, comp_win, block_win / 8, b_bytes);
            draw_bits = Compressor::DecompressMicroLayer(path_draw, comp_draw, block_draw / 8, b_bytes);

            if (win_bits.size() < b_bytes || draw_bits.size() < b_bytes) {
                std::cerr << "ERROR: InferenceEngine failed to load/decompress layer " << (int)M 
                          << " k1=" << k1 << " k2=" << (int)k2 
                          << " (win_sz=" << win_bits.size() << " draw_sz=" << draw_bits.size() 
                          << " expected=" << b_bytes << ")\n"
                          << "  path_win: " << path_win << "\n"
                          << "  path_draw: " << path_draw << "\n";
                return false;
            }
        }

        RawLayerCacheEntry entry;
        entry.win_bits = std::move(win_bits);
        entry.draw_bits = std::move(draw_bits);
        // Insert before setting loaded so the map doesn't rehash after the flag is set.
        raw_layer_cache[cache_key] = std::move(entry);
        // Release store: makes win_bits/draw_bits visible to any thread that
        // subsequently reads loaded with memory_order_acquire.
        raw_layer_cache[cache_key].loaded.store(1, std::memory_order_release);
        return true;
    }

    inline bool extract_bit(const std::vector<uint8_t>& block_data, size_t offset) const {
        return (block_data[offset / 8] >> (offset % 8)) & 1;
    }
};

} // namespace Bestemshe
