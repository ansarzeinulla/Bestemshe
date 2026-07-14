"""Bestemshe Perfect-Play Explorer.

A custom HTML/JS front end (multilingual, keyboard-driven, rewritable history)
talks to the C++ tablebase oracle through a hidden Gradio bridge. Keeping the
UI client-side lets us do global keyboard handling, arrow navigation, clickable
history and language switching that Gradio's own components cannot express.
"""

import json
import os
import subprocess

import gradio as gr

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
INDEX_MARKUP = r"""
<style>
  #oracle_in, #oracle_out, #oracle_btn { display: none !important; }
  #bb-wrap { max-width: 640px; margin: 0 auto; font-family: system-ui, sans-serif; color: #222; }
  #bb-wrap * { box-sizing: border-box; }
  .bb-top { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
  .bb-langs { display: flex; gap: 4px; }
  .bb-lang { cursor: pointer; border: 1px solid transparent; background: none; font-size: 20px;
             border-radius: 8px; padding: 2px 4px; line-height: 1; }
  .bb-lang.on { border-color: #d9822b; background: #fff3dc; }
  .bb-spacer { flex: 1; }
  .bb-icon { cursor: pointer; border: 1px solid #e2c98a; background: #fff8e6; border-radius: 10px;
             font-size: 18px; padding: 6px 10px; line-height: 1; }
  .bb-icon:hover { background: #ffedc2; }
  .bb-status { text-align: center; font-weight: 700; font-size: 18px; margin: 6px 0 12px;
               min-height: 24px; color: #7a5a12; }
  .bb-board { background: linear-gradient(160deg, #fffdf2 0%, #fff2c2 100%);
              border: 2px solid #e9cf7a; border-radius: 20px; padding: 16px; }
  .bb-kazan { text-align: center; font-weight: 800; color: #7a5a12; font-size: 22px; margin: 2px 0; }
  .bb-row { display: flex; gap: 12px; justify-content: center; margin: 12px 0; }
  .bb-pit { position: relative; width: 62px; height: 62px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: 22px; font-weight: 800; color: #111;
            background: radial-gradient(circle at 35% 30%, #f4ad55 0%, #d9822b 55%, #b5661d 100%);
            box-shadow: inset 0 -3px 6px rgba(0,0,0,0.25), 0 2px 3px rgba(0,0,0,0.2);
            border: 4px solid transparent; }
  .bb-pit.mv { cursor: pointer; }
  .bb-pit.mv:hover { transform: translateY(-2px); }
  .bb-pit.WIN  { border-color: #2e7d32; }
  .bb-pit.DRAW { border-color: #f0a020; }
  .bb-pit.LOSS { border-color: #c62828; }
  .bb-badge { position: absolute; top: -8px; left: -6px; background: #333; color: #fff;
              font-size: 12px; font-weight: 700; border-radius: 50%; width: 20px; height: 20px;
              display: flex; align-items: center; justify-content: center; }
  .bb-legend { display: flex; gap: 14px; justify-content: center; font-size: 13px; color: #555;
               margin: 10px 0; flex-wrap: wrap; }
  .bb-legend span { display: inline-flex; align-items: center; gap: 5px; }
  .bb-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
  .bb-nav { display: flex; gap: 6px; justify-content: center; margin: 10px 0; flex-wrap: wrap; }
  .bb-nav button { cursor: pointer; border: 1px solid #e2c98a; background: #fff8e6; border-radius: 10px;
                   font-size: 17px; font-weight: 700; padding: 8px 12px; min-width: 42px; }
  .bb-nav button:hover { background: #ffedc2; }
  .bb-hist-title { font-weight: 700; color: #7a5a12; margin: 10px 0 4px; }
  .bb-hist { background: #fffdf5; border: 1px solid #eadfb5; border-radius: 12px; padding: 10px;
             min-height: 48px; font-family: ui-monospace, monospace; line-height: 1.9; font-size: 15px; }
  .bb-turn { color: #999; margin-right: 4px; }
  .bb-mv { cursor: pointer; padding: 1px 6px; border-radius: 6px; margin-right: 4px; }
  .bb-mv:hover { background: #ffedc2; }
  .bb-mv.on { background: #d9822b; color: #fff; }
  .bb-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.45); display: none;
                align-items: center; justify-content: center; z-index: 1000; }
  .bb-overlay.open { display: flex; }
  .bb-modal { background: #fff; border-radius: 16px; padding: 22px; max-width: 460px; width: 92%;
              max-height: 88vh; overflow: auto; box-shadow: 0 10px 40px rgba(0,0,0,0.3); }
  .bb-modal h3 { margin: 0 0 12px; color: #7a5a12; }
  .bb-modal textarea { width: 100%; font-family: ui-monospace, monospace; font-size: 15px;
                       padding: 8px; border: 1px solid #ccc; border-radius: 8px; }
  .bb-modal .hint { font-size: 14px; color: #555; margin: 8px 0 14px; line-height: 1.5; }
  .bb-modal .err { color: #c62828; font-size: 14px; margin-top: 8px; min-height: 18px; }
  .bb-modal .btns { display: flex; gap: 8px; justify-content: flex-end; margin-top: 14px; }
  .bb-modal .btns button { cursor: pointer; border-radius: 10px; padding: 8px 16px; font-weight: 700;
                           border: 1px solid #d9822b; }
  .bb-modal .primary { background: #d9822b; color: #fff; }
  .bb-modal .ghost { background: #fff; color: #7a5a12; }
</style>
<div id="bb-wrap"><div id="bb-app"></div>
  <div class="bb-overlay" id="bb-setup"><div class="bb-modal">
    <h3 id="bb-setup-title"></h3>
    <textarea id="bb-fen" rows="2"></textarea>
    <div class="hint" id="bb-fen-help"></div>
    <div class="err" id="bb-setup-err"></div>
    <div class="btns"><button class="ghost" data-act="close" data-modal="bb-setup" id="bb-setup-close"></button>
      <button class="primary" data-act="apply" id="bb-setup-apply"></button></div>
  </div></div>
  <div class="bb-overlay" id="bb-help"><div class="bb-modal">
    <h3 id="bb-help-title"></h3>
    <div class="hint" id="bb-help-body"></div>
    <div class="btns"><button class="primary" data-act="close" data-modal="bb-help" id="bb-help-close"></button></div>
  </div></div>
</div>
"""

