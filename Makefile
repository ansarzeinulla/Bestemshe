# ==============================================================================
# BESTEMSHE HPC ENGINE - AUTO-DETECTING MAKEFILE (HOMEBREW GCC)
# ==============================================================================

# Detect Operating System
UNAME_S := $(shell uname -s)

ifeq ($(UNAME_S),Darwin)
    # --------------------------------------------------------------------------
    # macOS with Homebrew GCC (Adjust 'g++-16' if your installed version differs)
    # --------------------------------------------------------------------------
    CXX = g++-16
    CXXFLAGS = -std=c++17 -O3 -flto -Wall -Wextra -DNDEBUG -fopenmp -I/opt/homebrew/include
    LDFLAGS = -L/opt/homebrew/lib -lzstd -flto -fopenmp
else
    # --------------------------------------------------------------------------
    # Linux (Tomorrow School / Alem.ai Cluster Nodes - standard GCC)
    # --------------------------------------------------------------------------
    CXX = g++
    CXXFLAGS = -std=c++17 -O3 -march=native -flto -Wall -Wextra -DNDEBUG -fopenmp
    LDFLAGS = -lzstd -flto -fopenmp
endif

# Target Executable
TARGET = bestemshe

# Source Files (Inference.cpp and Splitter.cpp are removed)
SRCS = main.cpp Solver.cpp Compressor.cpp
OBJS = $(SRCS:.cpp=.o)

# Default Rule
all: $(TARGET)

# Tablebase Explorer CLI (mmap single-block reader, no solver deps)
query: query.cpp Oracle.h StateIndex.h BestemsheCore.h
	@echo "[BUILDING] query..."
	$(CXX) $(CXXFLAGS) query.cpp -o query $(LDFLAGS)
	@echo "[SUCCESS] Build complete: ./query"

# Linking
$(TARGET): $(OBJS)
	@echo "[LINKING for $(UNAME_S)] $(TARGET)..."
	$(CXX) $(OBJS) -o $(TARGET) $(LDFLAGS)
	@echo "[SUCCESS] Build complete: ./$(TARGET)"

# Compilation
%.o: %.cpp
	@echo "[COMPILING] $<..."
	$(CXX) $(CXXFLAGS) -c $< -o $@

# Clean Up
clean:
	@echo "[CLEANING] Removing object files and binary..."
	rm -f $(OBJS) $(TARGET) query

.PHONY: all clean