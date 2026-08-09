#!/usr/bin/env python3
"""
generate_book.py — Bestemshe PDF Puzzle Book generator (numeric diagram).

Reads a schema-v3 book ({"meta": ..., "tasks": [...]}, as written by
collect_tasks.py) and produces a printable A5-landscape puzzle book: 3x2
puzzles per page, alternating binding gutter (odd pages: 15% left margin, even
pages: 15% right margin, other sides 5%), plus a Solutions section at the end.

Each cell is drawn as a square holding the stone COUNT. For the pictorial
version that draws the stones as circles, see generate_book_circles.py, which
reuses the loading and page-layout helpers from this module.

Usage:
    python3 generate_book.py [--input puzzles/book_v3.json]
                             [--output bestemshe_puzzle_book.pdf]
"""
import argparse
import json
from dataclasses import dataclass

from reportlab.lib.pagesizes import A5, landscape
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas as pdfcanvas

PAGE_W, PAGE_H = landscape(A5)

INK = HexColor("#000000")
DIM = HexColor("#000000")
PIT_FILL = HexColor("#ffffff")
PIT_EDGE = HexColor("#000000")
BLACK_ROW = HexColor("#ffffff")


@dataclass
class Board:
    white_pits: list  # pits 0..4 (bottom, White to move)
    black_pits: list  # pits 5..9
    k_white: int
    k_black: int


def parse_fen(fen: str) -> Board:
    """FEN: p0,..,p4/p5,..,p9 K1,K2 w M"""
    board_part, kazans, _active, _turn = fen.split(" ")
    white_s, black_s = board_part.split("/")
    kw, kb = kazans.split(",")
    return Board(
        white_pits=[int(x) for x in white_s.split(",")],
        black_pits=[int(x) for x in black_s.split(",")],
        k_white=int(kw),
        k_black=int(kb),
    )


def load_book(path):
    """Loads a schema-v3 book, returning (meta, tasks)."""
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):          # bare array from ./generateTasks
        return {}, data
    return data.get("meta", {}), data["tasks"]


def assign_ids(tasks):
    """Uses the ids written by collect_tasks.py, falling back to book order."""
    return [t.get("id") or f"#A{i + 1}" for i, t in enumerate(tasks)]


TYPE_LABEL = {
    "mate": "mate in {n}",
    "atsyrau": "atsyrau in {n}",
    "capture_total": "take {k}+ in {n}",
    "capture_single": "take {k}+ at once in {n}",
    "loop": "hold the draw",
}


def task_label(task):
    """Short human-readable goal, e.g. 'take 6+ in 2'."""
    spec = task.get("task", {})
    return TYPE_LABEL.get(spec.get("type"), spec.get("type", "")).format(
        n=spec.get("n", ""), k=spec.get("k", ""))


def solution_text(task):
    """One-line solution: the first move(s), or the opening of a loop line."""
    sols = task.get("solutions") or []
    if not sols:
        # v2 books stored the single winning move under "notation".
        return task.get("notation", "-")
    if "line" in sols[0]:               # loop task: show the start of the line
        line = sols[0]["line"]
        shown = " ".join(line[:6])
        return shown + (" ..." if len(line) > 6 else "")
    return " / ".join(s["first_move"] for s in sols)


def page_frame(page_num: int):
    """Usable rect (x, y, w, h). Odd pages: fat left margin; even: fat right."""
    reg_x, fat_x = 0.05 * PAGE_W, 0.15 * PAGE_W
    reg_y = 0.05 * PAGE_H
    left = fat_x if page_num % 2 == 1 else reg_x
    right = reg_x if page_num % 2 == 1 else fat_x
    return left, reg_y, PAGE_W - left - right, PAGE_H - 2 * reg_y


def draw_page_number(c, page_num):
    """Odd pages: bottom-right. Even pages: bottom-left."""
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 14)
    if page_num % 2 == 1:
        c.drawRightString(PAGE_W - 0.02 * PAGE_W, 0.02 * PAGE_H, str(page_num))
    else:
        c.drawString(0.02 * PAGE_W, 0.02 * PAGE_H, str(page_num))


def draw_board(c, x, y, w, h, board: Board):
    """Square-cell table board inside rect (x, y, w, h):

        row 0 (top):    black kazan square above the middle column
        row 1:          5 black pit squares (pits 9..5, left to right)
        row 2:          5 white pit squares (pits 0..4)
        row 3 (bottom): white kazan square below the middle column
    """
    cell = min(w / 5, h / 4)
    bx = x + (w - 5 * cell) / 2       # center the 5-column table
    by = y + (h - 4 * cell) / 2
    board_top = by + 4 * cell

    def draw_square(col, row_from_top, count, shaded, kazan=False):
        sx = bx + col * cell
        sy = by + (3 - row_from_top) * cell
        c.setFillColor(BLACK_ROW if shaded else PIT_FILL)
        c.setStrokeColor(PIT_EDGE)
        c.setLineWidth(1)
        c.rect(sx, sy, cell, cell, stroke=1, fill=1)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", cell * 0.55)
        c.drawCentredString(sx + cell / 2, sy + cell / 2 - cell * 0.19, str(count))

    draw_square(2, 0, board.k_black, True, kazan=True)          # black kazan
    for i in range(5):
        draw_square(i, 1, board.black_pits[4 - i], True)        # pits 9..5
        draw_square(i, 2, board.white_pits[i], False)           # pits 0..4
    draw_square(2, 3, board.k_white, False, kazan=True)         # white kazan
    return board_top


