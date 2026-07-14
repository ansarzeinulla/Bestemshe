"""Bestemshe Tablebase Explorer — interactive perfect-play board over the C++ oracle."""

import json
import os
import subprocess
import tempfile

import gradio as gr

try:  # ZeroGPU Spaces require one @spaces.GPU entry point (a no-op for this CPU app)
    import spaces
    gpu_entry = spaces.GPU
except ImportError:
    def gpu_entry(fn):
        return fn

QUERY_BIN = os.environ.get("BESTEMSHE_QUERY_BIN", "./query")
DATA_DIR = os.environ.get("BESTEMSHE_DATA_DIR", "layers/compressed")
TABLEBASE_DATASET = os.environ.get("BESTEMSHE_DATASET", "ansarzeinulla/bestemshe-tablebase")

# Position as 12 integers: Bastaushi kazan, Kostaushi kazan, Bastaushi's 5 pits, Kostaushi's 5 pits.
START_POSITION = "0 0 5 5 5 5 5 5 5 5 5 5"


def ensure_tablebase():
    """The 8.96GB tablebase lives in a dataset repo (Space repos are capped at 1GB)."""
    if os.path.isdir(DATA_DIR) and any(f.endswith(".bin") for f in os.listdir(DATA_DIR)):
        return
    from huggingface_hub import snapshot_download
    print(f"[setup] downloading tablebase from {TABLEBASE_DATASET} ...")
    snapshot_download(repo_id=TABLEBASE_DATASET, repo_type="dataset", local_dir=".")
    print("[setup] tablebase ready.")


def ensure_query_binary():
    """On HF Gradio Spaces there is no Docker build step: compile at startup."""
    if os.path.isfile(QUERY_BIN) and os.access(QUERY_BIN, os.X_OK):
        return
    print("[setup] compiling query CLI...")
    subprocess.run(
        ["g++", "-std=c++17", "-O3", "-DNDEBUG", "query.cpp", "-o", "query", "-lzstd"],
        check=True,
    )
    print("[setup] query CLI ready.")


# --------------------------------------------------------------------------- #
# Core helpers
# --------------------------------------------------------------------------- #
def parse_fields(text: str):
    parts = text.split()
    if len(parts) != 12:
        raise ValueError("Enter 12 numbers: Bastaushi kazan, Kostaushi kazan, "
                         "Bastaushi's 5 pits, then Kostaushi's 5 pits.")
    try:
        vals = [int(p) for p in parts]
    except ValueError:
        raise ValueError("All 12 values must be whole numbers.")
    if any(v < 0 or v > 50 for v in vals):
        raise ValueError("Each number must be between 0 and 50.")
    if sum(vals) != 50:
        raise ValueError(f"The stones must add up to 50 (yours add up to {sum(vals)}).")
    if vals[0] % 2 or vals[1] % 2:
        raise ValueError("Kazan totals must be even (captures always take an even number).")
    if vals[0] > 24 or vals[1] > 24:
        raise ValueError("A kazan of 26+ means the game is already over — enter a live position.")
    return vals


def run_query(state_str: str):
    env = dict(os.environ, BESTEMSHE_DATA_DIR=DATA_DIR)
    proc = subprocess.run(
        [QUERY_BIN] + state_str.split(),
        capture_output=True, text=True, timeout=60, env=env,
    )
    return json.loads(proc.stdout)


def move_notation(m: dict) -> str:
    return f"{m['from']}{m['to']}" + ("+" if m["capture"] else "")


def result_label(mover_result: str, ply: int) -> str:
    """Convert a mover-relative result into an absolute Bastaushi/Kostaushi verdict."""
    if mover_result == "DRAW":
        return "Infinite Loop Draw"
    bastaushi_to_move = (ply % 2 == 0)
    mover_wins = (mover_result == "WIN")
    if mover_wins:
        return "Bastaushi WINS" if bastaushi_to_move else "Kostaushi WINS"
    return "Kostaushi WINS" if bastaushi_to_move else "Bastaushi WINS"


