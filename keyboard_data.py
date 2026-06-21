"""Static data for the virtual keyboard: themes, layouts and word lists.

Kept separate from the UI so layouts and palettes can be edited (or tested)
without touching the Tk code.
"""

THEMES = {
    "Light": {
        "bg": "#ffffff",
        "muted": "#777777",
        "status": "#999999",
        "chrome_bg": "#eeeeee",
        "chrome_fg": "#555555",
        "chrome_active": "#e0e0e0",
        "key_bg": "#f2f2f2",
        "key_fg": "#333333",
        "key_border": "#d2d2d2",
        "key_light": "#f7f7f7",
        "key_active": "#e6e6e6",
        "key_pressed": "#dadada",
        "accent": "#d7eaff",
        "accent_fg": "#111111",
        "card": "#eef1f5",
        "chip": "#eef2f7",
        "chip_hover": "#d7eaff",
        "chip_fg": "#333333",
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
    "ShiftLeft": "⇧",
    "ShiftRight": "⇧",
    "Home": "Home",
    "End": "End",
    "Symbols": "@#&",
    "AI": "✨ AI",
    "Enter": "Enter",
    "Tab": "⇥",
    "Left": "←",
    "Up": "↑",
    "Down": "↓",
    "Right": "→",
}
