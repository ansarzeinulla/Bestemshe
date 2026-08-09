#!/usr/bin/env python3
"""
generate_book_circles.py — Bestemshe PDF Puzzle Book, pictorial diagram.

Same book as generate_book.py (page geometry, ids, colours and the solutions
section are all imported from it), but each cell shows the kumalaks as physical
black circles instead of a number.

Diagram layout — four rows, top to bottom:

    row 0   black's kazan   one box spanning the whole 5-cell width
    row 1   black's cells   5 boxes
    row 2   white's cells   5 boxes
    row 3   white's kazan   one box spanning the whole 5-cell width

Stones stack in TWO columns inside every box, filling bottom-up, so a box
holding n stones is ceil(n / 2) circles tall. Each row's height is therefore
flexible: it is set by the fullest box in that row. The four heights are then
scaled together to fit the space available, so crowded positions get smaller
circles rather than overflowing.

Usage:
    python3 generate_book_circles.py [--input puzzles/book_v3.json]
                                     [--output bestemshe_puzzle_book_circles.pdf]
"""
import argparse
import math

from generate_book import (INK, PIT_EDGE, PIT_FILL, BLACK_ROW,
                           load_book, render_book)

COLS = 5          # cells per player row
STONE_COLS = 2    # circle columns inside one playing cell
# A kazan box spans all five cells, so it gets five cells' worth of columns —
# otherwise a 24-stone kazan would be 12 rows tall and dwarf the playing rows.
KAZAN_COLS = COLS * STONE_COLS


def _rows_needed(count, ncols=STONE_COLS):
    """How many circle rows a box needs; empty boxes still occupy one."""
    return max(1, math.ceil(count / ncols))


def _draw_stones(c, x, y, w, h, count, diameter, ncols=STONE_COLS):
    """Fills a box with `count` circles in `ncols` columns, bottom-up, centred."""
    if count <= 0:
        return
    rows = _rows_needed(count, ncols)
    gap = diameter * 0.18
    step = diameter + gap
    block_h = rows * step - gap
    y0 = y + (h - block_h) / 2 + diameter / 2

    c.setFillColor(INK)
    c.setStrokeColor(INK)
    for i in range(count):
        r, col = divmod(i, ncols)
        # The last row is often short; centre it across the full column span.
        in_row = min(ncols, count - r * ncols)
        row_w = in_row * step - gap
        x0 = x + (w - row_w) / 2 + diameter / 2
        c.circle(x0 + col * step, y0 + r * step, diameter / 2, stroke=0, fill=1)


def draw_board_circles(c, x, y, w, h, board):
    """Draws the pictorial board inside (x, y, w, h); returns its top edge."""
    counts_black = [board.black_pits[4 - i] for i in range(COLS)]  # pits 9..5
    counts_white = list(board.white_pits)                          # pits 0..4

    # Each row is as tall as its fullest cell.
    row_units = [
        _rows_needed(board.k_black, KAZAN_COLS),
        max(_rows_needed(n) for n in counts_black),
        max(_rows_needed(n) for n in counts_white),
        _rows_needed(board.k_white, KAZAN_COLS),
    ]

    cell_w = w / COLS
    # Pick the circle size that makes the four rows fit both dimensions.
    pad_frac = 0.16                      # vertical padding inside a box, in steps
    total_units = sum(row_units) + 4 * pad_frac
    step_by_h = h / total_units
    step_by_w = cell_w / (STONE_COLS + 0.7)   # keep 2 columns clear of the edges
    step = min(step_by_h, step_by_w)
    diameter = step / 1.18               # step = diameter + 0.18 * diameter

    row_h = [u * step + pad_frac * step for u in row_units]
    board_h = sum(row_h)
    by = y + (h - board_h) / 2           # centre vertically
    bx = x + (w - COLS * cell_w) / 2

    def box(px, py, pw, ph, count, shaded, ncols=STONE_COLS):
        c.setFillColor(BLACK_ROW if shaded else PIT_FILL)
        c.setStrokeColor(PIT_EDGE)
        c.setLineWidth(1)
        c.rect(px, py, pw, ph, stroke=1, fill=1)
        _draw_stones(c, px, py, pw, ph, count, diameter, ncols)

    # Rows are laid out top-down, so accumulate y from the top edge.
    top = by + board_h
    y0 = top - row_h[0]
    box(bx, y0, COLS * cell_w, row_h[0], board.k_black, True, KAZAN_COLS)   # black kazan

    y1 = y0 - row_h[1]
    for i in range(COLS):
        box(bx + i * cell_w, y1, cell_w, row_h[1], counts_black[i], True)

    y2 = y1 - row_h[2]
    for i in range(COLS):
        box(bx + i * cell_w, y2, cell_w, row_h[2], counts_white[i], False)

    y3 = y2 - row_h[3]
    box(bx, y3, COLS * cell_w, row_h[3], board.k_white, False, KAZAN_COLS)  # white kazan

    return top


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="puzzles/book_v3.json")
    ap.add_argument("--output", default="bestemshe_puzzle_book_circles.pdf")
    args = ap.parse_args()

    _meta, puzzles = load_book(args.input)
    render_book(puzzles, args.output, board_drawer=draw_board_circles,
                title="Bestemshe Puzzle Book (circles)")


if __name__ == "__main__":
    main()