INDEX_JS = r"""
() => {
  if (window.__bbInit) return; window.__bbInit = true;
  const DEFAULT = "0 0 5 5 5 5 5 5 5 5 5 5";

  const I18N = {
    EN: { flag:"🇬🇧", toMove:"to move", wins:"wins!", drawLoop:"Infinite loop — draw",
      history:"History", newGame:"New game", setup:"Set position", help:"Help", pgn:"PGN",
      apply:"Apply", close:"Close", fenLabel:"Position (12 numbers)",
      fenHelp:"Enter 12 numbers: Bastaushi's kazan, Kostaushi's kazan, Bastaushi's 5 pits, then Kostaushi's 5 pits. They must total 50, and Bastaushi moves first.",
      helpTitle:"How to play", legWin:"win", legDraw:"draw", legLoss:"loss",
      helpBody:["Click a highlighted pit, or press 1–5, to play that pit's move.",
        "Press 0 to play a random optimal move.",
        "← previous · → next · ↑ start · ↓ end",
        "Click a move in the history to jump there. Playing a new move rewrites the history from that point.",
        "Green = the side to move wins · amber = draw · red = the side to move loses."] },
    KZ: { flag:"🇰🇿", toMove:"жүреді", wins:"жеңеді!", drawLoop:"Шексіз цикл — тең ойын",
      history:"Тарих", newGame:"Жаңа ойын", setup:"Позиция", help:"Көмек", pgn:"PGN",
      apply:"Қолдану", close:"Жабу", fenLabel:"Позиция (12 сан)",
      fenHelp:"12 сан енгізіңіз: Бастаушының қазаны, Қостаушының қазаны, Бастаушының 5 ұясы, содан кейін Қостаушының 5 ұясы. Қосындысы 50 болуы керек. Алдымен Бастаушы жүреді.",
      helpTitle:"Қалай ойнау керек", legWin:"жеңіс", legDraw:"тең", legLoss:"жеңіліс",
      helpBody:["Белгіленген ұяны басыңыз немесе 1–5 пернелерін басыңыз.",
        "Кездейсоқ оңтайлы жүріс үшін 0 басыңыз.",
        "← артқа · → алға · ↑ басына · ↓ соңына",
        "Тарихтағы жүріске басып өтіңіз. Жаңа жүріс тарихты сол жерден қайта жазады.",
        "Жасыл — жүруші жеңеді · сары — тең · қызыл — жеңіледі."] },
    RU: { flag:"🇷🇺", toMove:"ходит", wins:"выигрывает!", drawLoop:"Бесконечный цикл — ничья",
      history:"История", newGame:"Новая игра", setup:"Позиция", help:"Помощь", pgn:"PGN",
      apply:"Применить", close:"Закрыть", fenLabel:"Позиция (12 чисел)",
      fenHelp:"Введите 12 чисел: казан Бастаушы, казан Костаушы, 5 лунок Бастаушы, затем 5 лунок Костаушы. В сумме — 50. Первым ходит Бастаушы.",
      helpTitle:"Как играть", legWin:"выигр.", legDraw:"ничья", legLoss:"проигр.",
      helpBody:["Нажмите на подсвеченную лунку или клавиши 1–5, чтобы сделать ход.",
        "Нажмите 0 для случайного оптимального хода.",
        "← назад · → вперёд · ↑ в начало · ↓ в конец",
        "Нажмите на ход в истории, чтобы перейти к нему. Новый ход перезапишет историю с этого места.",
        "Зелёный — ходящий выигрывает · жёлтый — ничья · красный — проигрывает."] },
    KG: { flag:"🇰🇬", toMove:"жүрөт", wins:"жеңет!", drawLoop:"Түгөнбөс цикл — тең",
      history:"Тарых", newGame:"Жаңы оюн", setup:"Позиция", help:"Жардам", pgn:"PGN",
      apply:"Колдонуу", close:"Жабуу", fenLabel:"Позиция (12 сан)",
      fenHelp:"12 сан киргизиңиз: Бастаушынын казаны, Костаушунун казаны, Бастаушынын 5 уясы, андан кийин Костаушунун 5 уясы. Суммасы 50 болушу керек. Биринчи Бастаушы жүрөт.",
      helpTitle:"Кантип ойноо керек", legWin:"жеңиш", legDraw:"тең", legLoss:"жеңилүү",
      helpBody:["Белгиленген уяны басыңыз же 1–5 баскычтарын басыңыз.",
        "Кокус оптималдуу жүрүш үчүн 0 басыңыз.",
        "← артка · → алдыга · ↑ башына · ↓ аягына",
        "Тарыхтагы жүрүшкө басып өтүңүз. Жаңы жүрүш тарыхты ошол жерден кайра жазат.",
        "Жашыл — жүрүүчү жеңет · сары — тең · кызыл — жеңилет."] },
    TR: { flag:"🇹🇷", toMove:"oynayacak", wins:"kazanır!", drawLoop:"Sonsuz döngü — beraberlik",
      history:"Geçmiş", newGame:"Yeni oyun", setup:"Konum", help:"Yardım", pgn:"PGN",
      apply:"Uygula", close:"Kapat", fenLabel:"Konum (12 sayı)",
      fenHelp:"12 sayı girin: Bastauşı'nın kazanı, Kostauşı'nın kazanı, Bastauşı'nın 5 kuyusu, sonra Kostauşı'nın 5 kuyusu. Toplamı 50 olmalı. İlk Bastauşı oynar.",
      helpTitle:"Nasıl oynanır", legWin:"galip", legDraw:"beraberlik", legLoss:"mağlup",
      helpBody:["Vurgulanan bir kuyuya tıklayın veya 1–5 tuşlarına basın.",
        "Rastgele en iyi hamle için 0'a basın.",
        "← önceki · → sonraki · ↑ başa · ↓ sona",
        "Geçmişteki bir hamleye tıklayarak oraya gidin. Yeni hamle geçmişi o noktadan yeniden yazar.",
        "Yeşil — oynayan kazanır · sarı — beraberlik · kırmızı — kaybeder."] }
  };

  let lang = "EN";
  let initialFen = DEFAULT;
  let line = [];      // nodes {state, ply, moveIn, key, moves, gameOver, winner}
  let played = [];    // notations, aligned to line transitions
  let cursor = 0;
  let busy = false;
  const t = (k) => (I18N[lang][k] !== undefined ? I18N[lang][k] : I18N.EN[k]);
  const playerName = (ply) => (ply % 2 === 0 ? "Bastaushi" : "Kostaushi");

  // ---- oracle bridge ----
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
      // Short per-attempt timeout so a dropped Gradio connection is retried quickly.
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
    if (node.moves.length === 0) { node.gameOver = "nomove"; node.winner = playerName((ply + 1) % 2); }
    return node;
  }

  async function newGame(fen) {
    const n0 = await makeNode(fen, 0, null);
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
                  moves: [], gameOver: "win", winner: playerName(node.ply) };
      } else {
        const repeat = line.some((nd) => nd.key === (cp % 2) + ":" + cs);
        child = await makeNode(cs, cp, notation);
        child.moveIn = notation;
        if (repeat) { child.gameOver = "draw"; child.winner = null; child.moves = []; }
      }
      line.push(child); played.push(notation); cursor = line.length - 1; render();
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
    if (i === 0) { const b = optimal(node); if (b.length) await playMove(node, b[Math.floor(Math.random() * b.length)]); return; }
    const m = node.moves.find((x) => x.from === i);
    if (m) await playMove(node, m);
  }
  function go(idx) { cursor = Math.max(0, Math.min(line.length - 1, idx)); render(); }

  function absView(state, ply) {
    const v = state.split(" ").map(Number);
    const kM = v[0], kO = v[1], b = v.slice(2);
    if (ply % 2 === 0) return { bk: kM, kk: kO, bp: b.slice(0, 5), kp: b.slice(5, 10), moverBottom: true };
    return { bk: kO, kk: kM, bp: b.slice(5, 10), kp: b.slice(0, 5), moverBottom: false };
  }

  function pgnBody() {
    let out = [];
    for (let i = 0; i < played.length; i += 2) {
      out.push((i / 2 + 1) + ". " + played.slice(i, i + 2).join(" "));
    }
    return out.join("\n");
  }
  function downloadPgn() {
    const pgn = '[Event "Bestemshe Perfect-Play Analysis"]\n[Site "Bestemshe Explorer"]\n[FEN "' +
      initialFen + '"]\n\n' + pgnBody() + "\n";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([pgn], { type: "text/plain" }));
    a.download = "bestemshe.pgn"; a.click();
  }

  // ---- rendering ----
  function pitHtml(count, idx, isMover, move) {
    const cls = "bb-pit" + (isMover && move ? " mv " + move.result : "");
    const badge = isMover ? '<span class="bb-badge">' + idx + "</span>" : "";
    const data = isMover && move ? ' data-act="pit" data-i="' + idx + '"' : "";
    return '<div class="' + cls + '"' + data + ">" + badge + count + "</div>";
  }

  function render() {
    const node = line[cursor];
    const av = absView(node.state, node.ply);
    const moverMoves = new Map();
    if (!node.gameOver && !node.error) node.moves.forEach((m) => moverMoves.set(m.from, m));

    let top = "";
    for (let i = 5; i >= 1; i--) top += pitHtml(av.kp[i - 1], i, !av.moverBottom, moverMoves.get(i));
    let bottom = "";
    for (let i = 1; i <= 5; i++) bottom += pitHtml(av.bp[i - 1], i, av.moverBottom, moverMoves.get(i));

    let status;
    if (node.error) status = "⚠️ " + node.error;
    else if (node.gameOver === "draw") status = t("drawLoop");
    else if (node.gameOver) status = node.winner + " " + t("wins");
    else status = playerName(node.ply) + " " + t("toMove");

    const langs = Object.keys(I18N).map((L) =>
      '<button class="bb-lang' + (L === lang ? " on" : "") + '" data-act="lang" data-lang="' + L + '">' +
      I18N[L].flag + "</button>").join("");

    // history
    let hist = "";
    for (let i = 0; i < played.length; i += 2) {
      hist += '<span class="bb-turn">' + (i / 2 + 1) + ".</span>";
      for (let j = i; j < Math.min(i + 2, played.length); j++) {
        hist += '<span class="bb-mv' + (j + 1 === cursor ? " on" : "") + '" data-act="hist" data-idx="' + j + '">' + played[j] + "</span>";
      }
    }
    if (!hist) hist = "&nbsp;";

    const legend = '<div class="bb-legend">' +
      '<span><i class="bb-dot" style="background:#2e7d32"></i>' + t("legWin") + "</span>" +
      '<span><i class="bb-dot" style="background:#f0a020"></i>' + t("legDraw") + "</span>" +
      '<span><i class="bb-dot" style="background:#c62828"></i>' + t("legLoss") + "</span></div>";

    document.getElementById("bb-app").innerHTML =
      '<div class="bb-top"><div class="bb-langs">' + langs + '</div><div class="bb-spacer"></div>' +
      '<button class="bb-icon" data-act="new" title="' + t("newGame") + '">↺</button>' +
      '<button class="bb-icon" data-act="open" data-modal="bb-setup" title="' + t("setup") + '">⚙️</button>' +
      '<button class="bb-icon" data-act="open" data-modal="bb-help" title="' + t("help") + '">❔</button>' +
      '<button class="bb-icon" data-act="pgn" title="' + t("pgn") + '">⬇️</button></div>' +
      '<div class="bb-status">' + status + "</div>" +
      '<div class="bb-board"><div class="bb-kazan">' + av.kk + "</div>" +
      '<div class="bb-row">' + top + "</div><div class=\"bb-row\">" + bottom + "</div>" +
      '<div class="bb-kazan">' + av.bk + "</div></div>" +
      legend +
      '<div class="bb-nav"><button data-act="nav" data-d="up">↑</button>' +
      '<button data-act="nav" data-d="left">←</button>' +
      '<button data-act="nav" data-d="right">→</button>' +
      '<button data-act="nav" data-d="down">↓</button>' +
      '<button data-act="num" data-i="1">1</button><button data-act="num" data-i="2">2</button>' +
      '<button data-act="num" data-i="3">3</button><button data-act="num" data-i="4">4</button>' +
      '<button data-act="num" data-i="5">5</button><button data-act="num" data-i="0">🎲</button></div>' +
      '<div class="bb-hist-title">' + t("history") + '</div><div class="bb-hist">' + hist + "</div>";

    // static modal labels
    document.getElementById("bb-setup-title").textContent = t("setup");
    document.getElementById("bb-fen-help").textContent = t("fenHelp");
    document.getElementById("bb-setup-apply").textContent = t("apply");
    document.getElementById("bb-setup-close").textContent = t("close");
    document.getElementById("bb-help-title").textContent = t("helpTitle");
    document.getElementById("bb-help-body").innerHTML = t("helpBody").join("<br>");
    document.getElementById("bb-help-close").textContent = t("close");
  }

  function anyModalOpen() {
    return document.querySelector(".bb-overlay.open") !== null;
  }

  // ---- events ----
  document.getElementById("bb-wrap").addEventListener("click", async (e) => {
    const el = e.target.closest("[data-act]"); if (!el) return;
    const act = el.dataset.act;
    if (act === "lang") { lang = el.dataset.lang; render(); }
    else if (act === "new") { await newGame(DEFAULT); }
    else if (act === "pgn") { downloadPgn(); }
    else if (act === "open") {
      const m = document.getElementById(el.dataset.modal);
      if (el.dataset.modal === "bb-setup") {
        document.getElementById("bb-fen").value = initialFen;
        document.getElementById("bb-setup-err").textContent = "";
      }
      m.classList.add("open");
    }
    else if (act === "close") { document.getElementById(el.dataset.modal).classList.remove("open"); }
    else if (act === "apply") {
      const fen = document.getElementById("bb-fen").value.trim();
      const err = await newGame(fen);
      if (err) document.getElementById("bb-setup-err").textContent = err;
      else document.getElementById("bb-setup").classList.remove("open");
    }
    else if (act === "pit") { await inputIndex(parseInt(el.dataset.i, 10)); }
    else if (act === "num") { await inputIndex(parseInt(el.dataset.i, 10)); }
    else if (act === "hist") { go(parseInt(el.dataset.idx, 10) + 1); }
    else if (act === "nav") {
      const d = el.dataset.d;
      if (d === "up") go(0); else if (d === "down") go(line.length - 1);
      else if (d === "left") go(cursor - 1); else go(cursor + 1);
    }
  });
  // close overlay on backdrop click
  document.querySelectorAll(".bb-overlay").forEach((o) => o.addEventListener("click", (e) => {
    if (e.target === o) o.classList.remove("open");
  }));

  document.addEventListener("keydown", (e) => {
    if (anyModalOpen()) { if (e.key === "Escape") document.querySelectorAll(".bb-overlay.open").forEach((o) => o.classList.remove("open")); return; }
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    if (tag === "TEXTAREA" || tag === "INPUT") return;
    if (e.key >= "0" && e.key <= "5") { inputIndex(parseInt(e.key, 10)); e.preventDefault(); }
    else if (e.key === "ArrowRight") { go(cursor + 1); e.preventDefault(); }
    else if (e.key === "ArrowLeft") { go(cursor - 1); e.preventDefault(); }
    else if (e.key === "ArrowUp") { go(0); e.preventDefault(); }
    else if (e.key === "ArrowDown") { go(line.length - 1); e.preventDefault(); }
  });

  // kick off once the bridge textareas exist
  const boot = setInterval(() => {
    if (document.querySelector("#oracle_in textarea") && document.querySelector("#oracle_btn")) {
      clearInterval(boot); newGame(DEFAULT);
    }
  }, 100);
}
"""

ensure_query_binary()
ensure_tablebase()

with gr.Blocks(title="Bestemshe — Perfect-Play Explorer") as demo:
    gr.HTML(INDEX_MARKUP)
    inp = gr.Textbox(elem_id="oracle_in")
    out = gr.Textbox(elem_id="oracle_out")
    btn = gr.Button("bridge", elem_id="oracle_btn")
    btn.click(oracle_bridge, inp, out)
    demo.load(None, None, None, js=INDEX_JS)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)))
