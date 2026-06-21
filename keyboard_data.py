"""Static data for the virtual keyboard: themes, layouts and word lists.

Kept separate from the UI so layouts and palettes can be edited (or tested)
without touching the Tk code.
"""

THEMES = {
    "Light": {
        "bg": "#e4e8ec",
        "muted": "#4f5964",
        "status": "#66717d",
        "chrome_bg": "#d3d9df",
        "chrome_fg": "#29323b",
        "chrome_active": "#c4cbd3",
        "key_bg": "#f4f6f8",
        "key_fg": "#1f2933",
        "key_border": "#aeb8c2",
        "key_light": "#ffffff",
        "key_active": "#dce5ee",
        "key_pressed": "#cbd7e2",
        "accent": "#b9d7f2",
        "accent_fg": "#142638",
        "card": "#d8dde3",
        "chip": "#f0f3f6",
        "chip_hover": "#cfe0f0",
        "chip_fg": "#25313d",
    },
    "Dark": {
        "bg": "#2b2b2b",
        "muted": "#bbbbbb",
        "status": "#888888",
        "chrome_bg": "#3c3f41",
        "chrome_fg": "#e8e8e8",
        "chrome_active": "#4a4d4f",
        "key_bg": "#3c3f41",
        "key_fg": "#e8e8e8",
        "key_border": "#555555",
        "key_light": "#454749",
        "key_active": "#4a4d4f",
        "key_pressed": "#565a5c",
        "accent": "#37506e",
        "accent_fg": "#ffffff",
        "card": "#34383c",
        "chip": "#3f4448",
        "chip_hover": "#4c5662",
        "chip_fg": "#e8e8e8",
    },
}

# A separate high-contrast palette, toggled from Accessibility settings. Kept
# out of THEMES so it doesn't appear as a normal selectable theme.
HIGH_CONTRAST = {
    "bg": "#000000",
    "muted": "#ffffff",
    "status": "#ffff00",
    "chrome_bg": "#000000",
    "chrome_fg": "#ffffff",
    "chrome_active": "#333333",
    "key_bg": "#000000",
    "key_fg": "#ffffff",
    "key_border": "#ffffff",
    "key_light": "#000000",
    "key_active": "#444444",
    "key_pressed": "#666666",
    "accent": "#ffff00",
    "accent_fg": "#000000",
    "card": "#000000",
    "chip": "#1a1a1a",
    "chip_hover": "#444444",
    "chip_fg": "#ffff00",
}

# Word-completion suggestions per language.
LANGUAGES = {
    "Norsk": [
        "og", "jeg", "det", "du", "er", "ikke", "til", "med", "for", "som",
        "hei", "takk", "ja", "nei", "kan", "skrive", "norsk", "keyboard",
        "virtual", "klikke", "ord", "hvor", "når", "hva", "bra", "veldig",
    ],
    "English": [
        "the", "and", "you", "that", "was", "for", "are", "with", "have",
        "this", "from", "they", "what", "hello", "thanks", "yes", "no",
        "can", "write", "keyboard", "virtual", "click", "word", "where",
        "when", "good",
    ],
    "Español": [
        "el", "la", "de", "que", "y", "en", "los", "se", "las", "por",
        "un", "para", "con", "no", "una", "su", "hola", "gracias", "sí",
        "escribir", "teclado", "virtual", "clic", "palabra", "dónde", "bueno",
    ],
    "Français": [
        "le", "la", "de", "et", "les", "des", "un", "une", "à", "en",
        "que", "pour", "bonjour", "merci", "oui", "non", "écrire", "clavier",
        "virtuel", "cliquer", "mot", "où", "quand", "bon", "très",
    ],
    "Deutsch": [
        "der", "die", "und", "den", "von", "zu", "das", "mit", "ist", "für",
        "hallo", "danke", "ja", "nein", "schreiben", "tastatur", "virtuell",
        "klicken", "wort", "wo", "wann", "gut", "sehr", "auf", "nicht",
    ],
    "Italiano": [
        "il", "la", "di", "che", "e", "la", "un", "una", "per", "con",
        "ciao", "grazie", "sì", "no", "scrivere", "tastiera", "virtuale",
        "cliccare", "parola", "dove", "quando", "buono", "molto", "non", "sono",
    ],
}

