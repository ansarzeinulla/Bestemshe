"""Bestemshe Perfect-Play Explorer.

A custom HTML/JS front end (multilingual, keyboard-driven, rewritable history)
talks to the C++ tablebase oracle through a hidden Gradio bridge. Keeping the
UI client-side lets us do global keyboard handling, arrow navigation, clickable
history and language switching that Gradio's own components cannot express.

All user-facing copy, flags and language names live in i18n.py.
"""

import json
import os
import subprocess

import gradio as gr

from i18n import LANGUAGES, TRANSLATIONS

# CPU-only app. If the Space is provisioned on ZeroGPU hardware its startup
# check demands a @spaces.GPU function; this dummy probe (never called) satisfies
# it while all real work runs on the always-available CPU.
try:
    import spaces

    @spaces.GPU
    def _zerogpu_probe():
        return None
except ImportError:
    pass

QUERY_BIN = os.environ.get("BESTEMSHE_QUERY_BIN", "./query")
DATA_DIR = os.environ.get("BESTEMSHE_DATA_DIR", "layers/compressed")
TABLEBASE_DATASET = os.environ.get("BESTEMSHE_DATASET", "ansarzeinulla/bestemshe-tablebase")


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


def parse_fields(text):
    parts = text.split()
    if len(parts) != 12:
        raise ValueError("Enter 12 numbers.")
    try:
        vals = [int(p) for p in parts]
    except ValueError:
        raise ValueError("All values must be whole numbers.")
    if any(v < 0 or v > 50 for v in vals):
        raise ValueError("Each number must be between 0 and 50.")
    if sum(vals) != 50:
        raise ValueError(f"The stones must total 50 (yours total {sum(vals)}).")
    if vals[0] % 2 or vals[1] % 2:
        raise ValueError("Kazan totals must be even.")
    if vals[0] > 24 or vals[1] > 24:
        raise ValueError("A kazan of 26+ means the game is already over.")
    return vals


def run_query(state_str):
    env = dict(os.environ, BESTEMSHE_DATA_DIR=DATA_DIR)
    proc = subprocess.run(
        [QUERY_BIN] + state_str.split(),
        capture_output=True, text=True, timeout=60, env=env,
    )
    return json.loads(proc.stdout)


def oracle_bridge(payload):
    """payload = 'nonce|K1 K2 p0..p9'. Returns JSON string with the same nonce."""
    nonce, _, state = payload.partition("|")
    try:
        parse_fields(state)
        data = run_query(state)
        if "error" in data:
            return json.dumps({"nonce": nonce, "ok": False, "error": data["error"]})
        return json.dumps({"nonce": nonce, "ok": True, "data": data})
    except ValueError as e:
        return json.dumps({"nonce": nonce, "ok": False, "error": str(e)})
    except Exception as e:  # noqa: BLE001
        return json.dumps({"nonce": nonce, "ok": False, "error": str(e)})


# --------------------------------------------------------------------------- #
# Front end
# --------------------------------------------------------------------------- #
LANG_OPTIONS = "".join(
    f'<option value="{l["code"]}">{l["flag"]} {l["name"]}</option>' for l in LANGUAGES
)

