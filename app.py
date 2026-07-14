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
  #bb-wrap { max-width: 980px; margin: 0 auto; font-family: system-ui, sans-serif; color: #2a2118; }
  #bb-wrap * { box-sizing: border-box; }
  #bb-cols { display: flex; gap: 20px; align-items: flex-start; }
  #bb-main { flex: 1 1 620px; min-width: 0; }
  #bb-side { flex: 0 0 280px; display: flex; flex-direction: column; gap: 12px; }
  @media (max-width: 860px) {
    #bb-cols { flex-direction: column; }
    #bb-side { flex: 1 1 auto; width: 100%; }
  }

  .bb-card { background: #fffdf5; border: 1px solid #ecdfb8; border-radius: 16px; padding: 14px; }

  .bb-status { text-align: center; font-weight: 700; font-size: 19px; margin: 0 0 12px;
               min-height: 26px; color: #6d500e; }
  .bb-status.end { color: #1b5e20; }

  .bb-board { background: linear-gradient(160deg, #fffdf2 0%, #fdf0bf 100%);
              border: 2px solid #e9cf7a; border-radius: 22px; padding: 18px 14px;
              box-shadow: 0 6px 18px rgba(160,120,30,0.10); }
  .bb-kazan { display: flex; justify-content: center; align-items: center; gap: 10px;
              font-weight: 800; color: #6d500e; font-size: 15px; margin: 4px 0; }
  .bb-kazan .num { background: #f6e2a0; border-radius: 12px; padding: 3px 14px; font-size: 20px; }
  .bb-row { display: flex; gap: 3.5%; justify-content: center; margin: 14px 0; }
  .bb-pit { width: 15%; max-width: 74px; aspect-ratio: 1; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: clamp(17px, 3vw, 24px); font-weight: 800; color: #14100a;
            background: radial-gradient(circle at 35% 30%, #f4ad55 0%, #d9822b 55%, #b5661d 100%);
            box-shadow: inset 0 -3px 6px rgba(0,0,0,0.25), 0 2px 3px rgba(0,0,0,0.2);
            border: 4px solid transparent; transition: transform .08s ease; }
  .bb-pit.mv { cursor: pointer; }
  .bb-pit.mv:hover { transform: translateY(-3px); }
  .bb-pit.WIN  { border-color: #2e7d32; }
  .bb-pit.DRAW { border-color: #f0a020; }
  .bb-pit.LOSS { border-color: #c62828; }

  .bb-legend { display: flex; gap: 16px; justify-content: center; font-size: 13px; color: #7a6a4a;
               margin: 12px 0 0; flex-wrap: wrap; }
  .bb-legend span { display: inline-flex; align-items: center; gap: 6px; }
  .bb-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }

  .bb-side-row { display: flex; gap: 8px; align-items: center; }
  #bb-langsel { width: 100%; font-size: 15px; padding: 9px 10px; border-radius: 12px;
                border: 1px solid #e2c98a; background: #fffdf5; color: #2a2118; cursor: pointer; }
  .bb-actions { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
  .bb-icon { cursor: pointer; border: 1px solid #e2c98a; background: #fff8e6; border-radius: 12px;
             font-size: 19px; padding: 10px 0; line-height: 1; text-align: center; }
  .bb-icon:hover { background: #ffedc2; }

  .bb-hist-title { font-weight: 700; color: #6d500e; margin: 0 0 8px; font-size: 14px;
                   text-transform: uppercase; letter-spacing: .04em; }
  .bb-hist { font-family: ui-monospace, monospace; line-height: 2.0; font-size: 15px;
             max-height: 340px; overflow-y: auto; }
  .bb-hist:empty::after { content: "—"; color: #c9b98e; }
  .bb-turn { color: #b3a276; margin-right: 4px; }
  .bb-mv { cursor: pointer; padding: 2px 7px; border-radius: 7px; margin-right: 4px; }
  .bb-mv:hover { background: #ffedc2; }
  .bb-mv.on { background: #d9822b; color: #fff; }

  .bb-overlay { position: fixed; inset: 0; background: rgba(30,22,8,0.5); display: none;
                align-items: center; justify-content: center; z-index: 1000; }
  .bb-overlay.open { display: flex; }
  .bb-modal { background: #fffdf8; border-radius: 18px; padding: 24px; max-width: 500px; width: 92%;
              max-height: 88vh; overflow: auto; box-shadow: 0 14px 48px rgba(0,0,0,0.35); }
  .bb-modal h3 { margin: 0 0 14px; color: #6d500e; }
  .bb-modal textarea { width: 100%; font-family: ui-monospace, monospace; font-size: 15px;
                       padding: 10px; border: 1px solid #d8c692; border-radius: 10px; background: #fff; }
  .bb-modal .hint { font-size: 14.5px; color: #4c4130; margin: 10px 0 4px; line-height: 1.65; }
  .bb-modal .hint b { color: #6d500e; }
  .bb-modal .keys { display: grid; grid-template-columns: 64px 1fr; gap: 6px 12px;
                    font-size: 14.5px; color: #4c4130; margin: 10px 0; align-items: center; }
  .bb-modal .keys kbd { background: #f1e5c0; border: 1px solid #d8c692; border-radius: 6px;
                        padding: 2px 8px; font-family: ui-monospace, monospace; font-size: 13px;
                        text-align: center; }
  .bb-modal .err { color: #c62828; font-size: 14px; margin-top: 8px; min-height: 18px; }
  .bb-modal .btns { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
  .bb-modal .btns button { cursor: pointer; border-radius: 10px; padding: 9px 18px; font-weight: 700;
                           border: 1px solid #d9822b; font-size: 14px; }
  .bb-modal .primary { background: #d9822b; color: #fff; }
  .bb-modal .ghost { background: #fff; color: #6d500e; }
</style>
<div id="bb-wrap">
  <div id="bb-cols">
    <div id="bb-main">
      <div class="bb-status" id="bb-status"></div>
      <div class="bb-board" id="bb-board"></div>
      <div class="bb-legend" id="bb-legend"></div>
    </div>
    <div id="bb-side">
      <select id="bb-langsel">
        <option value="EN">🇬🇧 English</option>
        <option value="KZ">🇰🇿 Қазақша</option>
        <option value="RU">🇷🇺 Русский</option>
        <option value="KG">🇰🇬 Кыргызча</option>
        <option value="TR">🇹🇷 Türkçe</option>
      </select>
      <div class="bb-actions">
        <button class="bb-icon" data-act="new" id="bb-btn-new">↺</button>
        <button class="bb-icon" data-act="open" data-modal="bb-setup" id="bb-btn-setup">⚙️</button>
        <button class="bb-icon" data-act="open" data-modal="bb-help" id="bb-btn-help">❔</button>
        <button class="bb-icon" data-act="pgn" id="bb-btn-pgn">⬇️</button>
      </div>
      <div class="bb-card">
        <div class="bb-hist-title" id="bb-hist-title"></div>
        <div class="bb-hist" id="bb-hist"></div>
      </div>
    </div>
  </div>

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
    <div class="hint" id="bb-help-intro"></div>
    <div class="keys" id="bb-help-keys"></div>
    <div class="hint" id="bb-help-extra"></div>
    <div class="btns"><button class="primary" data-act="close" data-modal="bb-help" id="bb-help-close"></button></div>
  </div></div>
</div>
"""

INDEX_JS = r"""
() => {
  if (window.__bbInit) return; window.__bbInit = true;
  const DEFAULT = "0 0 5 5 5 5 5 5 5 5 5 5";

  const I18N = {
    EN: { toMove:"to move", wins:"wins!", drawLoop:"Infinite loop — draw",
      history:"Moves", newGame:"New game", setup:"Set position", help:"How to play", pgn:"Download PGN",
      apply:"Start", close:"Close",
      fenHelp:"Enter 12 numbers separated by spaces: Bastaushi's kazan, Kostaushi's kazan, Bastaushi's 5 pits, then Kostaushi's 5 pits. All stones together must total 50. Bastaushi always moves first.",
      helpIntro:"Bestemshe is completely solved. The colored ring on each pit shows the outcome of that move with perfect play afterwards: <b>green</b> — the player who moves wins, <b>amber</b> — draw, <b>red</b> — the player who moves loses. Click a pit to play it.",
      keys:[["1–5","play a pit: counted from each player's own left hand (bottom player left→right, top player right→left)"],
            ["0","play a random optimal move"],["←","previous position"],["→","next position"],
            ["↑","back to the starting position"],["↓","jump to the last move"]],
      helpExtra:"Click any move in the list to jump back to it. Playing a different move from there rewrites the rest of the line. If a position ever repeats, the game stops as an infinite-loop draw.",
      legWin:"win", legDraw:"draw", legLoss:"loss" },
    KZ: { toMove:"жүреді", wins:"жеңеді!", drawLoop:"Шексіз цикл — тең ойын",
      history:"Жүрістер", newGame:"Жаңа ойын", setup:"Позиция қою", help:"Қалай ойнау", pgn:"PGN жүктеу",
      apply:"Бастау", close:"Жабу",
      fenHelp:"Бос орынмен бөлінген 12 сан енгізіңіз: Бастаушының қазаны, Қостаушының қазаны, Бастаушының 5 ұясы, содан кейін Қостаушының 5 ұясы. Барлық тастардың қосындысы 50 болуы керек. Әрқашан Бастаушы бірінші жүреді.",
      helpIntro:"Бестемше толық шешілген ойын. Әр ұядағы түсті сақина сол жүрістен кейін мінсіз ойында кім жеңетінін көрсетеді: <b>жасыл</b> — жүруші жеңеді, <b>сары</b> — тең, <b>қызыл</b> — жүруші жеңіледі. Жүру үшін ұяны басыңыз.",
      keys:[["1–5","ұяны ойнау: әр ойыншы өз сол қолынан санайды (төменгі — солдан оңға, жоғарғы — оңнан солға)"],
            ["0","кездейсоқ оңтайлы жүріс"],["←","алдыңғы позиция"],["→","келесі позиция"],
            ["↑","бастапқы позицияға"],["↓","соңғы жүріске"]],
      helpExtra:"Тізімдегі кез келген жүрісті басып, соған ораласыз. Ол жерден басқа жүріс жасасаңыз, қалған тарих қайта жазылады. Позиция қайталанса, ойын шексіз цикл — тең деп тоқтайды.",
      legWin:"жеңіс", legDraw:"тең", legLoss:"жеңіліс" },
    RU: { toMove:"ходит", wins:"выигрывает!", drawLoop:"Бесконечный цикл — ничья",
      history:"Ходы", newGame:"Новая игра", setup:"Задать позицию", help:"Как играть", pgn:"Скачать PGN",
      apply:"Начать", close:"Закрыть",
      fenHelp:"Введите 12 чисел через пробел: казан Бастаушы, казан Костаушы, 5 лунок Бастаушы, затем 5 лунок Костаушы. Сумма всех камней должна быть 50. Первым всегда ходит Бастаушы.",
      helpIntro:"Бестемше полностью решена. Цветное кольцо на лунке показывает исход этого хода при идеальной игре дальше: <b>зелёное</b> — ходящий выигрывает, <b>жёлтое</b> — ничья, <b>красное</b> — ходящий проигрывает. Нажмите на лунку, чтобы сделать ход.",
      keys:[["1–5","сыграть лунку: каждый считает от своей левой руки (нижний — слева направо, верхний — справа налево)"],
            ["0","случайный оптимальный ход"],["←","предыдущая позиция"],["→","следующая позиция"],
            ["↑","к начальной позиции"],["↓","к последнему ходу"]],
      helpExtra:"Нажмите на любой ход в списке, чтобы вернуться к нему. Сыграв оттуда другой ход, вы перепишете остаток партии. Если позиция повторяется, игра останавливается как ничья из-за бесконечного цикла.",
      legWin:"выигрыш", legDraw:"ничья", legLoss:"проигрыш" },
    KG: { toMove:"жүрөт", wins:"жеңет!", drawLoop:"Түгөнбөс цикл — тең",
      history:"Жүрүштөр", newGame:"Жаңы оюн", setup:"Позиция коюу", help:"Кантип ойноо", pgn:"PGN жүктөө",
      apply:"Баштоо", close:"Жабуу",
      fenHelp:"Боштук менен бөлүнгөн 12 сан киргизиңиз: Бастаушынын казаны, Костаушунун казаны, Бастаушынын 5 уясы, андан кийин Костаушунун 5 уясы. Бардык таштардын суммасы 50 болушу керек. Ар дайым Бастаушы биринчи жүрөт.",
      helpIntro:"Бестемше толук чечилген оюн. Ар бир уядагы түстүү шакек ошол жүрүштөн кийин мыкты оюнда ким утаарын көрсөтөт: <b>жашыл</b> — жүрүүчү утат, <b>сары</b> — тең, <b>кызыл</b> — жүрүүчү утулат. Жүрүш үчүн уяны басыңыз.",
      keys:[["1–5","уяны ойноо: ар ким өз сол колунан санайт (ылдыйкы — солдон оңго, үстүнкү — оңдон солго)"],
            ["0","кокус оптималдуу жүрүш"],["←","мурунку позиция"],["→","кийинки позиция"],
            ["↑","баштапкы позицияга"],["↓","акыркы жүрүшкө"]],
      helpExtra:"Тизмедеги каалаган жүрүштү басып, ага кайтасыз. Ошол жерден башка жүрүш жасасаңыз, калган тарых кайра жазылат. Позиция кайталанса, оюн түгөнбөс цикл — тең деп токтойт.",
      legWin:"утуш", legDraw:"тең", legLoss:"утулуш" },
    TR: { toMove:"oynayacak", wins:"kazanır!", drawLoop:"Sonsuz döngü — beraberlik",
      history:"Hamleler", newGame:"Yeni oyun", setup:"Konum ayarla", help:"Nasıl oynanır", pgn:"PGN indir",
      apply:"Başlat", close:"Kapat",
      fenHelp:"Boşlukla ayrılmış 12 sayı girin: Bastauşı'nın kazanı, Kostauşı'nın kazanı, Bastauşı'nın 5 kuyusu, sonra Kostauşı'nın 5 kuyusu. Tüm taşların toplamı 50 olmalı. İlk hamleyi her zaman Bastauşı yapar.",
      helpIntro:"Bestemshe tamamen çözülmüş bir oyundur. Her kuyudaki renkli halka, o hamleden sonra kusursuz oyunla sonucu gösterir: <b>yeşil</b> — hamleyi yapan kazanır, <b>sarı</b> — beraberlik, <b>kırmızı</b> — hamleyi yapan kaybeder. Oynamak için bir kuyuya tıklayın.",
      keys:[["1–5","kuyu oyna: her oyuncu kendi solundan sayar (alttaki soldan sağa, üstteki sağdan sola)"],
            ["0","rastgele en iyi hamle"],["←","önceki konum"],["→","sonraki konum"],
            ["↑","başlangıç konumuna"],["↓","son hamleye"]],
      helpExtra:"Listedeki herhangi bir hamleye tıklayarak oraya dönün. Oradan farklı bir hamle oynarsanız devamı yeniden yazılır. Bir konum tekrarlanırsa oyun sonsuz döngü beraberliğiyle durur.",
      legWin:"galibiyet", legDraw:"beraberlik", legLoss:"mağlubiyet" }
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
    const data = isMover && move ? ' data-act="pit" data-i="' + idx + '"' : "";
    return '<div class="' + cls + '"' + data + ">" + count + "</div>";
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

    const statusEl = document.getElementById("bb-status");
    statusEl.classList.remove("end");
    if (node.error) statusEl.textContent = "⚠️ " + node.error;
    else if (node.gameOver === "draw") { statusEl.textContent = "🔁 " + t("drawLoop"); statusEl.classList.add("end"); }
    else if (node.gameOver) { statusEl.textContent = "🏆 " + node.winner + " " + t("wins"); statusEl.classList.add("end"); }
    else statusEl.textContent = playerName(node.ply) + " " + t("toMove");

    document.getElementById("bb-board").innerHTML =
      '<div class="bb-kazan">Kostaushi<span class="num">' + av.kk + "</span></div>" +
      '<div class="bb-row">' + top + "</div><div class=\"bb-row\">" + bottom + "</div>" +
      '<div class="bb-kazan">Bastaushi<span class="num">' + av.bk + "</span></div>";

    document.getElementById("bb-legend").innerHTML =
      '<span><i class="bb-dot" style="background:#2e7d32"></i>' + t("legWin") + "</span>" +
      '<span><i class="bb-dot" style="background:#f0a020"></i>' + t("legDraw") + "</span>" +
      '<span><i class="bb-dot" style="background:#c62828"></i>' + t("legLoss") + "</span>";

    let hist = "";
    for (let i = 0; i < played.length; i += 2) {
      hist += '<span class="bb-turn">' + (i / 2 + 1) + ".</span>";
      for (let j = i; j < Math.min(i + 2, played.length); j++) {
        hist += '<span class="bb-mv' + (j + 1 === cursor ? " on" : "") + '" data-act="hist" data-idx="' + j + '">' + played[j] + "</span>";
      }
    }
    document.getElementById("bb-hist").innerHTML = hist;
    document.getElementById("bb-hist-title").textContent = t("history");

    // toolbar tooltips + modal labels
    document.getElementById("bb-btn-new").title = t("newGame");
    document.getElementById("bb-btn-setup").title = t("setup");
    document.getElementById("bb-btn-help").title = t("help");
    document.getElementById("bb-btn-pgn").title = t("pgn");
    document.getElementById("bb-setup-title").textContent = t("setup");
    document.getElementById("bb-fen-help").textContent = t("fenHelp");
    document.getElementById("bb-setup-apply").textContent = t("apply");
    document.getElementById("bb-setup-close").textContent = t("close");
    document.getElementById("bb-help-title").textContent = t("help");
    document.getElementById("bb-help-intro").innerHTML = t("helpIntro");
    document.getElementById("bb-help-keys").innerHTML =
      t("keys").map((k) => "<kbd>" + k[0] + "</kbd><span>" + k[1] + "</span>").join("");
    document.getElementById("bb-help-extra").textContent = t("helpExtra");
    document.getElementById("bb-help-close").textContent = t("close");
  }

  function anyModalOpen() {
    return document.querySelector(".bb-overlay.open") !== null;
  }

  // ---- events ----
  document.getElementById("bb-langsel").addEventListener("change", (e) => { lang = e.target.value; render(); });

  document.getElementById("bb-wrap").addEventListener("click", async (e) => {
    const el = e.target.closest("[data-act]"); if (!el) return;
    const act = el.dataset.act;
    if (act === "new") { await newGame(DEFAULT); }
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
    else if (act === "hist") { go(parseInt(el.dataset.idx, 10) + 1); }
  });
  document.querySelectorAll(".bb-overlay").forEach((o) => o.addEventListener("click", (e) => {
    if (e.target === o) o.classList.remove("open");
  }));

  document.addEventListener("keydown", (e) => {
    if (anyModalOpen()) { if (e.key === "Escape") document.querySelectorAll(".bb-overlay.open").forEach((o) => o.classList.remove("open")); return; }
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    if (tag === "TEXTAREA" || tag === "INPUT" || tag === "SELECT") return;
    if (e.key >= "0" && e.key <= "5") { inputIndex(parseInt(e.key, 10)); e.preventDefault(); }
    else if (e.key === "ArrowRight") { go(cursor + 1); e.preventDefault(); }
    else if (e.key === "ArrowLeft") { go(cursor - 1); e.preventDefault(); }
    else if (e.key === "ArrowUp") { go(0); e.preventDefault(); }
    else if (e.key === "ArrowDown") { go(line.length - 1); e.preventDefault(); }
  });

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
