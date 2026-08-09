#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <random>
#include "BestemsheCore.h"
#include "StateIndex.h"
#include "Inference.h"

namespace py = pybind11;
using namespace Bestemshe;

class OracleBridge {
private:
    InferenceEngine db;
    std::mt19937_64 rng;

public:
    OracleBridge() {
        StateIndex::InitCombinatorics();
        std::random_device rd;
        rng.seed(rd());
    }

    // Returns a 14-element Python List: [P1_pits(5), P2_pits(5), K1, K2, PlyClock, OracleValue]
    std::vector<int> sample_state(uint8_t M) {
        uint64_t max_idx = StateIndex::GetLayerSize(M);
        std::uniform_int_distribution<uint64_t> dist(0, max_idx - 1);

        State s;
        while (true) {
            uint64_t rand_idx = dist(rng);
            s = StateIndex::UnindexState(rand_idx, M);
            
            // Ensure we don't sample a state where the game is already mathematically over
            if (s.K_self <= 25 && s.K_opp <= 25) {
                break;
            }
        }

        std::vector<int> py_state(14, 0);
        
        // P1 pits (0-4) and P2 pits (5-9)
        for(int i = 0; i < 10; i++) {
            py_state[i] = s.board[i];
        }
        
        py_state[10] = s.K_self;
        py_state[11] = s.K_opp;
        py_state[12] = 0; // Reset Ply Clock for the AlphaZero rollout

        // Fetch Absolute Ground Truth (Optional, but brilliant for debugging/metrics)
        // 1 = P1 WIN, -1 = P2 WIN (P1 LOSS), 0 = DRAW, -99 = UNKNOWN (Not loaded)
        uint64_t s_idx = StateIndex::IndexState(s);
        GameValue val = db.query_state(M, s.K_opp, s_idx);
        if (val == GameValue::WIN) py_state[13] = 1;
        else if (val == GameValue::LOSS) py_state[13] = -1;
        else if (val == GameValue::DRAW) py_state[13] = 0;
        else py_state[13] = -99;

        return py_state;
    }
};

PYBIND11_MODULE(bestemshe_oracle, m) {
    m.doc() = "Bestemshe C++ Oracle Bridge for RCL-Zero";

    py::class_<OracleBridge>(m, "OracleBridge")
        .def(py::init<>())
        .def("sample_state", &OracleBridge::sample_state, "Samples a random non-terminal state from layer M");
}