# Both languages share ONE layout. Only three keys differ: in Norsk they are the
# Nordic letters å / ø / æ; in English those same positions become symbols.
# Special key names ("Backspace", "Enter", "Shift*", "Tab", "Caps", "Symbols",
# "AI", "Space", arrows) are handled by the app, not typed literally.
def _rows(top_right, home_1, home_2):
    return [
        ["|", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "+", "\\", "Backspace"],
        ["Tab", "q", "w", "e", "r", "t", "y", "u", "i", "o", "p", top_right, "Enter"],
        ["Caps", "a", "s", "d", "f", "g", "h", "j", "k", "l", home_1, home_2, "'"],
        ["ShiftLeft", "<", "z", "x", "c", "v", "b", "n", "m", ",", ".", "-", "ShiftRight"],
        ["Symbols", "Space", "Left", "Up", "Down", "Right", "AI"],
    ]


# Shift mapping shared by both languages (letters just upper-case, so they need
# no entry here).
_BASE_SHIFT = {
    "|": "§", "1": "!", "2": '"', "3": "#", "4": "¤", "5": "%",
    "6": "&", "7": "/", "8": "(", "9": ")", "0": "=", "+": "?",
    "\\": "`", "'": "*", "<": ">", ",": ";", ".": ":",
    "-": "_",
}

LAYOUTS = {
    "Norsk": {
        "rows": _rows("å", "ø", "æ"),
        "shift": dict(_BASE_SHIFT),
    },
    "English": {
        "rows": _rows("[", "]", ";"),
        "shift": {**_BASE_SHIFT, "[": "{", "]": "}", ";": ":"},
    },
    "Español": {
        # Spanish uses the same layout as English plus ñ; we put ñ where
        # Norsk has æ, and the other two slots stay as symbols.
        "rows": _rows("[", "]", "ñ"),
        "shift": {**_BASE_SHIFT, "[": "{", "]": "}", "ñ": "Ñ"},
    },
    "Français": {
        # French: à and è are common; we place them where Norsk has å/ø.
        "rows": _rows("à", "è", ";"),
        "shift": {**_BASE_SHIFT, "à": "À", "è": "È", ";": ":"},
    },
    "Deutsch": {
        # German: ä, ö, ü are the umlauts; we place ä/ö where Norsk has å/ø.
        "rows": _rows("ä", "ö", ";"),
        "shift": {**_BASE_SHIFT, "ä": "Ä", "ö": "Ö", ";": ":"},
    },
    "Italiano": {
        # Italian uses the same layout as English (no special letters needed
        # beyond accented vowels which can be typed via Symbols/Alt).
        "rows": _rows("[", "]", ";"),
        "shift": {**_BASE_SHIFT, "[": "{", "]": "}", ";": ":"},
    },
}

# Extra symbols shown in the suggestion strip via the Symbols toggle.
SYMBOL_ROW = [
    "!", "?", "@", "#", "$", "%", "&", "*", "(", ")",
    "=", "+", "/", "\\", "_", ":", ";", "^", "~", '"',
]

# Display labels for non-character keys.
SPECIAL_LABELS = {
    "Backspace": "⌫",
    "Del": "⌦",
    "Caps": "Caps",
    "ShiftLeft": "Shift",
    "ShiftRight": "Shift",
    "Home": "Home",
    "End": "End",
    "Symbols": "@#&",
    "AI": "✨ AI",
    "Enter": "Enter",
    "Tab": "Tab",
    "Left": "←",
    "Up": "↑",
    "Down": "↓",
    "Right": "→",
}
