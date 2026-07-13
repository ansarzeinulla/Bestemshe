"""Bestemshe Tablebase Explorer — Gradio UI over the C++ mmap query CLI."""

import json
import os
import shutil
import subprocess

import gradio as gr

QUERY_BIN = os.environ.get("BESTEMSHE_QUERY_BIN", "./query")
DATA_DIR = os.environ.get("BESTEMSHE_DATA_DIR", "layers/compressed")
START_POSITION = "0 0 5 5 5 5 5 5 5 5 5 5"

RESULT_LABEL = {
    "WIN": "✅ Win",
    "DRAW": "➖ Draw",
    "LOSS": "❌ Loss",
    "INVALID": "— (empty pit)",
}


def parse_fields(text: str):
    parts = text.split()
    if len(parts) != 12:
        raise ValueError("Expected 12 space-separated integers: K1 K2 p0 .. p9")
    try:
        vals = [int(p) for p in parts]
    except ValueError:
        raise ValueError("All 12 fields must be integers")
    if any(v < 0 or v > 50 for v in vals):
        raise ValueError("Each field must be between 0 and 50")
    if sum(vals) != 50:
        raise ValueError(f"Stones must total 50 (got {sum(vals)})")
    return vals


def board_html(k1: int, k2: int, pits: list, title: str = "") -> str:
    """Render the board: mover's pits (p0-p4) on the bottom row."""
    def pit_cells(indices, css):
        cells = ""
        for i in indices:
            cells += (
                f"<div class='pit {css}'><span class='count'>{pits[i]}</span>"
                f"<span class='label'>p{i}</span></div>"
            )
        return cells

    return f"""
    <style>
      .bboard {{ font-family: sans-serif; max-width: 560px; margin: 8px auto;
                 background: #7c4a1e; border-radius: 16px; padding: 14px; }}
      .bboard .rows {{ display: flex; flex-direction: column; gap: 10px; }}
      .bboard .row {{ display: flex; gap: 8px; justify-content: center; }}
      .bboard .pit {{ width: 64px; height: 64px; border-radius: 50%;
                      display: flex; flex-direction: column; align-items: center;
                      justify-content: center; color: #fff; }}
      .bboard .pit.opp  {{ background: #4a2c10; }}
      .bboard .pit.self {{ background: #a86a32; }}
      .bboard .count {{ font-size: 22px; font-weight: bold; }}
      .bboard .label {{ font-size: 10px; opacity: 0.75; }}
      .bboard .kazan {{ display: flex; justify-content: space-between;
                        color: #ffe9c9; font-weight: bold; padding: 4px 10px; }}
      .bboard h4 {{ color: #ffe9c9; text-align: center; margin: 2px 0 8px 0; }}
    </style>
    <div class="bboard">
      {f"<h4>{title}</h4>" if title else ""}
      <div class="kazan"><span>Opponent kazan: {k2}</span></div>
      <div class="rows">
        <div class="row">{pit_cells([9, 8, 7, 6, 5], "opp")}</div>
        <div class="row">{pit_cells([0, 1, 2, 3, 4], "self")}</div>
      </div>
      <div class="kazan"><span>Side to move — kazan: {k1}</span></div>
    </div>
    """


def analyze(position: str):
    try:
        vals = parse_fields(position)
    except ValueError as e:
        return f"<p style='color:red'>⚠️ {e}</p>", [], "Invalid input"

    if not (os.path.isfile(QUERY_BIN) and os.access(QUERY_BIN, os.X_OK)) and not shutil.which(QUERY_BIN):
        return "<p style='color:red'>⚠️ query binary not found — build it with `make query`.</p>", [], "Setup error"

    env = dict(os.environ, BESTEMSHE_DATA_DIR=DATA_DIR)
    try:
        proc = subprocess.run(
            [QUERY_BIN] + [str(v) for v in vals],
            capture_output=True, text=True, timeout=60, env=env,
        )
        data = json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        return "<p style='color:red'>⚠️ Query timed out.</p>", [], "Error"
    except (json.JSONDecodeError, OSError) as e:
        return f"<p style='color:red'>⚠️ Failed to run query: {e}</p>", [], "Error"

    if "error" in data:
        return f"<p style='color:red'>⚠️ {data['error']}</p>", [], "Error"

    pos = data["position"]
    html = board_html(pos["K1"], pos["K2"], pos["board"])

    rows = []
    for m in data["moves"]:
        result = RESULT_LABEL.get(m["result"], m["result"])
        child = m.get("child")
        child_str = (
            f"K1={child['K1']} K2={child['K2']} " + " ".join(map(str, child["board"]))
            if child else "—"
        )
        rows.append([f"Pit {m['pit']}", result, child_str])

    verdict = {
        "WIN": "🏆 Side to move WINS with perfect play",
        "LOSS": "💀 Side to move LOSES with perfect play",
        "DRAW": "🤝 Perfect play is a DRAW",
    }.get(data["value"], data["value"])

    return html, rows, verdict


with gr.Blocks(title="Bestemshe Tablebase Explorer") as demo:
    gr.Markdown(
        "# 🎯 Bestemshe Tablebase Explorer\n"
        "Bestemshe (a Mancala variant) is **strongly solved**. Enter a position as 12 integers — "
        "`K1 K2 p0 p1 p2 p3 p4 p5 p6 p7 p8 p9` — from the side-to-move perspective "
        "(K1/p0–p4 = mover, K2/p5–p9 = opponent; stones must total 50, kazans even)."
    )
    position = gr.Textbox(label="Position", value=START_POSITION)
    analyze_btn = gr.Button("Analyze Position", variant="primary")
    verdict = gr.Textbox(label="Oracle verdict", interactive=False)
    board = gr.HTML(board_html(0, 0, [5] * 10))
    moves = gr.Dataframe(
        headers=["Move", "Result (for mover)", "Resulting position"],
        interactive=False,
    )
    analyze_btn.click(analyze, inputs=position, outputs=[board, moves, verdict])
    position.submit(analyze, inputs=position, outputs=[board, moves, verdict])

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)))
