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
    {"code": "CS", "flag": "🇨🇿", "name": "Čeština"},
    {"code": "ES", "flag": "🇨🇴", "name": "Español"},
    {"code": "UZ", "flag": "🇺🇿", "name": "O‘zbekcha"},
]

# The two roles. The first player always moves first ("the one who starts"),
# the second follows. Their display names are translated per language via the
# "nameFirst" / "nameSecond" keys below — no White/Black wording anywhere.

TRANSLATIONS = {
    "EN": {
        "nameFirst": "Beginner",
        "nameSecond": "Follower",
        "wins": "wins!",
        "drawLoop": "Infinite loop — draw",
        "loopHint": "The exact same board position repeated, so the game is a draw.",
        "history": "Moves",
        "newGame": "New Game",
        "setup": "Set Position",
        "help": "How to Play",
        "pgn": "Download PGN",
        "apply": "Start",
        "close": "Close",
        "fenHelp": "Set up any custom board using FEN format. Read from left to right:<br><br>"
                   "<b>1. Board:</b> Beginner's 5 pits, a slash (<b>/</b>), then Follower's 5 pits.<br>"
                   "<b>2. Kazans:</b> Beginner's kazan, then Follower's kazan.<br>"
                   "<b>3. Turn:</b> <b>w</b> for Beginner, <b>b</b> for Follower.<br>"
                   "<b>4. Move Number:</b> Current move count.<br><br>"
                   "<i>Note: All kumalaks must add up exactly to 50.</i><br><br>"
                   "<b>Example (Starting Position):</b><br>"
                   "<code>5,5,5,5,5/5,5,5,5,5 0,0 w 1</code>",
        "helpIntro": "Bestemshe has been completely solved by computers. The glowing ring around each pit reveals "
                     "the guaranteed outcome of that move, assuming perfect play from both sides:<br><br>"
                     "🟢 <b>Green:</b> The corresponding player will win.<br>"
                     "🟡 <b>Yellow:</b> The game will be a draw via infinite loop.<br>"
                     "🔴 <b>Red:</b> The corresponding player will lose.<br><br>"
                     "Click on any of your pits to make a move.",
        "keys": [
            ["1–5", "Play pits 1 through 5"],
            ["0", "Play a random optimal move"],
            ["9", "Play a totally random move"],
            ["← / A", "Go back one move"],
            ["→ / D", "Go forward one move"],
            ["↑ / W", "Return to the starting position"],
            ["↓ / S", "Jump to the latest move"],
        ],
        "helpExtra": "Click any move in the history panel to jump back to that exact position. "
                     "If you play a different move from there, a new timeline is created and the old moves are overwritten. "
                     "The game ends in a draw if the exact same board position repeats.",
        "authors": "Bestemshe Table Base, its Strong Solution proof, and this God's Algorithm were "
                   "created by Ansar Zeinulla & Murat Manassov.",
    },
    "KZ": {
        "nameFirst": "Бастаушы",
        "nameSecond": "Қостаушы",
        "wins": "жеңеді!",
        "drawLoop": "Шексіз цикл — тең ойын",
        "loopHint": "Тақтадағы позиция қайталанды, сондықтан ойын тең аяқталды.",
        "history": "Жүрістер",
        "newGame": "Жаңа ойын",
        "setup": "Позиция қою",
        "help": "Қалай ойнайды?",
        "pgn": "PGN жүктеу",
        "apply": "Бастау",
        "close": "Жабу",
        "fenHelp": "FEN форматын пайдаланып кез келген позицияны қойыңыз. Солдан оңға қарай оқылады:<br><br>"
                   "<b>1. Тақта:</b> Бастаушының 5 ұясы, қиғаш сызық (<b>/</b>), сосын Қостаушының 5 ұясы.<br>"
                   "<b>2. Қазандар:</b> Бастаушының қазаны, сосын Қостаушының қазаны.<br>"
                   "<b>3. Кезек:</b> <b>w</b> — Бастаушы, <b>b</b> — Қостаушы.<br>"
                   "<b>4. Жүріс нөмірі:</b> Ағымдағы жүріс саны.<br><br>"
                   "<i>Ескертпе: Құмалақтардың жалпы саны әрқашан 50 болуы тиіс.</i><br><br>"
                   "<b>Мысал (Бастапқы позиция):</b><br>"
                   "<code>5,5,5,5,5/5,5,5,5,5 0,0 w 1</code>",
        "helpIntro": "Бестемше ойыны компьютермен толық шешілген. Әр ұяның айналасындағы жарқыраған сақина екі жақтың мінсіз "
                     "ойыны кезіндегі сол жүрістің кепілдендірілген нәтижесін көрсетеді:<br><br>"
                     "🟢 <b>Жасыл:</b> Жүріс жасайтын ойыншы жеңеді.<br>"
                     "🟡 <b>Сары:</b> Ойын шексіз циклге байланысты тең аяқталады.<br>"
                     "🔴 <b>Қызыл:</b> Жүріс жасайтын ойыншы жеңіледі.<br><br>"
                     "Жүріс жасау үшін кез келген ұяңызды басыңыз.",
        "keys": [
            ["1–5", "1-ден 5-ке дейінгі ұялардан ойнау"],
            ["0", "Кездейсоқ оңтайлы жүріс жасау"],
            ["9", "Толықтай кездейсоқ жүріс жасау"],
            ["← / A", "Бір жүріс артқа"],
            ["→ / D", "Бір жүріс алға"],
            ["↑ / W", "Бастапқы позицияға қайту"],
            ["↓ / S", "Соңғы жүріске өту"],
        ],
        "helpExtra": "Тарих тақтасындағы кез келген жүрісті басып, дәл сол позицияға орала аласыз. "
                     "Егер ол жерден басқа жүріс жасасаңыз, жаңа тармақ құрылып, ескі жүрістер қайта жазылады. "
                     "Тақтадағы позиция қайталанса, ойын шексіз циклге түсіп, тең аяқталады.",
        "authors": "Бестемше кестелік базасын, оның Толық Шешім дәлелін және осы Құдай алгоритмін "
                   "Аңсар Зейнулла мен Мұрат Манасов жасады.",
    },
    "RU": {
        "nameFirst": "Начинающий",
        "nameSecond": "Продолжающий",
        "wins": "выигрывает!",
        "drawLoop": "Бесконечный цикл — ничья",
        "loopHint": "Позиция на доске повторилась, поэтому игра завершилась вничью.",
        "history": "Ходы",
        "newGame": "Новая игра",
        "setup": "Задать позицию",
        "help": "Как играть?",
        "pgn": "Скачать PGN",
        "apply": "Начать",
        "close": "Закрыть",
        "fenHelp": "Настройте любую позицию, используя формат FEN. Читается слева направо:<br><br>"
                   "<b>1. Доска:</b> 5 лунок Начинающего, затем слэш (<b>/</b>), затем 5 лунок Продолжающего.<br>"
                   "<b>2. Казаны:</b> казан Начинающего, затем казан Продолжающего.<br>"
                   "<b>3. Очередь хода:</b> <b>w</b> — Начинающий, <b>b</b> — Продолжающий.<br>"
                   "<b>4. Номер хода:</b> Текущий номер хода.<br><br>"
                   "<i>Примечание: Общее количество кумалаков всегда должно быть равно 50.</i><br><br>"
                   "<b>Пример (Начальная позиция):</b><br>"
                   "<code>5,5,5,5,5/5,5,5,5,5 0,0 w 1</code>",
        "helpIntro": "Игра Бестемше полностью решена компьютерами. Светящееся кольцо вокруг каждой лунки "
                     "показывает гарантированный исход этого хода при идеальной игре обеих сторон:<br><br>"
                     "🟢 <b>Зеленый:</b> Ходящий игрок выиграет.<br>"
                     "🟡 <b>Желтый:</b> Будет ничья благодаря бесконечному циклу.<br>"
                     "🔴 <b>Красный:</b> Ходящий игрок проиграет.<br><br>"
                     "Нажмите на любую из ваших лунок, чтобы сделать ход.",
        "keys": [
            ["1–5", "Сыграть лунки с 1 по 5"],
            ["0", "Сделать случайный оптимальный ход"],
            ["9", "Сделать абсолютно случайный ход"],
            ["← / A", "На один ход назад"],
            ["→ / D", "На один ход вперед"],
            ["↑ / W", "Вернуться к начальной позиции"],
            ["↓ / S", "Перейти к последнему ходу"],
        ],
        "helpExtra": "Нажмите на любой ход в панели истории, чтобы вернуться точно к этой позиции. "
                     "Если вы сделаете оттуда другой ход, создастся новая ветка, а старые ходы будут удалены. "
                     "Если позиция на доске полностью повторяется, игра заканчивается вничью из-за бесконечного цикла.",
        "authors": "Табличную базу Бестемше, доказательство её Полного Решения и этот Алгоритм Бога "
                   "создали Ансар Зейнулла и Мурат Манасов.",
    },
    "KG": {
        "nameFirst": "Баштоочу",
        "nameSecond": "Коштоочу",
        "wins": "жеңет!",
        "drawLoop": "Түгөнбөс цикл — тең чыгуу",
        "loopHint": "Тактадагы позиция кайталанды, ошондуктан оюн тең чыгуу менен аяктады.",
        "history": "Жүрүштөр",
        "newGame": "Жаңы оюн",
        "setup": "Позиция коюу",
        "help": "Кантип ойнойт?",
        "pgn": "PGN жүктөө",
        "apply": "Баштоо",
        "close": "Жабуу",
        "fenHelp": "FEN форматын колдонуп каалаган позицияны коюңуз. Солдон оңго карай окулат:<br><br>"
                   "<b>1. Такта:</b> Баштоочунун 5 уясы, кыйгач сызык (<b>/</b>), андан кийин Коштоочунун 5 уясы.<br>"
                   "<b>2. Казандар:</b> Баштоочунун казаны, андан кийин Коштоочунун казаны.<br>"
                   "<b>3. Кезек:</b> <b>w</b> — Баштоочу, <b>b</b> — Коштоочу.<br>"
                   "<b>4. Жүрүш номери:</b> Учурдагы жүрүш саны.<br><br>"
                   "<i>Эскертүү: Кумалактардын жалпы саны ар дайым 50 болушу керек.</i><br><br>"
                   "<b>Мисал (Баштапкы позиция):</b><br>"
                   "<code>5,5,5,5,5/5,5,5,5,5 0,0 w 1</code>",
        "helpIntro": "Бестемше оюну компьютерлер тарабынан толук чечилген. Ар бир уянын айланасындагы жарык шакек "
                     "эки тараптын мыкты оюнундагы ошол жүрүштүн кепилденген натыйжасын көрсөтөт:<br><br>"
                     "🟢 <b>Жашыл:</b> Жүрүш жасоочу оюнчу утат.<br>"
                     "🟡 <b>Сары:</b> Оюн түгөнбөс циклге байланыштуу тең чыгуу менен аяктайт.<br>"
                     "🔴 <b>Кызыл:</b> Жүрүш жасоочу утулат.<br><br>"
                     "Жүрүш жасоо үчүн каалаган уяңызды басыңыз.",
        "keys": [
            ["1–5", "1ден 5ке чейинки уяларды ойноо"],
            ["0", "Кокустан оптималдуу жүрүш жасоо"],
            ["9", "Толугу менен кокус жүрүш жасоо"],
            ["← / A", "Бир жүрүш артка"],
            ["→ / D", "Бир жүрүш алдыга"],
            ["↑ / W", "Баштапкы позицияга кайтуу"],
            ["↓ / S", "Акыркы жүрүшкө өтүү"],
        ],
        "helpExtra": "Тарых тактасындагы каалаган жүрүштү басып, так ошол позицияга кайта аласыз. "
                     "Эгер ал жерден башка жүрүш жасасаңыз, жаңы бутак түзүлүп, эски жүрүштөр кайра жазылат. "
                     "Тактадагы позиция кайталанса, оюн түгөнбөс циклге түшүп, тең чыгуу менен аяктайт.",
        "authors": "Бестемше таблицалык базасын, анын Толук Чечим далилин жана бул Кудай алгоритмин "
                   "Ансар Зейнулла жана Мурат Манасов түзгөн.",
    },
    "TR": {
        "nameFirst": "Başlayan",
        "nameSecond": "İzleyen",
        "wins": "kazandı!",
        "drawLoop": "Sonsuz döngü — Beraberlik",
        "loopHint": "Tahtadaki konum tamamen tekrarlandığı için oyun berabere bitti.",
        "history": "Hamleler",
        "newGame": "Yeni Oyun",
        "setup": "Konum Ayarla",
        "help": "Nasıl Oynanır?",
        "pgn": "PGN İndir",
        "apply": "Başlat",
        "close": "Kapat",
        "fenHelp": "FEN formatını kullanarak özel bir konum ayarlayın. Soldan sağa doğru okunur:<br><br>"
                   "<b>1. Tahta:</b> Başlayan'ın 5 kuyusu, eğik çizgi (<b>/</b>), sonra İzleyen'in 5 kuyusu.<br>"
                   "<b>2. Kazanlar:</b> Başlayan'ın kazanı, sonra İzleyen'in kazanı.<br>"
                   "<b>3. Sıra:</b> <b>w</b> — Başlayan, <b>b</b> — İzleyen.<br>"
                   "<b>4. Hamle Numarası:</b> Mevcut hamle sayısı.<br><br>"
                   "<i>Not: Toplam kumalak sayısı her zaman tam olarak 50 olmalıdır.</i><br><br>"
                   "<b>Örnek (Başlangıç Konumu):</b><br>"
                   "<code>5,5,5,5,5/5,5,5,5,5 0,0 w 1</code>",
        "helpIntro": "Bestemshe oyunu bilgisayarlar tarafından tamamen çözülmüştür. Her kuyunun etrafındaki parlayan halka, "
                     "her iki tarafın da kusursuz oynadığı varsayılarak o hamlenin kesin sonucunu gösterir:<br><br>"
                     "🟢 <b>Yeşil:</b> Hamleyi yapan oyuncu kazanır.<br>"
                     "🟡 <b>Sarı:</b> Oyun sonsuz döngü nedeniyle berabere biter.<br>"
                     "🔴 <b>Kırmızı:</b> Hamleyi yapan oyuncu kaybeder.<br><br>"
                     "Hamle yapmak için kendi kuyularınızdan birine tıklayın.",
        "keys": [
            ["1–5", "1'den 5'e kadar olan kuyulardan birini oynayın"],
            ["0", "Rastgele en iyi (optimum) hamleyi yapın"],
            ["9", "Tamamen rastgele bir hamle yapın"],
            ["← / A", "Bir hamle geri git"],
            ["→ / D", "Bir hamle ileri git"],
            ["↑ / W", "Başlangıç konumuna dön"],
            ["↓ / S", "Son hamleye atla"],
        ],
        "helpExtra": "Geçmiş panelindeki herhangi bir hamleye tıklayarak tam o konuma geri dönebilirsiniz. "
                     "Oradan farklı bir hamle yaparsanız yeni bir varyant (dal) oluşur ve sonraki eski hamleler silinir. "
                     "Tahtadaki bir konum tam olarak tekrarlanırsa, oyun sonsuz döngü nedeniyle berabere biter.",
        "authors": "Bestemshe Tablo Tabanı, Güçlü Çözüm kanıtı ve bu Tanrı Algoritması "
                   "Ansar Zeinulla ve Murat Manassov tarafından oluşturulmuştur.",
    },
    "CS": {
        "nameFirst": "Začínající",
        "nameSecond": "Následující",
        "wins": "vyhrává!",
        "drawLoop": "Nekonečná smyčka — remíza",
        "loopHint": "Pozice na desce se zopakovala, takže hra končí remízou.",
        "history": "Tahy",
        "newGame": "Nová hra",
        "setup": "Nastavit pozici",
        "help": "Jak hrát?",
        "pgn": "Stáhnout PGN",
        "apply": "Začít",
        "close": "Zavřít",
        "fenHelp": "Nastavte si libovolnou pozici pomocí formátu FEN. Čte se zleva doprava:<br><br>"
                   "<b>1. Deska:</b> 5 jamek Začínajícího, lomítko (<b>/</b>), poté 5 jamek Následujícího.<br>"
                   "<b>2. Kazany:</b> kazan Začínajícího, poté kazan Následujícího.<br>"
                   "<b>3. Tah:</b> <b>w</b> — Začínající, <b>b</b> — Následující.<br>"
                   "<b>4. Číslo tahu:</b> Aktuální počet tahů.<br><br>"
                   "<i>Poznámka: Celkový počet kumalaků musí být přesně 50.</i><br><br>"
                   "<b>Příklad (Výchozí pozice):</b><br>"
                   "<code>5,5,5,5,5/5,5,5,5,5 0,0 w 1</code>",
        "helpIntro": "Hra Bestemshe byla kompletně vyřešena počítači. Zářící kruh kolem každé jamky ukazuje zaručený "
                     "výsledek daného tahu za předpokladu dokonalé hry obou stran:<br><br>"
                     "🟢 <b>Zelená:</b> Hráč na tahu vyhraje.<br>"
                     "🟡 <b>Žlutá:</b> Hra skončí remízou kvůli nekonečné smyčce.<br>"
                     "🔴 <b>Červená:</b> Hráč na tahu prohraje.<br><br>"
                     "Klikněte na jakoukoli ze svých jamek a zahrajte tah.",
        "keys": [
            ["1–5", "Zahrát jamky 1 až 5"],
            ["0", "Zahrát náhodný optimální tah"],
            ["9", "Zahrát zcela náhodný tah"],
            ["← / A", "O jeden tah zpět"],
            ["→ / D", "O jeden tah vpřed"],
            ["↑ / W", "Návrat do výchozí pozice"],
            ["↓ / S", "Skočit na poslední tah"],
        ],
        "helpExtra": "Kliknutím na jakýkoli tah v panelu historie přeskočíte přesně do dané pozice. "
                     "Pokud odtud zahrajete jiný tah, vytvoří se nová časová osa a staré tahy budou smazány. "
                     "Pokud se pozice na desce přesně zopakuje, hra končí remízou kvůli nekonečné smyčce.",
        "authors": "Databázi koncovek (Table Base) pro hru Bestemshe, její matematický důkaz a tento Boží algoritmus "
                   "vytvořili Ansar Zeinulla a Murat Manassov.",
    },
    "ES": {
        "nameFirst": "Iniciador",
        "nameSecond": "Seguidor",
        "wins": "¡gana!",
        "drawLoop": "Bucle infinito — Empate",
        "loopHint": "La posición en el tablero se repitió por completo, así que el juego termina en empate.",
        "history": "Jugadas",
        "newGame": "Juego Nuevo",
        "setup": "Configurar Posición",
        "help": "¿Cómo se juega?",
        "pgn": "Descargar PGN",
        "apply": "Empezar",
        "close": "Cerrar",
        "fenHelp": "Configura cualquier posición personalizada usando el formato FEN. Se lee de izquierda a derecha:<br><br>"
                   "<b>1. Tablero:</b> 5 hoyos del Iniciador, una barra (<b>/</b>), luego 5 hoyos del Seguidor.<br>"
                   "<b>2. Kazanes:</b> kazán del Iniciador, luego kazán del Seguidor.<br>"
                   "<b>3. Turno:</b> <b>w</b> — Iniciador, <b>b</b> — Seguidor.<br>"
                   "<b>4. Número de jugada:</b> Conteo actual de jugadas.<br><br>"
                   "<i>Nota: El total de kumalaks (fichas) siempre debe sumar exactamente 50.</i><br><br>"
                   "<b>Ejemplo (Posición inicial):</b><br>"
                   "<code>5,5,5,5,5/5,5,5,5,5 0,0 w 1</code>",
        "helpIntro": "El Bestemshe ha sido completamente resuelto por computadoras. El anillo brillante alrededor de cada hoyo "
                     "muestra el resultado garantizado de esa jugada, asumiendo que ambos juegan a la perfección:<br><br>"
                     "🟢 <b>Verde:</b> El jugador que mueve ganará.<br>"
                     "🟡 <b>Amarillo:</b> El juego será un empate por bucle infinito.<br>"
                     "🔴 <b>Rojo:</b> El jugador que mueve perderá.<br><br>"
                     "Haz clic en cualquiera de tus hoyos para hacer una jugada.",
        "keys": [
            ["1–5", "Jugar los hoyos del 1 al 5"],
            ["0", "Hacer una jugada óptima al azar"],
            ["9", "Hacer una jugada totalmente al azar"],
            ["← / A", "Retroceder una jugada"],
            ["→ / D", "Avanzar una jugada"],
            ["↑ / W", "Volver a la posición inicial"],
            ["↓ / S", "Saltar a la última jugada"],
        ],
        "helpExtra": "Haz clic en cualquier jugada en el panel de historial para volver a esa posición exacta. "
                     "Si haces una jugada diferente desde ahí, se crea una nueva variante y las jugadas anteriores se borran. "
                     "Si la misma posición en el tablero se repite, el juego termina en empate por bucle infinito.",
        "authors": "La base de datos de tablas (Table Base) de Bestemshe, su demostración de Solución Fuerte y este Algoritmo "
                   "de Dios fueron creados por Ansar Zeinulla y Murat Manassov.",
    },
    "UZ": {
        "nameFirst": "Boshlovchi",
        "nameSecond": "Ergashuvchi",
        "wins": "yutadi!",
        "drawLoop": "Cheksiz sikl — durang",
        "loopHint": "Taxtadagi holat to'liq takrorlandi, shuning uchun o'yin durang bilan tugadi.",
        "history": "Yurishlar",
        "newGame": "Yangi o‘yin",
        "setup": "Holatni o‘rnatish",
        "help": "Qanday o‘ynaladi?",
        "pgn": "PGN yuklab olish",
        "apply": "Boshlash",
        "close": "Yopish",
        "fenHelp": "FEN formati yordamida istalgan holatni o'rnating. Chapdan o'ngga o'qiladi:<br><br>"
                   "<b>1. Taxta:</b> Boshlovchining 5 ta uyasi, qiya chiziq (<b>/</b>), so'ngra Ergashuvchining 5 ta uyasi.<br>"
                   "<b>2. Qozonlar:</b> Boshlovchining qozoni, keyin Ergashuvchining qozoni.<br>"
                   "<b>3. Navbat:</b> <b>w</b> — Boshlovchi, <b>b</b> — Ergashuvchi.<br>"
                   "<b>4. Yurish raqami:</b> Joriy yurish soni.<br><br>"
                   "<i>Eslatma: Qumaloqlar (toshlar) ning umumiy soni doim 50 ta bo'lishi kerak.</i><br><br>"
                   "<b>Misol (Boshlang'ich holat):</b><br>"
                   "<code>5,5,5,5,5/5,5,5,5,5 0,0 w 1</code>",
        "helpIntro": "Bestemshe o'yini kompyuterlar tomonidan to'liq yechilgan. Har bir uya atrofidagi porlayotgan halqa "
                     "ikkala tomonning mukammal o'yinini hisobga olgan holda, shu yurishning kafolatlangan natijasini ko'rsatadi:<br><br>"
                     "🟢 <b>Yashil:</b> Yurish qilayotgan o'yinchi yutadi.<br>"
                     "🟡 <b>Sariq:</b> O'yin cheksiz sikl tufayli durang bilan tugaydi.<br>"
                     "🔴 <b>Qizil:</b> Yurish qilayotgan o'yinchi yutqazadi.<br><br>"
                     "Yurish qilish uchun o'z uyalaringizdan birini bosing.",
        "keys": [
            ["1–5", "1 dan 5 gacha bo'lgan uyalarni o'ynash"],
            ["0", "Tasodifiy eng yaxshi yurishni qilish"],
            ["9", "To'liq tasodifiy yurish qilish"],
            ["← / A", "Bir yurish orqaga"],
            ["→ / D", "Bir yurish oldinga"],
            ["↑ / W", "Boshlang'ich holatga qaytish"],
            ["↓ / S", "Oxirgi yurishga o'tish"],
        ],
        "helpExtra": "Tarix panelidagi istalgan yurishni bosib, aynan shu holatga qaytishingiz mumkin. "
                     "Agar u yerdan boshqa yurish qilsangiz, yangi tarmoq yaratiladi va eski yurishlar o'chiriladi. "
                     "Taxtadagi holat to'liq takrorlansa, o'yin cheksiz sikl sababli durang bilan tugaydi.",
        "authors": "Bestemshe jadval bazasi, uning To'liq Yechim isboti va ushbu Xudo Algoritmi "
                   "Ansar Zeinulla va Murat Manassov tomonidan yaratilgan.",
    },
}