def absolute_view(state_str: str, ply: int):
    """Return (bastaushi_kazan, kostaushi_kazan, bastaushi_pits[5], kostaushi_pits[5])."""
    v = [int(x) for x in state_str.split()]
    k_mover, k_opp, board = v[0], v[1], v[2:]
    if ply % 2 == 0:  # Bastaushi to move == the canonical mover
        return k_mover, k_opp, board[0:5], board[5:10]
    return k_opp, k_mover, board[5:10], board[0:5]


def board_html(state_str: str, ply: int) -> str:
    bk, kk, bpits, kpits = absolute_view(state_str, ply)

    def circle(n):
        return f"<div class='pit'>{n}</div>"

    top = "".join(circle(n) for n in reversed(kpits))   # Kostaushi row
    bottom = "".join(circle(n) for n in bpits)          # Bastaushi row

    return f"""
    <style>
      .bb {{ font-family: system-ui, sans-serif; max-width: 560px; margin: 8px auto;
             background: linear-gradient(160deg, #fffdf2 0%, #fff2c2 100%);
             border: 2px solid #e9cf7a; border-radius: 20px; padding: 18px; }}
      .bb .kazan {{ text-align: center; font-weight: 700; color: #7a5a12;
                    font-size: 15px; margin: 4px 0; }}
      .bb .kazan .num {{ display: inline-block; min-width: 34px; margin-left: 6px;
                         background: #f6e2a0; border-radius: 10px; padding: 1px 8px; }}
      .bb .row {{ display: flex; gap: 12px; justify-content: center; margin: 12px 0; }}
      .bb .pit {{ width: 60px; height: 60px; border-radius: 50%;
                  display: flex; align-items: center; justify-content: center;
                  font-size: 22px; font-weight: 800; color: #111;
                  background: radial-gradient(circle at 35% 30%, #f4ad55 0%, #d9822b 55%, #b5661d 100%);
                  box-shadow: inset 0 -3px 6px rgba(0,0,0,0.25), 0 2px 3px rgba(0,0,0,0.2); }}
    </style>
    <div class="bb">
      <div class="kazan">Kostaushi<span class="num">{kk}</span></div>
      <div class="row">{top}</div>
      <div class="row">{bottom}</div>
      <div class="kazan">Bastaushi<span class="num">{bk}</span></div>
    </div>
    """


def history_text(hist) -> str:
    """hist is a flat list of notations, alternating Bastaushi/Kostaushi."""
    lines = []
    for i in range(0, len(hist), 2):
        turn = i // 2 + 1
        pair = hist[i:i + 2]
        lines.append(f"{turn}. " + " ".join(pair))
    return "\n".join(lines) if lines else "(no moves yet)"


def moves_table(moves, ply):
    return [[move_notation(m), result_label(m["result"], ply)] for m in moves]


def turn_markdown(ply, over_msg=None):
    if over_msg:
        return f"### 🏁 {over_msg}"
    who = "Bastaushi" if ply % 2 == 0 else "Kostaushi"
    return f"### {who} to move — click a move below to play it"


# --------------------------------------------------------------------------- #
# Event handlers
# --------------------------------------------------------------------------- #
def new_game(pos_str):
    try:
        vals = parse_fields(pos_str)
    except ValueError as e:
        empty = board_html(START_POSITION, 0)
        return (empty, [], "(no moves yet)", f"### ⚠️ {e}",
                START_POSITION, 0, [], [], START_POSITION, True)

    state = " ".join(str(v) for v in vals)
    try:
        data = run_query(state)
    except Exception as e:  # noqa: BLE001
        empty = board_html(state, 0)
        return (empty, [], "(no moves yet)", f"### ⚠️ Engine error: {e}",
                state, 0, [], [], state, True)

    if "error" in data:
        empty = board_html(state, 0)
        return (empty, [], "(no moves yet)", f"### ⚠️ {data['error']}",
                state, 0, [], [], state, True)

    moves = data["moves"]
    over = len(moves) == 0
    return (board_html(state, 0),
            moves_table(moves, 0),
            "(no moves yet)",
            turn_markdown(0, "No legal moves." if over else None),
            state, 0, [], moves, state, over)


