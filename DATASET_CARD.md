---
license: cc-by-nc-4.0
task_categories:
- reinforcement-learning
language:
- en
tags:
- Bestemshe
- Togyzkumalak
- Togyzqumalaq
- Mancala
- Game-Theory
- Retrograde-Analysis
- Tablebase
- Strong-Solution
pretty_name: Bestemshe TableBase — Strong Solution Proof
size_categories:
- 10B<n<100B
---

# Bestemshe Table Base — Strong Solution Proof

**Authors:** Ansar Zeinulla & Murat Manassov  
**Affiliation:** Nazarbayev University, Kazakhstan  
**Code Repository:** [github.com/ansarzeinulla/Bestemshe](https://github.com/ansarzeinulla/Bestemshe)  
**Live Interactive Explorer:** [huggingface.co/spaces/ansarzeinulla/Bestemshe-God-Algorithm](https://huggingface.co/spaces/ansarzeinulla/bestemshe-god-algorithm)

Bestemshe is a traditional Kazakh two-player mancala-style game (5 pits per player, 50 total stones). This artifact is a **strong solution** of the game: for every reachable, legal position the exact game-theoretic value (win / draw for the side to move) has been computed by retrograde analysis and stored, enabling perfect play via direct $O(1)$ memory-mapped lookup without runtime search. 

Together with the solver that produced it, this tablebase constitutes a machine-verifiable proof of the game's outcome under optimal play: **a forced win for the second player (Follower)**.

---

## Game Encoding

A position is described by the two Kazans (captured-stone stores) `K1` (side to move) and `K2` (opponent), and ten pits of `0..N` stones. The 50 stones are conserved:
$$\sum_{i=1}^{10} \text{pits}[i] + K_1 + K_2 = 50$$

Captures are strictly even, so each Kazan score is an even integer. A Kazan reaching $\ge 26$ decides the game immediately and lies outside the stored range ($0 \le K_1, K_2 \le 24$). Positions are stored canonically from the **side-to-move** perspective.

---

## Layer Layout

The tablebase is sharded into **layers indexed by the Kazan pair `(K1, K2)`**, where each Kazan is even in $0..24$ ($13 \times 13 = 169$ pairs). Every pair consists of two Zstandard-compressed bitset files:

- `layer_<K1>_<K2>_win.bin.zst` — The WIN/LOSS bitset for that layer.
- `layer_<K1>_<K2>_draw.bin.zst` — The DRAW bitset for that layer.

Files are Zstandard-compressed bitsets indexed by a combinatorial ranking of the pit configuration (`StateIndex`).

---

## Summary Statistics

| Metric | Value |
| :--- | :--- |
| **Layer pairs `(K1, K2)`** | 169 |
| **Total files** | 338 (169 win + 169 draw) |
| **WIN files total size** | 6.0 GB |
| **DRAW files total size** | 2.4 GB |
| **Grand Total Size** | **8.3 GB** (8,962,782,421 bytes) |

---

## How to Query (Quickstart)

```python
import zstandard as zstd

# Example: Loading a specific layer in Python
def load_layer(k1, k2, result_type="win"):
    filename = f"data/layer_{k1}_{k2}_{result_type}.bin.zst"
    with open(filename, 'rb') as fh:
        dctx = zstd.ZstdDecompressor()
        decompressed_data = dctx.decompress(fh.read())
    return decompressed_data

# Query bit at index
def is_winning_state(decompressed_bytes, state_index):
    byte_idx = state_index // 8
    bit_idx = state_index % 8
    return bool((decompressed_bytes[byte_idx] >> bit_idx) & 1)
```

## Per-layer file sizes

| K1 | K2 | win.bin | draw.bin |
| ---: | ---: | ---: | ---: |
| 0 | 0 | 960.4 MB | 394.1 MB |
| 0 | 2 | 755.2 MB | 287.9 MB |
| 0 | 4 | 456.0 MB | 164.6 MB |
| 0 | 6 | 238.7 MB | 87.6 MB |
| 0 | 8 | 114.8 MB | 44.0 MB |
| 0 | 10 | 52.5 MB | 20.3 MB |
| 0 | 12 | 23.8 MB | 8.3 MB |
| 0 | 14 | 11.6 MB | 3.1 MB |
| 0 | 16 | 6.3 MB | 978.9 KB |
| 0 | 18 | 3.5 MB | 252.9 KB |
| 0 | 20 | 1.9 MB | 64.5 KB |
| 0 | 22 | 828.4 KB | 11.0 KB |
| 0 | 24 | 202.5 KB | 455.0 B |
| 2 | 0 | 440.9 MB | 188.7 MB |
| 2 | 2 | 487.8 MB | 204.0 MB |
| 2 | 4 | 367.9 MB | 143.3 MB |
| 2 | 6 | 212.7 MB | 79.0 MB |
| 2 | 8 | 106.5 MB | 39.8 MB |
| 2 | 10 | 49.4 MB | 18.6 MB |
| 2 | 12 | 22.4 MB | 7.8 MB |
| 2 | 14 | 10.8 MB | 2.9 MB |
| 2 | 16 | 5.7 MB | 922.9 KB |
| 2 | 18 | 3.1 MB | 236.7 KB |
| 2 | 20 | 1.6 MB | 59.2 KB |
| 2 | 22 | 702.7 KB | 10.5 KB |
| 2 | 24 | 160.6 KB | 306.0 B |
| 4 | 0 | 149.2 MB | 63.0 MB |
| 4 | 2 | 220.2 MB | 96.1 MB |
| 4 | 4 | 233.8 MB | 99.9 MB |
| 4 | 6 | 168.5 MB | 67.0 MB |
| 4 | 8 | 93.1 MB | 35.0 MB |
| 4 | 10 | 44.9 MB | 16.5 MB |
| 4 | 12 | 20.6 MB | 7.0 MB |
| 4 | 14 | 9.9 MB | 2.7 MB |
| 4 | 16 | 5.1 MB | 856.7 KB |
| 4 | 18 | 2.7 MB | 217.5 KB |
| 4 | 20 | 1.4 MB | 53.2 KB |
| 4 | 22 | 561.6 KB | 9.3 KB |
| 4 | 24 | 123.9 KB | 157.0 B |
| 6 | 0 | 43.6 MB | 17.2 MB |
| 6 | 2 | 72.5 MB | 31.4 MB |
| 6 | 4 | 103.6 MB | 45.9 MB |
| 6 | 6 | 104.9 MB | 45.7 MB |
| 6 | 8 | 71.8 MB | 28.9 MB |
| 6 | 10 | 38.1 MB | 14.1 MB |
| 6 | 12 | 18.1 MB | 6.1 MB |
| 6 | 14 | 8.7 MB | 2.4 MB |
| 6 | 16 | 4.4 MB | 756.5 KB |
| 6 | 18 | 2.3 MB | 195.4 KB |
| 6 | 20 | 1.1 MB | 46.3 KB |
| 6 | 22 | 426.8 KB | 7.5 KB |
| 6 | 24 | 91.1 KB | 157.0 B |
| 8 | 0 | 12.7 MB | 4.5 MB |
| 8 | 2 | 20.5 MB | 8.2 MB |
| 8 | 4 | 33.4 MB | 14.6 MB |
| 8 | 6 | 45.6 MB | 20.4 MB |
| 8 | 8 | 43.5 MB | 19.2 MB |
| 8 | 10 | 28.2 MB | 11.3 MB |
| 8 | 12 | 14.5 MB | 5.1 MB |
| 8 | 14 | 7.1 MB | 2.0 MB |
| 8 | 16 | 3.6 MB | 650.7 KB |
| 8 | 18 | 1.8 MB | 168.6 KB |
| 8 | 20 | 855.6 KB | 38.3 KB |
| 8 | 22 | 306.1 KB | 6.5 KB |
| 8 | 24 | 66.4 KB | 157.0 B |
| 10 | 0 | 4.3 MB | 1.3 MB |
| 10 | 2 | 6.2 MB | 2.1 MB |
| 10 | 4 | 9.6 MB | 3.8 MB |
| 10 | 6 | 14.9 MB | 6.3 MB |
| 10 | 8 | 18.8 MB | 8.2 MB |
| 10 | 10 | 16.5 MB | 7.3 MB |
| 10 | 12 | 10.0 MB | 3.9 MB |
| 10 | 14 | 5.1 MB | 1.5 MB |
| 10 | 16 | 2.6 MB | 521.9 KB |
| 10 | 18 | 1.3 MB | 131.7 KB |
| 10 | 20 | 571.3 KB | 28.1 KB |
| 10 | 22 | 199.9 KB | 4.9 KB |
| 10 | 24 | 42.6 KB | 157.0 B |
| 12 | 0 | 2.0 MB | 371.6 KB |
| 12 | 2 | 2.4 MB | 596.9 KB |
| 12 | 4 | 3.3 MB | 990.2 KB |
| 12 | 6 | 4.8 MB | 1.7 MB |
| 12 | 8 | 6.7 MB | 2.6 MB |
| 12 | 10 | 7.3 MB | 2.9 MB |
| 12 | 12 | 5.5 MB | 2.2 MB |
| 12 | 14 | 3.1 MB | 1.0 MB |
| 12 | 16 | 1.6 MB | 334.4 KB |
| 12 | 18 | 752.9 KB | 79.0 KB |
| 12 | 20 | 316.2 KB | 13.6 KB |
| 12 | 22 | 108.6 KB | 3.0 KB |
| 12 | 24 | 25.5 KB | 157.0 B |
| 14 | 0 | 1.3 MB | 107.1 KB |
| 14 | 2 | 1.3 MB | 176.7 KB |
| 14 | 4 | 1.5 MB | 287.4 KB |
| 14 | 6 | 2.0 MB | 481.2 KB |
| 14 | 8 | 2.6 MB | 770.0 KB |
| 14 | 10 | 3.0 MB | 983.1 KB |
| 14 | 12 | 2.6 MB | 878.9 KB |
| 14 | 14 | 1.5 MB | 481.3 KB |
| 14 | 16 | 787.7 KB | 162.0 KB |
| 14 | 18 | 356.4 KB | 37.1 KB |
| 14 | 20 | 144.9 KB | 3.4 KB |
| 14 | 22 | 51.7 KB | 157.0 B |
| 14 | 24 | 12.1 KB | 157.0 B |
| 16 | 0 | 919.0 KB | 30.7 KB |
| 16 | 2 | 903.3 KB | 47.6 KB |
| 16 | 4 | 933.4 KB | 77.1 KB |
| 16 | 6 | 1.0 MB | 127.0 KB |
| 16 | 8 | 1.2 MB | 211.7 KB |
| 16 | 10 | 1.4 MB | 286.9 KB |
| 16 | 12 | 1.2 MB | 258.7 KB |
| 16 | 14 | 727.8 KB | 149.3 KB |
| 16 | 16 | 344.9 KB | 58.0 KB |
| 16 | 18 | 145.1 KB | 12.9 KB |
| 16 | 20 | 56.2 KB | 157.0 B |
| 16 | 22 | 19.6 KB | 157.0 B |
| 16 | 24 | 5.3 KB | 157.0 B |
| 18 | 0 | 663.0 KB | 6.8 KB |
| 18 | 2 | 620.0 KB | 11.2 KB |
| 18 | 4 | 595.9 KB | 18.1 KB |
| 18 | 6 | 609.5 KB | 32.1 KB |
| 18 | 8 | 672.2 KB | 53.9 KB |
| 18 | 10 | 697.9 KB | 76.3 KB |
| 18 | 12 | 555.7 KB | 64.2 KB |
| 18 | 14 | 316.9 KB | 32.5 KB |
| 18 | 16 | 140.8 KB | 12.9 KB |
| 18 | 18 | 55.5 KB | 157.0 B |
| 18 | 20 | 19.3 KB | 157.0 B |
| 18 | 22 | 6.3 KB | 157.0 B |
| 18 | 24 | 1.8 KB | 157.0 B |
| 20 | 0 | 457.5 KB | 2.5 KB |
| 20 | 2 | 407.7 KB | 3.0 KB |
| 20 | 4 | 371.0 KB | 5.8 KB |
| 20 | 6 | 354.0 KB | 11.2 KB |
| 20 | 8 | 349.6 KB | 18.7 KB |
| 20 | 10 | 318.2 KB | 21.5 KB |
| 20 | 12 | 226.6 KB | 13.3 KB |
| 20 | 14 | 122.3 KB | 3.5 KB |
| 20 | 16 | 53.4 KB | 157.0 B |
| 20 | 18 | 19.4 KB | 157.0 B |
| 20 | 20 | 6.1 KB | 157.0 B |
| 20 | 22 | 1.8 KB | 157.0 B |
| 20 | 24 | 609.0 B | 157.0 B |
| 22 | 0 | 255.1 KB | 720.0 B |
| 22 | 2 | 217.5 KB | 1.0 KB |
| 22 | 4 | 186.4 KB | 1.7 KB |
| 22 | 6 | 163.2 KB | 2.1 KB |
| 22 | 8 | 142.2 KB | 3.4 KB |
| 22 | 10 | 113.0 KB | 3.6 KB |
| 22 | 12 | 73.0 KB | 2.7 KB |
| 22 | 14 | 39.9 KB | 157.0 B |
| 22 | 16 | 17.6 KB | 157.0 B |
| 22 | 18 | 6.3 KB | 157.0 B |
| 22 | 20 | 1.9 KB | 157.0 B |
| 22 | 22 | 598.0 B | 157.0 B |
| 22 | 24 | 240.0 B | 157.0 B |
| 24 | 0 | 88.0 KB | 455.0 B |
| 24 | 2 | 67.2 KB | 306.0 B |
| 24 | 4 | 51.4 KB | 157.0 B |
| 24 | 6 | 40.3 KB | 157.0 B |
| 24 | 8 | 30.4 KB | 157.0 B |
| 24 | 10 | 21.3 KB | 157.0 B |
| 24 | 12 | 13.6 KB | 157.0 B |
| 24 | 14 | 7.8 KB | 157.0 B |
| 24 | 16 | 3.8 KB | 157.0 B |
| 24 | 18 | 1.6 KB | 157.0 B |
| 24 | 20 | 587.0 B | 157.0 B |
| 24 | 22 | 243.0 B | 157.0 B |
| 24 | 24 | 164.0 B | 157.0 B |


## Citation

If you use this tablebase, solver architecture, or game-theoretic proof in your research, please cite:

```Bibtex
@misc{zeinulla2026bestemshe,
  title={Strongly Solving Bestemshe: A 10-Gigabyte Retrograde Tablebase Proof},
  author={Zeinulla, Ansar and Manassov, Murat},
  year={2026},
  publisher={Hugging Face Datasets},
  howpublished={\url{https://huggingface.co/datasets/ansarzeinulla/bestemshe-tablebase}}
}
```