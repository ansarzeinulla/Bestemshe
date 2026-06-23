#include <iostream>
#include <string>
#include <vector>
#include <filesystem>
#include <fstream>
#include <cstdlib>
#include <algorithm>
#include <iomanip>
#include <chrono>
#include <iomanip>

// Helper to run command and benchmark it
double ExecuteAndBenchmark(const std::string& cmd) {
    auto start = std::chrono::high_resolution_clock::now();
    
    int ret = std::system(cmd.c_str());
    if (ret != 0) {
        std::cerr << "FATAL ERROR: Command failed: " << cmd << "\n";
        std::exit(1);
    }
    
    auto end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double> diff = end - start;
    return diff.count();
}

namespace fs = std::filesystem;

uint64_t GetFileSize(const std::string& path) {
    if (!fs::exists(path)) return 0;
    return fs::file_size(path);
}

void ExecuteCommand(const std::string& cmd) {
    int ret = std::system(cmd.c_str());
    if (ret != 0) {
        std::cerr << "FATAL ERROR: Command failed with exit code " << ret << "\nAborting." << std::endl;
        std::exit(1);
    }
}

void AppendToManifest(const std::string& manifest_path, uint16_t k1, uint16_t k2, const std::string& type, const std::string& algo, const std::string& block_size) {
    std::ofstream out(manifest_path, std::ios::app);
    if (out.is_open())
        out << k1 << " " << k2 << " " << type << " " << algo << " " << block_size << "\n";
}

std::vector<uint8_t> ReadFileBytes(const std::string& path) {
    std::ifstream in(path, std::ios::binary | std::ios::ate);
    if (!in.is_open()) return {};
    std::streamsize size = in.tellg();
    in.seekg(0, std::ios::beg);
    std::vector<uint8_t> bytes(static_cast<size_t>(size));
    if (size > 0) in.read(reinterpret_cast<char*>(bytes.data()), size);
    return bytes;
}

bool VerifyRoundTrip(const std::string& raw_path,
                     const std::string& compressed_path,
                     const std::string& algorithm,
                     size_t block_size_bits) {
    std::vector<uint8_t> raw = ReadFileBytes(raw_path);
    if (raw.empty() && !fs::exists(raw_path)) return false;
    std::string tmp_raw = compressed_path + ".verify.tmp";
    std::string cmd = "./bestemshe --decompress " + compressed_path + " " + tmp_raw + " " + algorithm + " " +
                      std::to_string(block_size_bits) + " " + std::to_string(raw.size());
    ExecuteCommand(cmd);

    std::vector<uint8_t> decompressed = ReadFileBytes(tmp_raw);
    std::error_code ec;
    fs::remove(tmp_raw, ec);
    return raw == decompressed;
}

int main(int argc, char* argv[]) {
    if (argc < 3 || std::string(argv[1]) != "--maxlayer") {
        std::cerr << "Usage: ./pipeline --maxlayer <target_M>\n";
        return 1;
    }

    int target_M = std::stoi(argv[2]);
    
    std::cout << "========================================================\n"
              << "   BESTEMSHE PRODUCTION ZSTD PIPELINE (1MB BLOCKS)      \n"
              << "   Solving from M = 48 down to M = " << target_M << "\n"
              << "========================================================" << std::endl;

    fs::create_directories("layers");
    fs::create_directories("layers/compressed");

    std::string manifest = "layers/compressed/compression_map.txt";
    std::string stats_csv = "layers/stats_zstd.csv";

    if (!fs::exists(manifest)) {
        std::ofstream out(manifest);
        out << "# K_self K_opp DB_Type(win/draw) Compression_Type Block_Size\n";
    }

    if (!fs::exists(stats_csv)) {
        std::ofstream out(stats_csv);
        out << "M,K1,K2,Type,Raw_Bytes,ZSTD_Bytes,ZSTD_Ratio\n";
    }

    for (int M = 48; M >= target_M; M -= 2) {
        std::cout << "\n>>> PROCESSING LAYER M = " << M << " <<<\n" << std::endl;

        double t_solve = ExecuteAndBenchmark("./bestemshe --solve " + std::to_string(M) + " " + manifest);
        double t_split = ExecuteAndBenchmark("./bestemshe --split " + std::to_string(M) + " layers/ layers/");

        std::cout << "[TELEMETRY] Layer " << M << " Solver: " << std::fixed << std::setprecision(4) << t_solve << "s\n";
        std::cout << "[TELEMETRY] Layer " << M << " Splitter: " << t_split << "s\n";

        int min_K = std::max(0, M - 24);
        int max_K = std::min(24, M);

        for (int k1 = min_K; k1 <= max_K; k1 += 2) {
            int k2 = M - k1;
            std::string k_str = std::to_string(k1) + "_" + std::to_string(k2);

            for (const std::string& type : {"win", "draw"}) {
                std::string raw_file = "layers/layer_" + k_str + "_" + type + ".raw";
                std::string zstd_file = "layers/compressed/layer_" + k_str + "_" + type + ".bin";

                if (!fs::exists(raw_file)) continue;

                // Compress strictly with ZSTD using our 1M state L2-Cache optimized blocks
                constexpr size_t block_size_bits = 33554432;
                std::string comp_cmd = "./bestemshe --compress " + raw_file + " " + zstd_file + " ZSTD " + std::to_string(block_size_bits);
                ExecuteCommand(comp_cmd);
                AppendToManifest(manifest, k1, k2, type, "ZSTD", "33554432");

                if (!VerifyRoundTrip(raw_file, zstd_file, "ZSTD", block_size_bits)) {
                    std::cerr << "CRITICAL ERROR: round-trip verification failed for "
                              << raw_file << " -> " << zstd_file << "\n";
                    std::exit(1);
                }

                uint64_t raw_sz = GetFileSize(raw_file);
                uint64_t zstd_sz = GetFileSize(zstd_file);
                double zstd_ratio = static_cast<double>(raw_sz) / (zstd_sz ? zstd_sz : 1);

                std::ofstream stats_out(stats_csv, std::ios::app);
                if (stats_out.is_open()) {
                    stats_out << M << "," << k1 << "," << k2 << "," << type << ","
                              << raw_sz << "," << zstd_sz << ","
                              << std::fixed << std::setprecision(4) << zstd_ratio << "\n";
                }

                fs::remove(raw_file);
            }
        }

        fs::remove("layers/layer" + std::to_string(M) + "_win.bin");
        fs::remove("layers/layer" + std::to_string(M) + "_draw.bin");

        std::cout << "[STATUS] Layer " << M << " fully processed via ZSTD." << std::endl;
    }

    std::cout << "\nPIPELINE RUN COMPLETE. See layers/stats_zstd.csv" << std::endl;
    return 0;
}
