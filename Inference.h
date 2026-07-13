#pragma once
#include <vector>
#include <string>
#include <iostream>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <atomic>
#include "StateIndex.h"
#include "Compressor.h"

namespace Bestemshe {

enum class GameValue : uint8_t {
    UNKNOWN = 0,
    WIN = 1,
    LOSS = 2,
    DRAW = 3
};

class InferenceEngine {
private:
    struct RawLayerCacheEntry {
        std::vector<uint8_t> win_bits;
        std::vector<uint8_t> draw_bits;
        std::atomic<int> loaded{0};

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

        RawLayerCacheEntry(const RawLayerCacheEntry&) = delete;
        RawLayerCacheEntry& operator=(const RawLayerCacheEntry&) = delete;
    };

    // THE BREAKTHROUGH: Flat 2D Array Cache. No std::string, no std::unordered_map.
    // M ranges from 0 to 48. K2 ranges from 0 to 24.
    // We size to [50][26] to safely cover bounds without math operations.
    RawLayerCacheEntry fast_cache[50][26];
    std::mutex cache_mutex;

    // Hardcoded ZSTD configuration
    static constexpr size_t ZSTD_BLOCK_SIZE_BITS = 33554432; 

public:
    InferenceEngine() = default;

    // Evicts all preloaded data from memory
    void clear_cache() {
        std::lock_guard<std::mutex> lock(cache_mutex);
        for (int m = 0; m < 50; ++m) {
            for (int k2 = 0; k2 < 26; ++k2) {
                fast_cache[m][k2].win_bits.clear();
                fast_cache[m][k2].win_bits.shrink_to_fit();
                fast_cache[m][k2].draw_bits.clear();
                fast_cache[m][k2].draw_bits.shrink_to_fit();
                fast_cache[m][k2].loaded.store(0, std::memory_order_relaxed);
            }
        }
    }

    // Preloads ONLY the higher micro-layers strictly reachable from pair (K1, K2).
    bool preload_pair(uint16_t K1, uint16_t K2, uint8_t layer_M) {
        clear_cache(); 

        std::cout << "[INFO] InferenceEngine: Preloading selective reach set for Pair ("
                  << K1 << "," << K2 << ") in Layer M=" << static_cast<int>(layer_M) << "...\n";

        bool ok = true;
        // 1. (K2, j) where j is even and K1 < j <= 24
        for (int j = K1 + 2; j <= 24; j += 2) {
            uint8_t M_next = K2 + j;
            if (M_next <= 48 && !preload_uncompressed_layer(M_next, static_cast<uint8_t>(j))) ok = false;
        }

        // 2. (K1, j) where j is even and K2 < j <= 24
        for (int j = K2 + 2; j <= 24; j += 2) {
            uint8_t M_next = K1 + j;
            if (M_next <= 48 && !preload_uncompressed_layer(M_next, static_cast<uint8_t>(j))) ok = false;
        }
        return ok;
    }

    // High-performance $O(1)$ single-state query. Zero heap allocations.
    inline GameValue query_state(uint8_t M, uint8_t k2, uint64_t state_index) {
        if (k2 > M) return GameValue::UNKNOWN;
        
        const auto& entry = fast_cache[M][k2];
        if (entry.loaded.load(std::memory_order_acquire) == 0) {
            // Lazy load fallback (should rarely hit during active sweep if preloaded correctly)
            if (!preload_uncompressed_layer(M, k2)) return GameValue::UNKNOWN;
        }

        int R = 50 - static_cast<int>(M);
        uint64_t b_count = StateIndex::nCr(R + 9, 9);
        uint64_t local_idx = state_index % b_count;

        if (extract_bit(entry.draw_bits, local_idx)) return GameValue::DRAW;
        if (extract_bit(entry.win_bits, local_idx)) return GameValue::WIN;
        return GameValue::LOSS;
    }

private:
    bool preload_uncompressed_layer(uint8_t M, uint8_t k2) {
        // Fast path: Check without lock
        if (fast_cache[M][k2].loaded.load(std::memory_order_acquire) == 1) return true;

        std::lock_guard<std::mutex> lock(cache_mutex);
        // Double check with lock
        if (fast_cache[M][k2].loaded.load(std::memory_order_relaxed) == 1) return true;

        uint16_t k1 = static_cast<uint16_t>(M) - static_cast<uint16_t>(k2);
        
        std::string raw_win = "layers/layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_win.raw";
        std::string raw_draw = "layers/layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_draw.raw";
        std::string comp_win = "layers/compressed/layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_win.bin";
        std::string comp_draw = "layers/compressed/layer_" + std::to_string(k1) + "_" + std::to_string(k2) + "_draw.bin";

        std::vector<uint8_t> win_bits;
        std::vector<uint8_t> draw_bits;

        // Try RAW files first (if we are actively generating/verifying)
        if (std::filesystem::exists(raw_win) && std::filesystem::exists(raw_draw)) {
            auto read_raw = [](const std::string& path) -> std::vector<uint8_t> {
                std::ifstream f(path, std::ios::binary | std::ios::ate);
                if (!f) return {};
                size_t sz = f.tellg();
                f.seekg(0);
                std::vector<uint8_t> data(sz);
                f.read(reinterpret_cast<char*>(data.data()), sz);
                return data;
            };
            win_bits = read_raw(raw_win);
            draw_bits = read_raw(raw_draw);
        } 
        // Fallback to ZSTD COMPRESSED files
        else if (std::filesystem::exists(comp_win) && std::filesystem::exists(comp_draw)) {
            int R = 50 - M;
            uint64_t b_count = StateIndex::nCr(R + 9, 9);
            uint64_t expected_bytes = (b_count + 7) / 8;

            win_bits = Compressor::DecompressMicroLayer(comp_win, ZSTD_BLOCK_SIZE_BITS / 8, expected_bytes);
            draw_bits = Compressor::DecompressMicroLayer(comp_draw, ZSTD_BLOCK_SIZE_BITS / 8, expected_bytes);
        } else {
            std::cerr << "[FATAL] Dependencies missing for Pair (" << k1 << "," << (int)k2 
                      << ") in M=" << (int)M << ". Ensure .raw or .bin files exist.\n";
            return false;
        }

        if (win_bits.empty() || draw_bits.empty()) return false;

        fast_cache[M][k2].win_bits = std::move(win_bits);
        fast_cache[M][k2].draw_bits = std::move(draw_bits);
        fast_cache[M][k2].loaded.store(1, std::memory_order_release);
        return true;
    }

    inline bool extract_bit(const std::vector<uint8_t>& block_data, size_t offset) const {
        return (block_data[offset / 8] >> (offset % 8)) & 1;
    }
};

} // namespace Bestemshe