def display_board(task):
    """Canonical FEN is mover-relative. White to move: mover = white row.
    Black to move: rotate — mover's pits/kazan go to the black (top) row."""
    b = parse_fen(task["fen"])
    if task["color"] == "w":
        return b
    return Board(white_pits=b.black_pits, black_pits=b.white_pits,
                 k_white=b.k_black, k_black=b.k_white)


def draw_puzzle_cell(c, x, y, w, h, puzzle_id, task, board_drawer=None):
    """Draws one puzzle. `board_drawer(c, x, y, w, h, board) -> board_top`
    defaults to the numeric table; the circle book passes its own."""
    board_drawer = board_drawer or draw_board
    label_h = h * 0.13          # room for the id line plus the goal line
    pad = w * 0.03
    board_top = board_drawer(c, x + pad, y, w - 2 * pad, h - label_h,
                             display_board(task))
    # ID + turn-indicator square sit directly above the board table
    font_sz = label_h * 0.55
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", font_sz)
    text_w = c.stringWidth(puzzle_id, "Helvetica-Bold", font_sz)
    sq = font_sz * 0.9
    total = text_w + font_sz * 0.5 + sq
    tx = x + w / 2 - total / 2
    ty = board_top + label_h * 0.66
    c.drawString(tx, ty, puzzle_id)
    c.setStrokeColor(INK)
    c.setLineWidth(1.2)
    c.rect(tx + text_w + font_sz * 0.5, ty - sq * 0.12, sq, sq,
           stroke=1, fill=1 if task["color"] == "b" else 0)
    # Goal ("mate in 2", "take 6+ in 2", ...) sits just under the id line.
    goal = task_label(task)
    if goal:
        c.setFont("Helvetica", font_sz * 0.72)
        c.drawCentredString(x + w / 2, board_top + label_h * 0.20, goal)


def render_book(puzzles, output, board_drawer=None, title="Bestemshe Puzzle Book"):
    """Renders the puzzle pages + solutions section to `output`."""
    ids = assign_ids(puzzles)

    c = pdfcanvas.Canvas(output, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(title)

    COLS, ROWS = 3, 2
    page_num = 1

    # ---------- Puzzle pages ----------
    for start in range(0, len(puzzles), COLS * ROWS):
        chunk = list(zip(ids[start:start + COLS * ROWS],
                         puzzles[start:start + COLS * ROWS]))
        fx, fy, fw, fh = page_frame(page_num)
        cell_w, cell_h = fw / COLS, fh / ROWS
        gap = min(cell_w, cell_h) * 0.06

        for j, (pid, p) in enumerate(chunk):
            col, row = j % COLS, j // COLS
            cx = fx + col * cell_w
            cy = fy + fh - (row + 1) * cell_h  # top row first
            draw_puzzle_cell(c, cx + gap / 2, cy + gap / 2,
                             cell_w - gap, cell_h - gap, pid, p, board_drawer)

        draw_page_number(c, page_num)
        c.showPage()
        page_num += 1

    # ---------- Solutions section ----------
    font_sz, line_h = 10, 14
    lines = [f"{ids[i]} — {'1.' if p['color'] == 'w' else '1...'} {solution_text(p)}"
             for i, p in enumerate(puzzles)]
    # Pick a column count that actually fits the longest solution (loop lines
    # are far wider than a single move).
    widest = max(c.stringWidth(s, "Helvetica", font_sz) for s in lines)
    _, _, frame_w, _ = page_frame(1)
    sol_cols = max(1, min(6, int(frame_w // (widest * 1.08))))

    i = 0
    while i < len(lines):
        fx, fy, fw, fh = page_frame(page_num)
        top = fy + fh
        rows_per_col = int((top - fy) // line_h)
        col_w = fw / sol_cols
        c.setFont("Helvetica", font_sz)
        for col in range(sol_cols):
            for r in range(rows_per_col):
                if i >= len(lines):
                    break
                c.setFillColor(INK)
                c.drawString(fx + col * col_w, top - (r + 1) * line_h, lines[i])
                i += 1
        draw_page_number(c, page_num)
        c.showPage()
        page_num += 1

    c.save()
    print(f"[DONE] {len(puzzles)} puzzles -> {output} ({page_num - 1} pages)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="puzzles/book_v3.json")
    ap.add_argument("--output", default="bestemshe_puzzle_book.pdf")
    args = ap.parse_args()

    _meta, puzzles = load_book(args.input)
    render_book(puzzles, args.output)


if __name__ == "__main__":
    main()
