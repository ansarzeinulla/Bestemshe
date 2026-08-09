# ==============================================================================
# BESTEMSHE HPC ENGINE — AUTO-DETECTING MAKEFILE
#
# CMakeLists.txt is the primary build (see the repo README). This Makefile is
# the zero-dependency fallback for cluster nodes without CMake:
#     make -C cpp_solver all
# Binaries land in cpp_solver/build/.
# ==============================================================================

UNAME_S := $(shell uname -s)

ifeq ($(UNAME_S),Darwin)
    # macOS with Homebrew GCC (adjust 'g++-16' if your installed version differs)
    CXX = g++-16
    CXXFLAGS = -std=c++17 -O3 -flto -Wall -Wextra -DNDEBUG -fopenmp -Iinclude -I/opt/homebrew/include
    LDFLAGS = -L/opt/homebrew/lib -lzstd -flto -fopenmp
else
    # Linux cluster nodes (standard GCC)
    CXX = g++
    CXXFLAGS = -std=c++17 -O3 -march=native -flto -Wall -Wextra -DNDEBUG -fopenmp -Iinclude
    LDFLAGS = -lzstd -flto -fopenmp
endif

BUILD = build

# Solver driver: solve-pair / verify-pair / compress / root
SOLVER_SRCS = src/Main.cpp src/Solver.cpp src/Compressor.cpp
SOLVER_OBJS = $(SOLVER_SRCS:src/%.cpp=$(BUILD)/%.o)

all: $(BUILD)/bestemshe $(BUILD)/query $(BUILD)/generateTasks $(BUILD)/generateVictory

$(BUILD):
	@mkdir -p $(BUILD)

$(BUILD)/bestemshe: $(SOLVER_OBJS) | $(BUILD)
	@echo "[LINKING for $(UNAME_S)] bestemshe..."
	$(CXX) $(SOLVER_OBJS) -o $@ $(LDFLAGS)

# Tablebase explorer CLI (mmap single-block reader, no solver deps)
$(BUILD)/query: src/query.cpp include/Oracle.h include/StateIndex.h include/BestemsheCore.h | $(BUILD)
	@echo "[BUILDING] query..."
	$(CXX) $(CXXFLAGS) src/query.cpp -o $@ $(LDFLAGS)

# Puzzle extractors (drive tasks/generate_puzzles.py)
$(BUILD)/generateTasks: src/generateTasks.cpp $(BUILD)/Compressor.o | $(BUILD)
	@echo "[BUILDING] generateTasks..."
	$(CXX) $(CXXFLAGS) src/generateTasks.cpp $(BUILD)/Compressor.o -o $@ $(LDFLAGS)

$(BUILD)/generateVictory: src/generateVictory.cpp $(BUILD)/Compressor.o | $(BUILD)
	@echo "[BUILDING] generateVictory..."
	$(CXX) $(CXXFLAGS) src/generateVictory.cpp $(BUILD)/Compressor.o -o $@ $(LDFLAGS)

$(BUILD)/%.o: src/%.cpp | $(BUILD)
	@echo "[COMPILING] $<..."
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	@echo "[CLEANING] Removing build directory..."
	rm -rf $(BUILD)

.PHONY: all clean
