#pragma once
#include "BestemsheCore.h"

namespace Bestemshe {

class StateIndex {
private:
    static uint64_t NCR_TABLE[60][10];

public:
    static void InitCombinatorics() {
        for (int n = 0; n < 60; ++n) {
            for (int k = 0; k < 10; ++k) {
                if (k == 0 || n == k) NCR_TABLE[n][k] = 1;
                else if (k > n)       NCR_TABLE[n][k] = 0;
                else                  NCR_TABLE[n][k] = NCR_TABLE[n-1][k-1] + NCR_TABLE[n-1][k];
            }
        }
    }

    static inline uint64_t nCr(int n, int k) {
        // NCR_TABLE is [60][10]: valid rows 0..59, valid cols 0..9.
        // Guard every dimension so k==10 / n>=60 can never index out of bounds.
        if (n < 0 || k < 0 || k >= 10 || n >= 60 || n < k) return 0;
        return NCR_TABLE[n][k];
    }

    static inline int GetMinK(uint8_t M) { 
        return std::max(0, (int)M - 24); 
    }
    
    static inline int GetKCount(uint8_t M) { 
        return (std::min(24, (int)M) - GetMinK(M)) / 2 + 1; 
    }

    static uint64_t GetLayerSize(uint8_t M) {
        uint64_t k_count = GetKCount(M);
        int R = 50 - M;
        uint64_t b_count = nCr(R + 9, 9);
        return k_count * b_count;
    }

    static uint64_t IndexState(const State& s) {
        int min_K = GetMinK(s.M);
        uint64_t I_K = (s.K_self - min_K) / 2;

        uint64_t I_B = 0;
        int sum = 0;
        for (int i = 0; i < 9; ++i) {
            sum += s.board[i];
            int p_i = i + sum;
            I_B += nCr(p_i, i + 1);
        }

        int R = 50 - s.M;
        return I_K * nCr(R + 9, 9) + I_B;
    }

    static State UnindexState(uint64_t index, uint8_t M) {
        State s;
        s.M = M;
        int R = 50 - M;
        uint64_t b_count = nCr(R + 9, 9);

        uint64_t I_K = index / b_count;
        uint64_t I_B = index % b_count;

        s.K_self = GetMinK(M) + I_K * 2;
        s.K_opp = M - s.K_self;

        int current_p = 0;
        for (int i = 8; i >= 0; --i) {
            int p = i;
            while (nCr(p + 1, i + 1) <= I_B) p++;
            I_B -= nCr(p, i + 1);
            if (i == 8) s.board[9] = R + 8 - p;
            else s.board[i + 1] = current_p - p - 1;
            current_p = p;
        }
        s.board[0] = current_p;
        return s;
    }

    // O(1)-amortized "board odometer": advances a board (sum == R) to the next composition
    // in IndexState (colex combinatorial-number-system) order. Moving a stone leftward is the
    // CNS-rank successor; the inner clear loop is the odometer "carry", amortized O(1) over a
    // full enumeration. Returns false on wrap-around from the last composition (R,0,...,0).
    // Bijection-equivalent to iterating UnindexState(i) for i = 0,1,2,... within a fixed K.
    static inline bool AdvanceBoard(uint8_t b[10]) {
        int S = b[0];                               // running prefix sum b[0..j-1]
        for (int j = 1; j <= 9; ++j) {
            if (b[j] > 0) {
                b[j] -= 1;
                for (int t = 0; t <= j - 2; ++t) b[t] = 0;
                b[j - 1] = static_cast<uint8_t>(S + 1);
                return true;
            }
            S += b[j];                              // b[j] == 0 here; keeps S == b[0..j]
        }
        return false;                               // wrapped (last composition reached)
    }
};

// Allocate the static table definition
inline uint64_t StateIndex::NCR_TABLE[60][10] = {};

} // namespace Bestemshe