INDEX_MARKUP = r"""
<style>
  #oracle_in, #oracle_out, #oracle_btn { display: none !important; }
  footer { display: none !important; }   /* hide Gradio's "Use via API · Built with Gradio" bar */
  .gradio-container { max-width: 100% !important; width: 100% !important; padding: 4px !important; }
  .gradio-container .main, .gradio-container .wrap, .gradio-container .contain { max-width: 100% !important; }
  /* strip Gradio's own horizontal padding so the board can use the full width */
  .fillable, .main.fillable, .app { padding-left: 6px !important; padding-right: 6px !important; }
  .html-container { padding: 0 !important; }
  .block.padded { padding: 0 !important; }
  #bb-wrap { max-width: 1700px; margin: 0 auto; padding: 0 8px;
             font-family: system-ui, sans-serif; color: #2a2118; --bs: 42px; }
  #bb-wrap * { box-sizing: border-box; }
  #bb-cols { display: flex; gap: 16px; align-items: stretch; }
  #bb-main { position: relative; flex: 1 1 auto; min-width: 0; display: flex; align-items: flex-start; }
  #bb-side { flex: 0 0 250px; display: flex; flex-direction: column; gap: 12px; min-height: 0; }
  #bb-cols.side-hidden #bb-side { display: none; }
  /* collapse / expand the right column */
  #bb-toggle { position: absolute; top: 10px; right: 10px; z-index: 6; width: 34px; height: 34px;
               border-radius: 10px; border: 1px solid #b98f52; background: rgba(255,250,235,0.9);
               color: #6d500e; font-size: 18px; font-weight: 800; cursor: pointer; line-height: 1;
               display: flex; align-items: center; justify-content: center; }
  #bb-toggle:hover { background: #fff4d6; }
  @media (max-width: 860px) {
    #bb-wrap { padding: 0 6px; }
    #bb-cols { flex-direction: column; gap: 12px; }
    #bb-side { flex: 1 1 auto; width: 100%; }
    .bb-board { padding: 10px; border-radius: 18px; gap: 6px; }
    .bb-cellrow, .bb-numrow { gap: 5px; }
    .bb-cell { padding: 4px; border-radius: 9px; }
    .bb-numrow .n { font-size: 14px; }
    .bb-kazan { padding: 6px 10px; gap: 8px; }
    .bb-kcount { font-size: 18px; }
    .bb-hist { min-height: 220px; }
    #bb-toggle { top: 6px; right: 6px; }
  }

  .bb-card { background: #fffdf5; border: 1px solid #ecdfb8; border-radius: 16px; padding: 14px;
             display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; }

  /* ---- board: a real Bestemshe board with kumalak stones ---- */
  .bb-board { flex: 1 1 auto; width: 100%;
              background: linear-gradient(160deg, #ddba86 0%, #c99f68 100%);
              border: 2px solid #a67c48; border-radius: 22px; padding: 16px;
              box-shadow: inset 0 2px 10px rgba(120,80,30,0.20), 0 6px 18px rgba(120,80,20,0.16);
              display: flex; flex-direction: column; gap: 8px; }

  .ball { position: relative; display: inline-block; width: var(--bs); height: var(--bs); border-radius: 50%;
          background: radial-gradient(circle at 34% 30%, #fffdf6 0%, #eed9a6 46%, #bd9051 100%);
          box-shadow: inset 0 -2px 4px rgba(90,60,20,0.40), 0 1px 2px rgba(0,0,0,0.28); }
  .ball.ghost { background: none; box-shadow: none; }
  /* stones inside the play cells sit a touch smaller than their slot for breathing room */
  .bb-cell .ball { transform: scale(0.9); }
  /* a stacked (overlaid) layer of stones is shown as a dark dot at the centre */
  .ball .ov { position: absolute; top: 25%; left: 25%; width: 50%; height: 50%; border-radius: 50%;
              background: #241a0d; box-shadow: inset 0 1px 1px rgba(255,255,255,0.18); }

  /* kazans (stores) — lighter, no name labels */
  .bb-kazan { --ks: clamp(16px, calc(var(--bs) * 0.58), 32px);   /* kazan stones stay compact */
              display: flex; align-items: center; gap: 12px; padding: 8px 14px; border-radius: 16px;
              background: rgba(255,250,235,0.28); border: 2px solid rgba(120,80,30,0.28);
              height: calc(var(--ks) * 2 + 20px);   /* FIXED — never changes with stone count */
              flex: 0 0 auto; transition: box-shadow .15s, border-color .15s; }
  .bb-kazan.turn { border-color: #d99a1f; box-shadow: 0 0 0 1px rgba(217,154,31,0.5), 0 0 14px rgba(217,154,31,0.35); }
  .bb-kcount { font-weight: 800; font-size: 22px; color: #5a3d18; min-width: 34px; text-align: center;
               background: rgba(120,80,30,0.14); border-radius: 12px; padding: 3px 10px;
               font-variant-numeric: tabular-nums; }
  .bb-kballs { display: flex; flex-wrap: nowrap; align-items: center; gap: 4px; flex: 1 1 auto;
               overflow: hidden; }   /* one row of columns only — kazan height stays fixed */
  .bb-kballs .ball { width: var(--ks); height: var(--ks); }
  .bb-kcol { display: flex; flex-direction: column; gap: 4px; height: calc(var(--ks) * 2 + 4px); }
  .bb-kazan.kazan-black .bb-kcol { justify-content: flex-start; }   /* gravity top */
  .bb-kazan.kazan-white .bb-kcol { justify-content: flex-end; }     /* gravity down */

  /* count sub-rows between cells and kazans */
  .bb-numrow { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; padding: 0 2px; }
  .bb-numrow .n { text-align: center; font-weight: 800; font-size: 17px; color: #5a3d18;
                  font-variant-numeric: tabular-nums; }

  /* the five cells of each side — each exactly 2 stones wide, 5 tall */
  .bb-cellrow { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; }
  .bb-board { overflow-x: hidden; }
  .bb-cell { border-radius: 12px; border: 2px solid rgba(90,60,25,0.30);
             background: rgba(70,45,18,0.16); padding: 6px;
             height: calc(var(--bs) * 5 + 36px); display: flex;
             transition: box-shadow .15s, border-color .15s, background .12s; }
  .bb-cell.mv { cursor: pointer; }
  .bb-cell.mv:hover { background: rgba(70,45,18,0.26); }
  .bb-cell.WIN  { border-color: #2fa740; box-shadow: 0 0 0 1px rgba(47,167,64,0.6), 0 0 14px rgba(47,167,64,0.55); }
  .bb-cell.DRAW { border-color: #e8c400; box-shadow: 0 0 0 1px rgba(232,196,0,0.65), 0 0 14px rgba(232,196,0,0.6); }
  .bb-cell.LOSS { border-color: #e23b3b; box-shadow: 0 0 0 1px rgba(226,59,59,0.6), 0 0 14px rgba(226,59,59,0.55); }
  .bb-stack { display: flex; flex-direction: column; gap: 6px; flex: 1; }
  .bb-cellrow.row-black .bb-stack { justify-content: flex-start; }  /* grows downward */
  .bb-cellrow.row-white .bb-stack { justify-content: flex-end; }    /* grows upward */
  .bb-brow { display: flex; gap: 6px; justify-content: center; }    /* 2 columns, left gravity */

  .bb-side-row { display: flex; gap: 8px; align-items: center; }
  #bb-langsel { width: 100%; font-size: 15px; padding: 9px 10px; border-radius: 12px;
                border: 1px solid #e2c98a; background: #fffdf5; color: #2a2118; cursor: pointer; }
  .bb-actions { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
  .bb-icon { cursor: pointer; border: 1px solid #e2c98a; background: #fff8e6; border-radius: 12px;
             height: 46px; font-size: 22px; font-weight: 800; color: #8a5a00; padding: 0;
             line-height: 1; display: flex; align-items: center; justify-content: center;
             font-family: system-ui, sans-serif; }
  .bb-icon:hover { background: #ffedc2; color: #5c3c00; }
  #bb-btn-setup { font-size: 27px; }   /* the gear reads optically small — nudge it up */

  .bb-hist-title { font-weight: 700; color: #6d500e; margin: 0 0 8px; font-size: 14px;
                   text-transform: uppercase; letter-spacing: .04em; }
  .bb-hist { font-family: ui-monospace, monospace; font-size: 15px;
             flex: 1 1 0; min-height: 0; overflow-y: auto; overflow-x: hidden; }
  .bb-hrow { display: grid; grid-template-columns: 34px 1fr 1fr; gap: 4px; align-items: center;
             line-height: 1.5; padding: 2px 0; }
  .bb-turn { color: #b3a276; text-align: right; padding-right: 4px; }
  .bb-mv { cursor: pointer; padding: 3px 8px; border-radius: 7px; text-align: center; }
  .bb-mv:hover { background: #ffedc2; }
  .bb-mv.on { background: #d9822b; color: #fff; }

  .bb-overlay { position: fixed; inset: 0; background: rgba(30,22,8,0.5); display: none;
                align-items: center; justify-content: center; z-index: 1000; }
  .bb-overlay.open { display: flex; }
  .bb-modal { background: #fffdf8; border-radius: 18px; padding: 24px; max-width: 70%; width: 100%;
              max-height: 88vh; overflow: auto; box-shadow: 0 14px 48px rgba(0,0,0,0.35); }
  .bb-modal h3 { margin: 0 0 14px; color: #6d500e; }
  .bb-modal textarea { width: 100%; font-family: ui-monospace, monospace; font-size: 15px;
                       padding: 10px; border: 1px solid #d8c692; border-radius: 10px; background: #fff; }
  .bb-modal .hint { font-size: 15.5px; color: #4c4130; margin: 10px 0 4px; line-height: 1.75; }
  #bb-fen-help { background: #fbf3dc; border: 1px solid #ecdfb8; border-radius: 10px;
                 padding: 12px 14px; margin-top: 12px; }
  #bb-fen-help b { color: #6d500e; }
  .bb-modal .hint b { color: #6d500e; }
  .bb-modal .keys { display: grid; grid-template-columns: 74px 1fr; gap: 6px 12px;
                    font-size: 14.5px; color: #4c4130; margin: 10px 0; align-items: center; }
  .bb-modal .keys kbd { background: #f1e5c0; border: 1px solid #d8c692; border-radius: 6px;
                        padding: 2px 8px; font-family: ui-monospace, monospace; font-size: 13px;
                        text-align: center; }
  .bb-modal .err { color: #c62828; font-size: 14px; margin-top: 8px; min-height: 18px; }
  .bb-modal .credit { font-size: 13px; color: #6d500e; margin-top: 14px; line-height: 1.6;
                      border-top: 1px solid #ecdfb8; padding-top: 12px; }
  .bb-modal .btns { display: flex; gap: 10px; justify-content: stretch; margin-top: 16px; }
  /* Start and Close buttons are forced to identical size/height. */
  .bb-modal .btns button { flex: 1 1 0; cursor: pointer; border-radius: 10px; padding: 0;
                           height: 46px; line-height: 46px; box-sizing: border-box;
                           display: flex; align-items: center; justify-content: center;
                           font-weight: 700; font-size: 15px; border: 1px solid #d9822b;
                           background: #d9822b; color: #fff; }
  .bb-modal .btns button:hover { background: #c4741f; }
  .bb-end-title { text-align: center; font-size: 22px; }
</style>
<div id="bb-wrap">
  <div id="bb-cols">
    <div id="bb-main">
      <button id="bb-toggle" title="Hide / show panel">⇥</button>
      <div class="bb-board" id="bb-board"></div>
    </div>
    <div id="bb-side">
      <select id="bb-langsel">__LANG_OPTIONS__</select>
      <div class="bb-actions">
        <button class="bb-icon" data-act="new" id="bb-btn-new">↺</button>
        <button class="bb-icon" data-act="open" data-modal="bb-setup" id="bb-btn-setup">⚙</button>
        <button class="bb-icon" data-act="open" data-modal="bb-help" id="bb-btn-help">?</button>
        <button class="bb-icon" data-act="pgn" id="bb-btn-pgn">⤓</button>
      </div>
      <div class="bb-card">
        <div class="bb-hist-title" id="bb-hist-title"></div>
        <div class="bb-hist" id="bb-hist"></div>
      </div>
    </div>
  </div>

  <div class="bb-overlay" id="bb-setup"><div class="bb-modal" style="max-width: 50%">
    <h3 id="bb-setup-title"></h3>
    <textarea id="bb-fen" rows="2"></textarea>
    <div class="hint" id="bb-fen-help"></div>
    <div class="err" id="bb-setup-err"></div>
    <div class="btns"><button data-act="close" data-modal="bb-setup" id="bb-setup-close"></button>
      <button data-act="apply" id="bb-setup-apply"></button></div>
  </div></div>
  <div class="bb-overlay" id="bb-help"><div class="bb-modal">
    <h3 id="bb-help-title"></h3>
    <div class="hint" id="bb-help-intro"></div>
    <div class="keys" id="bb-help-keys"></div>
    <div class="hint" id="bb-help-extra"></div>
    <div class="credit" id="bb-help-credit"></div>
    <div class="btns"><button data-act="close" data-modal="bb-help" id="bb-help-close"></button></div>
  </div></div>
  <div class="bb-overlay" id="bb-end"><div class="bb-modal">
    <h3 class="bb-end-title" id="bb-end-title"></h3>
    <div class="hint" id="bb-end-msg" style="text-align:center"></div>
    <div class="btns"><button data-act="close" data-modal="bb-end" id="bb-end-close"></button>
      <button data-act="pgn" id="bb-end-pgn"></button></div>
  </div></div>
</div>
""".replace("__LANG_OPTIONS__", LANG_OPTIONS)

