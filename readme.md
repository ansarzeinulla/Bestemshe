clang++ -std=c++17 -O3 -march=native -Wno-unknown-pragmas main.cpp -o main

./main --level 48
./main --level 46
./main --level 44
./main --level 42
./main --level 40
./main --level 38
./main --level 36
./main --level 34
./main --level 32
./main --level 30

The solver now uses retrograde value iteration and writes two files per layer:

- `layers/layerM.bin` for winning states
- `layers/layerM_draw.bin` for draw states

The solver keeps iterating until no new wins or losses can be proven. Anything left after convergence is treated as a perfect-play draw.
