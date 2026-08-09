cmake_minimum_required(VERSION 3.16)
project(bestemshe_solver LANGUAGES CXX)

# ==============================================================================
# Bestemshe HPC engine — parallel retrograde tablebase solver
#
# Targets:
#   bestemshe        solve / verify / compress driver (OpenMP required)
#   query            O(1) mmap tablebase explorer CLI (no OpenMP)
#   generateTasks    puzzle extractor: mate / atsyrau / capture / loop
#   generateVictory  forced-win-in-1 extractor
#
# Build:
#   cmake -S cpp_solver -B build && cmake --build build -j
#
# On macOS, AppleClang ships without an OpenMP runtime. Either install it
# (brew install libomp) or point CMake at Homebrew GCC:
#   cmake -S cpp_solver -B build -DCMAKE_CXX_COMPILER=g++-16
# ==============================================================================

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})

# ------------------------------------------------------------------ zstd
# Prefer the CMake package; fall back to a plain header/library probe so the
# cluster nodes (libzstd-dev via apt) work without zstd's own config files.
find_package(zstd QUIET)
if(TARGET zstd::libzstd_shared)
  set(ZSTD_LINK zstd::libzstd_shared)
elseif(TARGET zstd::libzstd_static)
  set(ZSTD_LINK zstd::libzstd_static)
else()
  find_path(ZSTD_INCLUDE_DIR zstd.h HINTS /opt/homebrew/include /usr/local/include)
  find_library(ZSTD_LIBRARY NAMES zstd HINTS /opt/homebrew/lib /usr/local/lib)
  if(NOT ZSTD_INCLUDE_DIR OR NOT ZSTD_LIBRARY)
    message(FATAL_ERROR
      "zstd not found. macOS: brew install zstd. Debian/Ubuntu: apt install libzstd-dev.")
  endif()
  add_library(zstd_fallback INTERFACE)
  target_include_directories(zstd_fallback INTERFACE ${ZSTD_INCLUDE_DIR})
  target_link_libraries(zstd_fallback INTERFACE ${ZSTD_LIBRARY})
  set(ZSTD_LINK zstd_fallback)
endif()

# ---------------------------------------------------------------- OpenMP
# Only the retrograde sweep in Solver.cpp is parallel, so the explorer and the
# puzzle extractors still build on a toolchain without an OpenMP runtime.
#
# AppleClang ships no OpenMP runtime of its own, so point CMake at Homebrew's
# libomp before probing. Without this the default macOS toolchain silently falls
# back to a single-threaded solve.
if(APPLE)
  find_package(OpenMP QUIET COMPONENTS CXX)
  if(NOT OpenMP_CXX_FOUND)
    execute_process(COMMAND brew --prefix libomp
                    OUTPUT_VARIABLE LIBOMP_PREFIX
                    OUTPUT_STRIP_TRAILING_WHITESPACE
                    ERROR_QUIET)
    if(LIBOMP_PREFIX AND EXISTS "${LIBOMP_PREFIX}/include/omp.h")
      set(OpenMP_CXX_FLAGS "-Xpreprocessor -fopenmp -I${LIBOMP_PREFIX}/include")
      set(OpenMP_CXX_LIB_NAMES "omp")
      set(OpenMP_omp_LIBRARY "${LIBOMP_PREFIX}/lib/libomp.dylib")
    endif()
  endif()
endif()
find_package(OpenMP QUIET COMPONENTS CXX)

# ----------------------------------------------------------------- common
# Header-only core shared by every target: state encoding, colexicographical
# ranking, ZSTD block container, layer cache.
add_library(bestemshe_core INTERFACE)
target_include_directories(bestemshe_core INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_options(bestemshe_core INTERFACE -O3 -Wall -Wextra)
target_compile_definitions(bestemshe_core INTERFACE NDEBUG)

# ---------------------------------------------------------------- targets
add_executable(bestemshe src/Main.cpp src/Solver.cpp src/Compressor.cpp)
target_link_libraries(bestemshe PRIVATE bestemshe_core ${ZSTD_LINK})
if(OpenMP_CXX_FOUND)
  target_link_libraries(bestemshe PRIVATE OpenMP::OpenMP_CXX)
else()
  message(WARNING
    "OpenMP not found: 'bestemshe' will solve single-threaded. "
    "macOS: brew install libomp, or configure with -DCMAKE_CXX_COMPILER=g++-16.")
endif()

add_executable(query src/query.cpp)
target_link_libraries(query PRIVATE bestemshe_core ${ZSTD_LINK})

add_executable(generateTasks src/generateTasks.cpp src/Compressor.cpp)
target_link_libraries(generateTasks PRIVATE bestemshe_core ${ZSTD_LINK})

add_executable(generateVictory src/generateVictory.cpp src/Compressor.cpp)
target_link_libraries(generateVictory PRIVATE bestemshe_core ${ZSTD_LINK})