@gpu_entry
def play_move(evt: gr.SelectData, state, ply, history, moves, over):
    # No-op if game is finished or the click didn't land on a valid row.
    if over or evt.index is None or evt.index[0] >= len(moves):
        return (gr.update(), gr.update(), gr.update(), gr.update(),
                state, ply, history, moves, over)

    m = moves[evt.index[0]]
    history = history + [move_notation(m)]

    if m["terminal"]:
        result = result_label("WIN", ply)  # a terminal move is an immediate win for the mover
        return (board_html(state, ply), [], history_text(history),
                turn_markdown(ply, result + " (game over)"),
                state, ply, history, [], True)

    child = m["child"]
    new_state = f"{child['K1']} {child['K2']} " + " ".join(str(x) for x in child["board"])
    new_ply = ply + 1
    try:
        data = run_query(new_state)
    except Exception as e:  # noqa: BLE001
        return (board_html(new_state, new_ply), [], history_text(history),
                f"### ⚠️ Engine error: {e}", new_state, new_ply, history, [], True)

    new_moves = data.get("moves", [])
    over = len(new_moves) == 0
    return (board_html(new_state, new_ply),
            moves_table(new_moves, new_ply),
            history_text(history),
            turn_markdown(new_ply, "No legal moves — game over." if over else None),
            new_state, new_ply, history, new_moves, over)


def make_pgn(start_fen, history):
    body = history_text(history)
    if body == "(no moves yet)":
        body = ""
    pgn = (
        '[Event "Bestemshe Perfect-Play Analysis"]\n'
        '[Site "Bestemshe Tablebase Explorer"]\n'
        f'[FEN "{start_fen}"]\n\n'
        f"{body}\n"
    )
    fd, path = tempfile.mkstemp(suffix=".pgn", prefix="bestemshe_")
    with os.fdopen(fd, "w") as f:
        f.write(pgn)
    return path


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
ensure_query_binary()
ensure_tablebase()

INSTRUCTIONS = (
    "Enter a position as **12 numbers**, in this order:\n\n"
    "1. **Bastaushi's kazan** (stones Bastaushi has captured)\n"
    "2. **Kostaushi's kazan** (stones Kostaushi has captured)\n"
    "3. **Bastaushi's 5 pits** (from pit 1 to pit 5)\n"
    "4. **Kostaushi's 5 pits** (from pit 1 to pit 5)\n\n"
    "All the stones must add up to **50**, and Bastaushi moves first. "
    "Leave the default for the standard opening position, then just press **New Game**."
)

with gr.Blocks(title="Bestemshe Tablebase Explorer") as demo:
    gr.Markdown("# 🎯 Bestemshe — Perfect-Play Explorer\n"
                "Bestemshe is **strongly solved**. Play out any line and the oracle tells you, "
                "for every legal move, who wins with perfect play.")

    st_state = gr.State(START_POSITION)
    st_ply = gr.State(0)
    st_history = gr.State([])
    st_moves = gr.State([])
    st_startfen = gr.State(START_POSITION)
    st_over = gr.State(False)

    with gr.Accordion("Set a custom starting position", open=False):
        gr.Markdown(INSTRUCTIONS)
        pos_input = gr.Textbox(label="Position (12 numbers)", value=START_POSITION)
    new_game_btn = gr.Button("New Game", variant="primary")

    turn_label = gr.Markdown(turn_markdown(0))
    board = gr.HTML(board_html(START_POSITION, 0))

    with gr.Row():
        with gr.Column(scale=2):
            moves_df = gr.Dataframe(
                headers=["Move", "Perfect play"],
                datatype=["str", "str"],
                interactive=False,
                label="Legal moves — click one to play it",
            )
        with gr.Column(scale=1):
            history_box = gr.Textbox(label="Move history", lines=10, interactive=False,
                                     value="(no moves yet)")
            download_btn = gr.DownloadButton("⬇️ Download PGN")

    game_outputs = [board, moves_df, history_box, turn_label,
                    st_state, st_ply, st_history, st_moves, st_startfen, st_over]
    new_game_btn.click(new_game, [pos_input], game_outputs)
    pos_input.submit(new_game, [pos_input], game_outputs)
    demo.load(new_game, [pos_input], game_outputs)

    moves_df.select(
        play_move,
        [st_state, st_ply, st_history, st_moves, st_over],
        [board, moves_df, history_box, turn_label,
         st_state, st_ply, st_history, st_moves, st_over],
    )
    download_btn.click(make_pgn, [st_startfen, st_history], download_btn)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)))