INDEX_JS = r"""
() => {
  if (window.__bbInit) return; window.__bbInit = true;
  const DEFAULT_FEN = "5,5,5,5,5/5,5,5,5,5 0,0 w 1";

  const I18N = __I18N_JSON__;
  const SITE = "https://huggingface.co/spaces/ansarzeinulla/Bestemshe-God-Algorithm";

  let lang = "EN";
  let initialFen = DEFAULT_FEN;
  let line = [];      // nodes {state, ply, moveIn, key, moves, gameOver, winner}
  let played = [];    // notations, aligned to line transitions
  let cursor = 0;
  let busy = false;
  const t = (k) => (I18N[lang][k] !== undefined ? I18N[lang][k] : I18N.EN[k]);
  // Two roles by side index: 0 = the first player (moves first), 1 = the follower.
  // Names are translated, so winners are tracked by side index, not by name.
  const nameFor = (side) => (side === 0 ? t("nameFirst") : t("nameSecond"));

  // ---- FEN <-> internal state -------------------------------------------- #
  // Internal state is mover-relative "K1 K2 p0..p9" (K1/p0-4 = side to move).
  // FEN is colour-absolute:  w1..w5/b1..b5 wKazan,bKazan side moveNo  (White=Bastaushi).
  function absView(state, ply) {
    const v = state.split(" ").map(Number);
    const kM = v[0], kO = v[1], b = v.slice(2);
    if (ply % 2 === 0) return { bk: kM, kk: kO, bp: b.slice(0, 5), kp: b.slice(5, 10), moverBottom: true };
    return { bk: kO, kk: kM, bp: b.slice(5, 10), kp: b.slice(0, 5), moverBottom: false };
  }
  function nodeToFen(node) {
    const av = absView(node.state, node.ply);
    const side = node.ply % 2 === 0 ? "w" : "b";
    const moveNo = Math.floor(node.ply / 2) + 1;
    return av.bp.join(",") + "/" + av.kp.join(",") + " " +
           av.bk + "," + av.kk + " " + side + " " + moveNo;
  }
  // Returns {state, ply} or {error}.
  function fenToInternal(fen) {
    try {
      const parts = fen.trim().split(/\s+/);
      if (parts.length < 3) return { error: "bad" };
      const cells = parts[0].split("/");
      if (cells.length !== 2) return { error: "bad" };
      const white = cells[0].split(",").map(Number);
      const black = cells[1].split(",").map(Number);
      const kaz = parts[1].split(",").map(Number);
      if (white.length !== 5 || black.length !== 5 || kaz.length !== 2) return { error: "bad" };
      const all = white.concat(black, kaz);
      if (all.some((n) => !Number.isInteger(n) || n < 0)) return { error: "bad" };
      const side = (parts[2] || "w").toLowerCase();
      const moveNo = parts[3] !== undefined ? parseInt(parts[3], 10) : 1;
      const wk = kaz[0], bk = kaz[1];
      let state, ply;
      if (side === "b") {                       // Black (Kostaushi) to move
        state = bk + " " + wk + " " + black.concat(white).join(" ");
        ply = (Math.max(1, moveNo) - 1) * 2 + 1;
      } else {                                  // White (Bastaushi) to move
        state = wk + " " + bk + " " + white.concat(black).join(" ");
        ply = (Math.max(1, moveNo) - 1) * 2;
      }
      return { state, ply };
    } catch (e) { return { error: "bad" }; }
  }

  // ---- oracle bridge ----------------------------------------------------- #
  function setNative(el, val) {
    const set = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
    set.call(el, val); el.dispatchEvent(new Event("input", { bubbles: true }));
  }
  function oracleOnce(state) {
    return new Promise((resolve, reject) => {
      const nonce = Math.random().toString(36).slice(2);
      const inp = document.querySelector("#oracle_in textarea");
      const out = document.querySelector("#oracle_out textarea");
      const btn = document.querySelector("#oracle_btn button") || document.querySelector("#oracle_btn");
      if (!inp || !out || !btn) { reject("bridge not ready"); return; }
      let done = false;
      const poll = setInterval(() => {
        try { const j = JSON.parse(out.value); if (j.nonce === nonce) { done = true; clearInterval(poll); resolve(j); } } catch (e) {}
      }, 70);
      setTimeout(() => { if (!done) { clearInterval(poll); reject("timeout"); } }, 6000);
      setNative(inp, nonce + "|" + state);
      btn.click();
    });
  }
  async function oracle(state) {
    let lastErr;
    for (let attempt = 0; attempt < 4; attempt++) {
      try { return await oracleOnce(state); }
      catch (e) { lastErr = e; await new Promise((r) => setTimeout(r, 250)); }
    }
    throw lastErr;
  }

  async function makeNode(state, ply, moveIn) {
    const node = { state, ply, moveIn, key: (ply % 2) + ":" + state, moves: [], gameOver: null, winner: null };
    const res = await oracle(state);
    if (!res.ok) { node.error = res.error; return node; }
    node.moves = res.data.moves;
    if (node.moves.length === 0) { node.gameOver = "nomove"; node.winner = (ply + 1) % 2; }
    return node;
  }

  async function newGame(fen) {
    const parsed = fenToInternal(fen);
    if (parsed.error) return "bad";
    const n0 = await makeNode(parsed.state, parsed.ply, null);
    if (n0.error) return n0.error;
    initialFen = fen; line = [n0]; played = []; cursor = 0; render();
    return null;
  }

  async function playMove(node, m) {
    if (busy) return; busy = true;
    try {
      line = line.slice(0, cursor + 1);
      played = played.slice(0, cursor);
      const notation = "" + m.from + m.to + (m.capture ? "+" : "");
      const cs = m.child.K1 + " " + m.child.K2 + " " + m.child.board.join(" ");
      const cp = node.ply + 1;
      let child;
      if (m.terminal) {
        child = { state: cs, ply: cp, moveIn: notation, key: (cp % 2) + ":" + cs,
                  moves: [], gameOver: "win", winner: node.ply % 2 };
      } else {
        // Loop detection: we keep every position (side-to-move + board) of the
        // current line; if this child repeats one of them, it is an infinite-loop draw.
        const repeat = line.some((nd) => nd.key === (cp % 2) + ":" + cs);
        child = await makeNode(cs, cp, notation);
        child.moveIn = notation;
        if (repeat) { child.gameOver = "draw"; child.winner = null; child.moves = []; }
      }
      line.push(child); played.push(notation); cursor = line.length - 1; render();
      if (child.gameOver) announceEnd(child);
    } finally { busy = false; }
  }

  function optimal(node) {
    const rank = { WIN: 2, DRAW: 1, LOSS: 0 };
    let best = -1; node.moves.forEach((m) => { best = Math.max(best, rank[m.result]); });
    return node.moves.filter((m) => rank[m.result] === best);
  }
  async function inputIndex(i) {
    const node = line[cursor];
    if (!node || node.gameOver || node.error) return;
    if (i === 0) {                              // random OPTIMAL move
      const b = optimal(node);
      if (b.length) await playMove(node, b[Math.floor(Math.random() * b.length)]);
      return;
    }
    if (i === 9) {                              // random move — optimality ignored
      if (node.moves.length) await playMove(node, node.moves[Math.floor(Math.random() * node.moves.length)]);
      return;
    }
    const m = node.moves.find((x) => x.from === i);
    if (m) await playMove(node, m);
  }
  function go(idx) { cursor = Math.max(0, Math.min(line.length - 1, idx)); render(); }

  // ---- PGN --------------------------------------------------------------- #
  function resultToken() {
    const last = line[line.length - 1];
    if (last.gameOver === "draw") return "1/2-1/2";
    if (last.gameOver === "win" || last.gameOver === "nomove")
      return last.winner === 0 ? "1-0" : "0-1";
    return "*";
  }
  function pgnMoves() {
    let out = [];
    for (let i = 0; i < played.length; i += 2) {
      out.push((i / 2 + 1) + ". " + played.slice(i, i + 2).join(" "));
    }
    let body = out.join(" ");
    const last = line[line.length - 1];
    if (last.gameOver === "draw") body += " {Loop is reached}";
    const res = resultToken();
    if (res !== "*") body += " " + res;
    return body;
  }
  function downloadPgn() {
    const d = new Date();
    const date = d.getFullYear() + "." +
      String(d.getMonth() + 1).padStart(2, "0") + "." + String(d.getDate()).padStart(2, "0");
    const header =
      '[Event "Single Play Versus God"]\n' +
      '[Site "' + SITE + '"]\n' +
      '[Date "' + date + '"]\n' +
      '[White "Player"]\n' +
      '[Black "God"]\n' +
      '[Result "' + resultToken() + '"]\n' +
      '[PlyCount "' + played.length + '"]\n' +
      '[Annotator "God"]\n' +
      '[Mode "online"]\n';
    const pgn = header + "\n" + pgnMoves() + "\n";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([pgn], { type: "text/plain" }));
    a.download = "bestemshe.pgn"; a.click();
  }

  // ---- rendering --------------------------------------------------------- #
  // Colour-absolute view of a node (White = Bastaushi, Black = Kostaushi).
  function colorView(node) {
    const v = node.state.split(" ").map(Number);
    const k1 = v[0], k2 = v[1], p = v.slice(2);
    const whiteToMove = node.ply % 2 === 0;
    let wk, bk, wp, bp;
    if (whiteToMove) { wk = k1; bk = k2; wp = p.slice(0, 5); bp = p.slice(5, 10); }
    else { bk = k1; wk = k2; bp = p.slice(0, 5); wp = p.slice(5, 10); }
    return { wk, bk, wp, bp, whiteToMove };
  }

  // A cell is exactly 2 stones wide and 5 stones tall — 10 visible slots.
  // Stones fill row by row, left column first (an odd stone sits on the left).
  // `side` sets the growth direction: black grows downward (rows top→bottom),
  // white grows upward (rows bottom→top). Once a slot is full, further stones
  // stack a new layer on top of it — shown as a small dark dot in the stone's
  // centre rather than a second circle. Slot i holds ceil((n-i)/10) layers.
  function cellStack(n, side) {
    let rows = [];
    for (let r = 0; r < 5; r++) {
      let s = "";
      for (let c = 0; c < 2; c++) {
        const i = r * 2 + c;
        const layers = n > i ? Math.ceil((n - i) / 10) : 0;
        if (layers <= 0) s += '<span class="ball ghost"></span>';
        else s += '<span class="ball">' + (layers >= 2 ? '<i class="ov"></i>' : "") + "</span>";
      }
      rows.push('<div class="bb-brow">' + s + "</div>");
    }
    if (side === "white") rows.reverse();
    return '<div class="bb-stack">' + rows.join("") + "</div>";
  }

  // A kazan holds stones in columns of 2, filled column by column (left→right).
  // Vertical gravity (top for black, bottom for white) is handled in CSS.
  function kazanStack(n) {
    let cols = [];
    const ncols = Math.ceil(n / 2);
    for (let c = 0; c < ncols; c++) {
      const inCol = Math.min(2, n - c * 2);
      let b = "";
      for (let k = 0; k < inCol; k++) b += '<span class="ball"></span>';
      cols.push('<div class="bb-kcol">' + b + "</div>");
    }
    return cols.join("");
  }

  function cellHtml(count, pit, isMover, move, side) {
    const cls = "bb-cell" + (isMover && move ? " mv " + move.result : "");
    const data = isMover && move ? ' data-act="pit" data-i="' + pit + '"' : "";
    return '<div class="' + cls + '"' + data + ">" + cellStack(count, side) + "</div>";
  }

  // Each cell is 2 stones wide; the five cells fill the board's width, so the
  // stone size is whatever makes 2 of them fit snugly inside one cell. Recomputed
  // on every render and on resize (keeps stones as large as the space allows).
  function sizeBoard() {
    const board = document.getElementById("bb-board");
    const wrap = document.getElementById("bb-wrap");
    if (!board || !wrap) return;
    const cs = getComputedStyle(board);
    const inner = board.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    const cellGap = 8, cellPad = 6, colGap = 6;   // must match the CSS
    const cellOuter = (inner - 4 * cellGap) / 5;
    let bs = Math.floor((cellOuter - 2 * cellPad - colGap) / 2);   // largest that fits the width
    bs = Math.max(14, Math.min(120, bs));
    wrap.style.setProperty("--bs", bs + "px");
    // Then measure the real board height and shrink until it fits the device viewport.
    for (let i = 0; i < 5; i++) {
      const avail = window.innerHeight - board.getBoundingClientRect().top - 12;
      const h = board.offsetHeight;
      if (h <= avail || bs <= 14) break;
      bs = Math.max(14, Math.floor(bs * avail / h));
      wrap.style.setProperty("--bs", bs + "px");
    }
  }
  window.addEventListener("resize", sizeBoard);

  function announceEnd(node) {
    const titleEl = document.getElementById("bb-end-title");
    const msgEl = document.getElementById("bb-end-msg");
    if (node.gameOver === "draw") {
      titleEl.textContent = "🔁 " + t("drawLoop");
      msgEl.textContent = t("loopHint");
    } else {
      titleEl.textContent = "🏆 " + nameFor(node.winner) + " " + t("wins");
      msgEl.textContent = "";
    }
    document.getElementById("bb-end").classList.add("open");
  }

  function render() {
    const node = line[cursor];
    const cv = colorView(node);
    const moverMoves = new Map();
    if (!node.gameOver && !node.error) node.moves.forEach((m) => moverMoves.set(m.from, m));

    // Fixed board: Black (Kostaushi) on top, White (Bastaushi) on the bottom.
    // Each player numbers pits 1..5 from their own left, so Black's pits read
    // right-to-left across the top; White's read left-to-right along the bottom.
    let blackCells = "", blackNums = "", whiteCells = "", whiteNums = "";
    for (let c = 1; c <= 5; c++) {
      const bp = 6 - c;                                   // black pit at visual column c
      const bMover = !cv.whiteToMove;
      blackCells += cellHtml(cv.bp[bp - 1], bp, bMover, moverMoves.get(bp), "black");
      blackNums += '<div class="n">' + cv.bp[bp - 1] + "</div>";
      const wp = c;                                       // white pit at visual column c
      const wMover = cv.whiteToMove;
      whiteCells += cellHtml(cv.wp[wp - 1], wp, wMover, moverMoves.get(wp), "white");
      whiteNums += '<div class="n">' + cv.wp[wp - 1] + "</div>";
    }
    const blackTurn = cv.whiteToMove ? "" : " turn";
    const whiteTurn = cv.whiteToMove ? " turn" : "";

    document.getElementById("bb-board").innerHTML =
      '<div class="bb-kazan kazan-black' + blackTurn + '">' +
        '<span class="bb-kcount">' + cv.bk + '</span>' +
        '<div class="bb-kballs">' + kazanStack(cv.bk) + "</div></div>" +
      '<div class="bb-numrow">' + blackNums + "</div>" +
      '<div class="bb-cellrow row-black">' + blackCells + "</div>" +
      '<div class="bb-cellrow row-white">' + whiteCells + "</div>" +
      '<div class="bb-numrow">' + whiteNums + "</div>" +
      '<div class="bb-kazan kazan-white' + whiteTurn + '">' +
        '<span class="bb-kcount">' + cv.wk + '</span>' +
        '<div class="bb-kballs">' + kazanStack(cv.wk) + "</div></div>";
    sizeBoard();

    let hist = "";
    for (let i = 0; i < played.length; i += 2) {
      hist += '<div class="bb-hrow"><span class="bb-turn">' + (i / 2 + 1) + ".</span>";
      for (let j = i; j < i + 2; j++) {
        hist += (j < played.length)
          ? '<span class="bb-mv' + (j + 1 === cursor ? " on" : "") + '" data-act="hist" data-idx="' + j + '">' + played[j] + "</span>"
          : "<span></span>";
      }
      hist += "</div>";
    }
    const histEl = document.getElementById("bb-hist");
    histEl.innerHTML = hist;
    document.getElementById("bb-hist-title").textContent = t("history");
    const onEl = histEl.querySelector(".bb-mv.on");
    if (onEl) onEl.scrollIntoView({ block: "nearest" });
    else histEl.scrollTop = histEl.scrollHeight;

    // toolbar tooltips + modal labels
    document.getElementById("bb-btn-new").title = t("newGame");
    document.getElementById("bb-btn-setup").title = t("setup");
    document.getElementById("bb-btn-help").title = t("help");
    document.getElementById("bb-btn-pgn").title = t("pgn");
    document.getElementById("bb-setup-title").textContent = t("setup");
    document.getElementById("bb-fen-help").innerHTML = t("fenHelp");
    document.getElementById("bb-setup-apply").textContent = t("apply");
    document.getElementById("bb-setup-close").textContent = t("close");
    document.getElementById("bb-help-title").textContent = t("help");
    document.getElementById("bb-help-intro").innerHTML = t("helpIntro");
    document.getElementById("bb-help-keys").innerHTML =
      t("keys").map((k) => "<kbd>" + k[0] + "</kbd><span>" + k[1] + "</span>").join("");
    document.getElementById("bb-help-extra").textContent = t("helpExtra");
    document.getElementById("bb-help-credit").textContent = t("authors");
    document.getElementById("bb-help-close").textContent = t("close");
    document.getElementById("bb-end-close").textContent = t("close");
    document.getElementById("bb-end-pgn").textContent = t("pgn");
  }

  function anyModalOpen() {
    return document.querySelector(".bb-overlay.open") !== null;
  }

  // ---- events ------------------------------------------------------------ #
  document.getElementById("bb-langsel").addEventListener("change", (e) => { lang = e.target.value; render(); });

  document.getElementById("bb-toggle").addEventListener("click", () => {
    const cols = document.getElementById("bb-cols");
    const hidden = cols.classList.toggle("side-hidden");
    document.getElementById("bb-toggle").textContent = hidden ? "⇤" : "⇥";
    sizeBoard();   // board width changed — rescale stones
  });

  document.getElementById("bb-wrap").addEventListener("click", async (e) => {
    const el = e.target.closest("[data-act]"); if (!el) return;
    const act = el.dataset.act;
    if (act === "new") { await newGame(DEFAULT_FEN); }
    else if (act === "pgn") { downloadPgn(); }
    else if (act === "open") {
      const m = document.getElementById(el.dataset.modal);
      if (el.dataset.modal === "bb-setup") {
        document.getElementById("bb-fen").value = nodeToFen(line[cursor]);
        document.getElementById("bb-setup-err").textContent = "";
      }
      m.classList.add("open");
    }
    else if (act === "close") { document.getElementById(el.dataset.modal).classList.remove("open"); }
    else if (act === "apply") {
      const fen = document.getElementById("bb-fen").value.trim();
      const err = await newGame(fen);
      if (err) document.getElementById("bb-setup-err").textContent = t("fenHelp");
      else document.getElementById("bb-setup").classList.remove("open");
    }
    else if (act === "pit") { await inputIndex(parseInt(el.dataset.i, 10)); }
    else if (act === "hist") { go(parseInt(el.dataset.idx, 10) + 1); }
  });
  document.querySelectorAll(".bb-overlay").forEach((o) => o.addEventListener("click", (e) => {
    if (e.target === o) o.classList.remove("open");
  }));

  // Kazakh keyboard number row maps to the same digit inputs (item 5.2).
  const KZ_DIGIT = { "«": "1", "ә": "2", "і": "3", "ң": "4", "ғ": "5", "ұ": "9", "қ": "0" };
  // WASD navigation, case-insensitive, plus the letters those keys type on a
  // Kazakh/Russian layout: W→ц, A→ф, S→ы, D→в (items 5.3 / 5.4).
  const NAV = { w: "up", a: "left", s: "down", d: "right",
                "ц": "up", "ф": "left", "ы": "down", "в": "right" };

  document.addEventListener("keydown", (e) => {
    if (anyModalOpen()) { if (e.key === "Escape") document.querySelectorAll(".bb-overlay.open").forEach((o) => o.classList.remove("open")); return; }
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    if (tag === "TEXTAREA" || tag === "INPUT" || tag === "SELECT") return;

    let key = e.key;
    if (KZ_DIGIT[key] !== undefined) key = KZ_DIGIT[key];   // normalise Kazakh row to digits
    const nav = NAV[key.toLowerCase()];                     // WASD / Kazakh nav (case-insensitive)

    if ((key >= "0" && key <= "5") || key === "9") { inputIndex(parseInt(key, 10)); e.preventDefault(); }
    else if (e.key === "ArrowRight" || nav === "right") { go(cursor + 1); e.preventDefault(); }
    else if (e.key === "ArrowLeft" || nav === "left") { go(cursor - 1); e.preventDefault(); }
    else if (e.key === "ArrowUp" || nav === "up") { go(0); e.preventDefault(); }
    else if (e.key === "ArrowDown" || nav === "down") { go(line.length - 1); e.preventDefault(); }
  });

  const boot = setInterval(() => {
    if (document.querySelector("#oracle_in textarea") && document.querySelector("#oracle_btn")) {
      clearInterval(boot); newGame(DEFAULT_FEN);
    }
  }, 100);
}
""".replace("__I18N_JSON__", json.dumps(TRANSLATIONS, ensure_ascii=False))

ensure_query_binary()
ensure_tablebase()

with gr.Blocks(title="Bestemshe — Perfect-Play Explorer", fill_width=True) as demo:
    gr.HTML(INDEX_MARKUP)
    inp = gr.Textbox(elem_id="oracle_in")
    out = gr.Textbox(elem_id="oracle_out")
    btn = gr.Button("bridge", elem_id="oracle_btn")
    btn.click(oracle_bridge, inp, out)
    demo.load(None, None, None, js=INDEX_JS)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)))
