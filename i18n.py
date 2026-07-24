"""Single source of truth for every user-facing string, flag and language name.

`LANGUAGES` drives the language dropdown (code + flag + native name).
`TRANSLATIONS` holds every phrase, keyed by the same codes. app.py injects both
into the front-end as JSON, so there is exactly one place to edit copy.
"""

# code -> flag emoji + native language name (order = dropdown order)
LANGUAGES = [
    {"code": "EN", "flag": "🇬🇧", "name": "English"},
    {"code": "KZ", "flag": "🇰🇿", "name": "Қазақша"},
    {"code": "RU", "flag": "🇷🇺", "name": "Русский"},
    {"code": "KG", "flag": "🇰🇬", "name": "Кыргызча"},
    {"code": "TR", "flag": "🇹🇷", "name": "Türkçe"},
]

# Fixed player names (never translated — they are proper nouns of the game).
PLAYER_WHITE = "Bastaushi"   # White / Player, always moves first
PLAYER_BLACK = "Kostaushi"   # Black / God

TRANSLATIONS = {
    "EN": {
        "wins": "wins!",
        "drawLoop": "Infinite loop — draw",
        "loopHint": "The position repeated, so the game is a draw.",
        "history": "Moves",
        "newGame": "New game",
        "setup": "Set position",
        "help": "How to play",
        "pgn": "Download PGN",
        "apply": "Start",
        "close": "Close",
        "fenHelp": "Position format:  w1,w2,w3,w4,w5/b1,b2,b3,b4,b5 wKazan,bKazan side moveNo — "
                   "White is Bastaushi (moves first), Black is Kostaushi. 'side' is w or b. "
                   "All stones together must total 50. Example: 5,5,5,5,5/5,5,5,5,5 0,0 w 1",
        "helpIntro": "Bestemshe is completely solved. The colored ring on each pit shows the outcome "
                     "of that move with perfect play afterwards: <b>green</b> — the mover wins, "
                     "<b>amber</b> — draw, <b>red</b> — the mover loses. Click a pit to play it.",
        "keys": [
            ["1–5", "play one of your five pits (counted from each player's own left hand)"],
            ["0", "play a random optimal move"],
            ["9", "play a random move (any legal move, good or bad)"],
            ["← / A", "previous position"],
            ["→ / D", "next position"],
            ["↑ / W", "back to the starting position"],
            ["↓ / S", "jump to the last move"],
        ],
        "helpExtra": "Click any move in the list to jump back to it — playing a different move there "
                     "rewrites the rest of the line. If a position ever repeats, the game ends as an "
                     "infinite-loop draw. The Kazakh keyboard row (әіңғ… and қ, ұ) works for the digits too.",
        "authors": "Bestemshe Table Base, its Strong Solution proof and this God's algorithm were "
                   "created by Ansar Zeinulla & Murat Manassov.",
    },
    "KZ": {
        "wins": "жеңеді!",
        "drawLoop": "Шексіз цикл — тең ойын",
        "loopHint": "Позиция қайталанды, сондықтан ойын тең аяқталды.",
        "history": "Жүрістер",
        "newGame": "Жаңа ойын",
        "setup": "Позиция қою",
        "help": "Қалай ойнау",
        "pgn": "PGN жүктеу",
        "apply": "Бастау",
        "close": "Жабу",
        "fenHelp": "Позиция форматы:  w1,w2,w3,w4,w5/b1,b2,b3,b4,b5 wҚазан,bҚазан жүрушісі жүрісНө — "
                   "Ақ — Бастаушы (бірінші жүреді), Қара — Қостаушы. 'жүрушісі' — w немесе b. "
                   "Барлық тастардың қосындысы 50 болуы керек. Мысал: 5,5,5,5,5/5,5,5,5,5 0,0 w 1",
        "helpIntro": "Бестемше толық шешілген ойын. Әр ұядағы түсті сақина сол жүрістен кейін мінсіз "
                     "ойында нәтижені көрсетеді: <b>жасыл</b> — жүруші жеңеді, <b>сары</b> — тең, "
                     "<b>қызыл</b> — жүруші жеңіледі. Жүру үшін ұяны басыңыз.",
        "keys": [
            ["1–5", "өз бес ұяңның бірін ойнау (әр ойыншы өз сол қолынан санайды)"],
            ["0", "кездейсоқ оңтайлы жүріс"],
            ["9", "кездейсоқ жүріс (кез келген заңды жүріс)"],
            ["← / A", "алдыңғы позиция"],
            ["→ / D", "келесі позиция"],
            ["↑ / W", "бастапқы позицияға"],
            ["↓ / S", "соңғы жүріске"],
        ],
        "helpExtra": "Тізімдегі кез келген жүрісті басып, соған ораласыз — ол жерден басқа жүріс жасасаң, "
                     "қалған тарих қайта жазылады. Позиция қайталанса, ойын шексіз цикл — тең деп аяқталады. "
                     "Қазақ пернетақтасының қатары (әіңғ… және қ, ұ) сандар үшін де жұмыс істейді.",
        "authors": "Бестемше кестелік базасын, оның Толық Шешім дәлелін және осы Құдай алгоритмін "
                   "Ансар Зейнұлла мен Мұрат Манасов жасады.",
    },
    "RU": {
        "wins": "выигрывает!",
        "drawLoop": "Бесконечный цикл — ничья",
        "loopHint": "Позиция повторилась, поэтому игра — ничья.",
        "history": "Ходы",
        "newGame": "Новая игра",
        "setup": "Задать позицию",
        "help": "Как играть",
        "pgn": "Скачать PGN",
        "apply": "Начать",
        "close": "Закрыть",
        "fenHelp": "Формат позиции:  w1,w2,w3,w4,w5/b1,b2,b3,b4,b5 wКазан,bКазан сторона номерХода — "
                   "Белые — Бастаушы (ходит первым), Чёрные — Костаушы. 'сторона' — w или b. "
                   "Сумма всех камней должна быть 50. Пример: 5,5,5,5,5/5,5,5,5,5 0,0 w 1",
        "helpIntro": "Бестемше полностью решена. Цветное кольцо на лунке показывает исход этого хода "
                     "при идеальной игре дальше: <b>зелёное</b> — ходящий выигрывает, <b>жёлтое</b> — "
                     "ничья, <b>красное</b> — ходящий проигрывает. Нажмите на лунку, чтобы сделать ход.",
        "keys": [
            ["1–5", "сыграть одну из своих пяти лунок (каждый считает от своей левой руки)"],
            ["0", "случайный оптимальный ход"],
            ["9", "случайный ход (любой допустимый, хороший или плохой)"],
            ["← / A", "предыдущая позиция"],
            ["→ / D", "следующая позиция"],
            ["↑ / W", "к начальной позиции"],
            ["↓ / S", "к последнему ходу"],
        ],
        "helpExtra": "Нажмите на любой ход в списке, чтобы вернуться к нему — сыграв оттуда другой ход, "
                     "вы перепишете остаток партии. Если позиция повторяется, игра заканчивается ничьей "
                     "из-за бесконечного цикла. Ряд казахской клавиатуры (әіңғ… и қ, ұ) тоже работает для цифр.",
        "authors": "Табличную базу Бестемше, доказательство её Полного Решения и этот алгоритм Бога "
                   "создали Ансар Зейнулла и Мурат Манасов.",
    },
    "KG": {
        "wins": "жеңет!",
        "drawLoop": "Түгөнбөс цикл — тең",
        "loopHint": "Позиция кайталанды, ошондуктан оюн тең аяктады.",
        "history": "Жүрүштөр",
        "newGame": "Жаңы оюн",
        "setup": "Позиция коюу",
        "help": "Кантип ойноо",
        "pgn": "PGN жүктөө",
        "apply": "Баштоо",
        "close": "Жабуу",
        "fenHelp": "Позиция форматы:  w1,w2,w3,w4,w5/b1,b2,b3,b4,b5 wКазан,bКазан тарап жүрүшНө — "
                   "Ак — Бастаушы (биринчи жүрөт), Кара — Костаушу. 'тарап' — w же b. "
                   "Бардык таштардын суммасы 50 болушу керек. Мисал: 5,5,5,5,5/5,5,5,5,5 0,0 w 1",
        "helpIntro": "Бестемше толук чечилген оюн. Ар бир уядагы түстүү шакек ошол жүрүштөн кийин мыкты "
                     "оюндагы натыйжаны көрсөтөт: <b>жашыл</b> — жүрүүчү утат, <b>сары</b> — тең, "
                     "<b>кызыл</b> — жүрүүчү утулат. Жүрүш үчүн уяны басыңыз.",
        "keys": [
            ["1–5", "беш уяңдын бирин ойноо (ар ким өз сол колунан санайт)"],
            ["0", "кокус оптималдуу жүрүш"],
            ["9", "кокус жүрүш (каалаган мыйзамдуу жүрүш)"],
            ["← / A", "мурунку позиция"],
            ["→ / D", "кийинки позиция"],
            ["↑ / W", "баштапкы позицияга"],
            ["↓ / S", "акыркы жүрүшкө"],
        ],
        "helpExtra": "Тизмедеги каалаган жүрүштү басып, ага кайтасыз — ошол жерден башка жүрүш жасасаң, "
                     "калган тарых кайра жазылат. Позиция кайталанса, оюн түгөнбөс цикл — тең деп аяктайт. "
                     "Казак тергичинин катары (әіңғ… жана қ, ұ) сандар үчүн да иштейт.",
        "authors": "Бестемше таблицалык базасын, анын Толук Чечим далилин жана бул Кудай алгоритмин "
                   "Ансар Зейнулла жана Мурат Манасов түзгөн.",
    },
    "TR": {
        "wins": "kazanır!",
        "drawLoop": "Sonsuz döngü — beraberlik",
        "loopHint": "Konum tekrarlandı, bu yüzden oyun berabere bitti.",
        "history": "Hamleler",
        "newGame": "Yeni oyun",
        "setup": "Konum ayarla",
        "help": "Nasıl oynanır",
        "pgn": "PGN indir",
        "apply": "Başlat",
        "close": "Kapat",
        "fenHelp": "Konum biçimi:  w1,w2,w3,w4,w5/b1,b2,b3,b4,b5 wKazan,bKazan taraf hamleNo — "
                   "Beyaz Bastauşı'dır (ilk oynar), Siyah Kostauşı'dır. 'taraf' w veya b'dir. "
                   "Tüm taşların toplamı 50 olmalı. Örnek: 5,5,5,5,5/5,5,5,5,5 0,0 w 1",
        "helpIntro": "Bestemshe tamamen çözülmüştür. Her kuyudaki renkli halka, o hamleden sonra kusursuz "
                     "oyunla sonucu gösterir: <b>yeşil</b> — hamleyi yapan kazanır, <b>sarı</b> — beraberlik, "
                     "<b>kırmızı</b> — hamleyi yapan kaybeder. Oynamak için bir kuyuya tıklayın.",
        "keys": [
            ["1–5", "beş kuyunuzdan birini oynayın (her oyuncu kendi solundan sayar)"],
            ["0", "rastgele en iyi hamle"],
            ["9", "rastgele hamle (herhangi bir geçerli hamle)"],
            ["← / A", "önceki konum"],
            ["→ / D", "sonraki konum"],
            ["↑ / W", "başlangıç konumuna"],
            ["↓ / S", "son hamleye"],
        ],
        "helpExtra": "Listedeki herhangi bir hamleye tıklayarak oraya dönün — oradan farklı bir hamle "
                     "oynarsanız devamı yeniden yazılır. Bir konum tekrarlanırsa oyun sonsuz döngü "
                     "beraberliğiyle biter. Kazak klavye sırası (әіңғ… ve қ, ұ) rakamlar için de çalışır.",
        "authors": "Bestemshe Tablo Tabanı, Güçlü Çözüm kanıtı ve bu Tanrı algoritması "
                   "Ansar Zeinulla & Murat Manassov tarafından oluşturuldu.",
    },
}
