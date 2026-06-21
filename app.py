import sys


if sys.platform != "win32":
    raise SystemExit("This virtual keyboard currently supports Windows only.")

import json
import os
import tkinter as tk
import winsound
from tkinter import font as tkfont
from tkinter import ttk

import winapi as win
from keyboard_data import (
    HIGH_CONTRAST,
    LANGUAGES,
    LAYOUTS,
    SPECIAL_LABELS,
    SYMBOL_ROW,
    THEMES,
)
from text_logic import completion, rank_words


SCALES = {"Small": 0.85, "Normal": 1.0, "Large": 1.2, "Extra Large": 1.45}
# (initial delay, repeat interval) in milliseconds for hold-to-repeat keys.
REPEAT_SPEEDS = {"Slow": (500, 110), "Normal": (400, 60), "Fast": (320, 40)}

DEFAULTS = {
    "theme": "Light",
    "high_contrast": False,
    "language": "Norsk",
    "scale": "Normal",
    "always_on_top": True,
    "remember_position": True,
    "suggestions_enabled": True,
    "suggestion_count": 6,
    "auto_space": True,
    "learn_words": True,
    "repeat_speed": "Normal",
    "key_animation": True,
    "sound": False,
    "show_ai": True,
}

BASE_WIDTH, BASE_HEIGHT = 640, 320
BASE_MIN_WIDTH, BASE_MIN_HEIGHT = 520, 245


class VirtualKeyboard(tk.Tk):
    # Keys that fire repeatedly while held down.
    REPEATABLE = {"Backspace", "Del", "Left", "Right", "Up", "Down"}

    def __init__(self):
        super().__init__()
        self.title("Virtual Keyboard")
        self.attributes("-topmost", True)
        # Remove the native OS title bar so the keyboard has a single, clearly
        # styled Exit button instead of the OS close button plus a custom one.
        self.overrideredirect(True)
        self._drag_offset = (0, 0)

        s = self._load_settings()
        self.theme_name = s["theme"] if s["theme"] in THEMES else "Light"
        self.high_contrast = bool(s["high_contrast"])
        self.language = s["language"] if s["language"] in LANGUAGES else "Norsk"
        self.scale_name = s["scale"] if s["scale"] in SCALES else "Normal"
        self.remember_position = bool(s["remember_position"])
        self.suggestions_enabled = bool(s["suggestions_enabled"])
        self.suggestion_count = s["suggestion_count"] if s["suggestion_count"] in (3, 6, 9) else 6
        self.auto_space = bool(s["auto_space"])
        self.learn_words = bool(s["learn_words"])
        self.repeat_speed = s["repeat_speed"] if s["repeat_speed"] in REPEAT_SPEEDS else "Normal"
        self.key_animation = bool(s["key_animation"])
        self.sound = bool(s["sound"])
        self.show_ai = bool(s["show_ai"])
        self.always_on_top = tk.BooleanVar(value=bool(s["always_on_top"]))
        self.word_freq = self._load_word_freq()

        self.shift_active = False
        self.caps_lock = False
        self.symbols_visible = False
        self.settings_visible = False
        self.current_word = ""
        self.status_text = tk.StringVar(value="Click where text should go, then use the keys")
        self.key_buttons = {}
        self.last_target_hwnd = None
        self._repeat_job = None
        self._option_groups = []
        self.common_words = LANGUAGES[self.language]
        self.layout_rows = LAYOUTS[self.language]["rows"]
        self.shift_map = LAYOUTS[self.language]["shift"]

        self.configure(bg=self.palette["bg"])
        self._apply_geometry(s)

        self.taskbar_anchor = None
        self._anchor_ready = False

        self._build_styles()
        self._build_ui()
        self._apply_theme()
        self._create_taskbar_anchor()
        self.after(200, self._make_no_activate)
        self.after(250, self._track_target_window)

    @property
    def palette(self):
        return HIGH_CONTRAST if self.high_contrast else THEMES[self.theme_name]

    def _scaled(self, value):
        return max(1, int(round(value * SCALES[self.scale_name])))

    # ------------------------------------------------------------------ settings
    def _settings_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

    def _load_settings(self):
        merged = dict(DEFAULTS)
        try:
            with open(self._settings_path(), encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                merged.update(data)
        except (OSError, ValueError):
            pass
        return merged

    def _apply_geometry(self, settings):
        width = int(BASE_WIDTH * SCALES[self.scale_name])
        height = int(BASE_HEIGHT * SCALES[self.scale_name])
        self.minsize(
            int(BASE_MIN_WIDTH * SCALES[self.scale_name]),
            int(BASE_MIN_HEIGHT * SCALES[self.scale_name]),
        )
        x, y = settings.get("x"), settings.get("y")
        if self.remember_position and isinstance(x, int) and isinstance(y, int):
            self.geometry(f"{width}x{height}+{x}+{y}")
        else:
            self.geometry(f"{width}x{height}")

    def _save_settings(self):
        data = {
            "theme": self.theme_name,
            "high_contrast": self.high_contrast,
            "language": self.language,
            "scale": self.scale_name,
            "always_on_top": bool(self.always_on_top.get()),
            "remember_position": self.remember_position,
            "suggestions_enabled": self.suggestions_enabled,
            "suggestion_count": self.suggestion_count,
            "auto_space": self.auto_space,
            "learn_words": self.learn_words,
            "repeat_speed": self.repeat_speed,
            "key_animation": self.key_animation,
            "sound": self.sound,
            "show_ai": self.show_ai,
            "x": self.winfo_x(),
            "y": self.winfo_y(),
        }
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
        except OSError:
            pass

    def _freq_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "learned_words.json")

    def _load_word_freq(self):
        try:
            with open(self._freq_path(), encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return {str(k): int(v) for k, v in data.items() if isinstance(v, int)}
        except (OSError, ValueError):
            pass
        return {}

    def _save_word_freq(self):
        try:
            with open(self._freq_path(), "w", encoding="utf-8") as handle:
                json.dump(self.word_freq, handle)
        except OSError:
            pass

    def _learn(self, word):
        if not self.learn_words:
            return
        word = word.strip().lower()
        if len(word) < 2 or not word.isalpha():
            return
        self.word_freq[word] = self.word_freq.get(word, 0) + 1
        self._save_word_freq()

    # --------------------------------------------------------------------- styles
    def _build_styles(self):
        self._style = ttk.Style(self)
        self._style.theme_use("clam")
        self._configure_styles()

    def _configure_styles(self):
        style = self._style
        palette = self.palette
        pad = (self._scaled(7), self._scaled(5))
        key_font = ("Segoe UI", self._scaled(10))
        word_font = ("Segoe UI", self._scaled(9))

        style.configure("Root.TFrame", background=palette["bg"])
        style.configure("Keyboard.TFrame", background=palette["bg"])
        style.configure("Key.TButton", font=key_font, padding=pad)
        style.configure("Wide.TButton", font=key_font, padding=pad)
        style.configure("Word.TButton", font=word_font, padding=(self._scaled(8), self._scaled(4)))
        style.configure(
            "Caps.TButton",
            font=("Segoe UI", self._scaled(10), "bold"),
            padding=pad,
            foreground=palette["accent_fg"],
            background=palette["accent"],
            bordercolor=palette["key_border"],
            lightcolor=palette["accent"],
            darkcolor=palette["key_border"],
            relief=tk.FLAT,
        )
        style.map(
            "Caps.TButton",
            background=[("active", palette["accent"]), ("pressed", palette["accent"])],
        )
        for button_style in ("Key.TButton", "Wide.TButton", "Word.TButton"):
            style.configure(
                button_style,
                foreground=palette["key_fg"],
                background=palette["key_bg"],
                bordercolor=palette["key_border"],
                lightcolor=palette["key_light"],
                darkcolor=palette["key_border"],
                relief=tk.FLAT,
            )
            style.map(
                button_style,
                background=[
                    ("active", palette["key_active"]),
                    ("pressed", palette["key_pressed"]),
                ],
            )

    def _apply_scale(self):
        self._configure_styles()
        width = int(BASE_WIDTH * SCALES[self.scale_name])
        height = int(BASE_HEIGHT * SCALES[self.scale_name])
        self.minsize(
            int(BASE_MIN_WIDTH * SCALES[self.scale_name]),
            int(BASE_MIN_HEIGHT * SCALES[self.scale_name]),
        )
        self.geometry(f"{width}x{height}+{self.winfo_x()}+{self.winfo_y()}")
        self.suggestions.config(height=self._scaled(42))
        self._refresh_suggestions()

    # ------------------------------------------------------------------------- UI
    def _build_ui(self):
        root = ttk.Frame(self, style="Root.TFrame", padding=8)
        root.pack(fill=tk.BOTH, expand=True)

        self.top_bar = ttk.Frame(root, style="Root.TFrame")
        self.top_bar.pack(fill=tk.X, pady=(0, 4))

        self.language_button = tk.Button(
            self.top_bar,
            text=self._language_caption(self.language),
            command=self._cycle_language,
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            cursor="hand2",
            padx=2,
        )
        self.language_button.pack(side=tk.LEFT)

        self.status_label = tk.Label(
            self.top_bar, textvariable=self.status_text, font=("Segoe UI", 8)
        )
        self.status_label.pack(side=tk.LEFT, padx=(8, 0))

        # No OS title bar anymore, so let the user drag the window by the top bar.
        for widget in (self.top_bar, self.status_label):
            widget.bind("<Button-1>", self._start_move)
            widget.bind("<B1-Motion>", self._on_move)
            widget.bind("<ButtonRelease-1>", self._on_move_done)

        self.exit_button = tk.Button(
            self.top_bar,
            text="✕ Exit",
            command=self.destroy,
            bg="#e53935",
            fg="#ffffff",
            activebackground="#c62828",
            activeforeground="#ffffff",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10, "bold"),
            padx=10,
        )
        self.exit_button.pack(side=tk.RIGHT, padx=(6, 0))

        self.clear_button = tk.Button(
            self.top_bar,
            text="Clear",
            command=self._clear_text,
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            padx=10,
        )
        self.clear_button.pack(side=tk.RIGHT, padx=(6, 0))

        self.minimize_button = tk.Button(
            self.top_bar,
            text="—",
            command=self._minimize,
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10, "bold"),
            padx=10,
        )
        self.minimize_button.pack(side=tk.RIGHT, padx=(6, 0))

        self.settings_button = tk.Button(
            self.top_bar,
            text="⚙",
            command=self._toggle_settings,
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 12),
            padx=8,
        )
        self.settings_button.pack(side=tk.RIGHT, padx=(6, 0))

        self.body = ttk.Frame(root, style="Root.TFrame")
        self.body.pack(fill=tk.BOTH, expand=True)

        self.main_view = ttk.Frame(self.body, style="Root.TFrame")
        self.settings_view = ttk.Frame(self.body, style="Root.TFrame")
        self._build_main_view(self.main_view)
        self._build_settings_panel(self.settings_view)
        self.main_view.pack(fill=tk.BOTH, expand=True)

    def _build_main_view(self, parent):
        self.suggestions = tk.Frame(parent, bg=self.palette["bg"], height=self._scaled(42))
        self.suggestions.pack(fill=tk.X, pady=(0, 6))
        self.suggestions.pack_propagate(False)

        self.keyboard_frame = ttk.Frame(parent, style="Keyboard.TFrame")
        self.keyboard_frame.pack(fill=tk.BOTH, expand=True)
        self._build_keyboard()
        self._refresh_suggestions()

    def _build_keyboard(self):
        for child in self.keyboard_frame.winfo_children():
            child.destroy()
        self.key_buttons = {}

        for row in self.layout_rows:
            items = [k for k in row if not (k == "AI" and not self.show_ai)]
            frame = ttk.Frame(self.keyboard_frame, style="Keyboard.TFrame")
            frame.pack(fill=tk.BOTH, expand=True, pady=2)
            for column, item in enumerate(items):
                frame.columnconfigure(column, weight=self._key_weight(item), uniform="keys")
                button = ttk.Button(
                    frame,
                    text=self._key_label(item),
                    style=self._style_for_key(item),
                )
                if item in self.REPEATABLE:
                    # Drive entirely from press/release so holding repeats; no
                    # command, so there's no extra fire on release.
                    button.bind("<ButtonPress-1>", lambda _e, v=item: self._start_repeat(v))
                    button.bind("<ButtonRelease-1>", lambda _e: self._stop_repeat())
                    button.bind("<Leave>", lambda _e: self._stop_repeat())
                else:
                    button.configure(command=lambda value=item: self._press_key(value))
                button.grid(row=0, column=column, sticky="nsew", padx=2)
                self.key_buttons.setdefault(item, []).append(button)
            frame.rowconfigure(0, weight=1)

    def _start_repeat(self, key):
        self._stop_repeat()
        self._press_key(key)
        delay = REPEAT_SPEEDS[self.repeat_speed][0]
        self._repeat_job = self.after(delay, lambda: self._repeat_tick(key))

    def _repeat_tick(self, key):
        self._press_key(key, feedback=False)
        interval = REPEAT_SPEEDS[self.repeat_speed][1]
        self._repeat_job = self.after(interval, lambda: self._repeat_tick(key))

    def _stop_repeat(self):
        if self._repeat_job is not None:
            self.after_cancel(self._repeat_job)
            self._repeat_job = None

    # ------------------------------------------------------------- settings panel
    def _build_settings_panel(self, parent):
        self._settings_labels = []
        self._option_groups = []

        header = ttk.Frame(parent, style="Root.TFrame")
        header.pack(fill=tk.X, pady=(0, 6))
        title = tk.Label(header, text="Settings", font=("Segoe UI", 12, "bold"))
        title.pack(side=tk.LEFT)
        self._settings_labels.append(title)
        self._settings_back = tk.Button(
            header,
            text="← Back",
            command=self._hide_settings,
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            padx=10,
            pady=2,
        )
        self._settings_back.pack(side=tk.RIGHT)

        canvas = tk.Canvas(parent, highlightthickness=0, bd=0, bg=self.palette["bg"])
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._settings_canvas = canvas

        inner = ttk.Frame(canvas, style="Root.TFrame")
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", self._on_settings_wheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        self._build_settings_categories(inner)

    def _on_settings_wheel(self, event):
        self._settings_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _build_settings_categories(self, parent):
        self._section(parent, "Appearance")
        self._add_option(parent, "Theme", list(THEMES.keys()),
                         self._set_theme, lambda: self.theme_name)
        self._add_option(parent, "Keyboard Scale", list(SCALES.keys()),
                         self._set_scale, lambda: self.scale_name)
        self._add_option(parent, "Key Press Animation", ["On", "Off"],
                         self._set_key_animation, lambda: self._onoff(self.key_animation))

        self._section(parent, "Behavior")
        self._add_option(parent, "Always on Top", ["On", "Off"],
                         self._set_always_on_top, lambda: self._onoff(self.always_on_top.get()))
        self._add_option(parent, "Remember Position", ["On", "Off"],
                         self._set_remember_position, lambda: self._onoff(self.remember_position))

        self._section(parent, "Suggestions")
        self._add_option(parent, "Enable Suggestions", ["On", "Off"],
                         self._set_suggestions_enabled, lambda: self._onoff(self.suggestions_enabled))
        self._add_option(parent, "Number of Suggestions", ["3", "6", "9"],
                         self._set_suggestion_count, lambda: str(self.suggestion_count))
        self._add_option(parent, "Auto-Insert Space", ["On", "Off"],
                         self._set_auto_space, lambda: self._onoff(self.auto_space))
        self._add_option(parent, "Learn Words", ["On", "Off"],
                         self._set_learn_words, lambda: self._onoff(self.learn_words))

        self._section(parent, "Language")
        self._add_option(parent, "Language", list(LANGUAGES.keys()),
                         self._set_language, lambda: self.language)

        self._section(parent, "Accessibility")
        self._add_option(parent, "Key Repeat Speed", list(REPEAT_SPEEDS.keys()),
                         self._set_repeat_speed, lambda: self.repeat_speed)
        self._add_option(parent, "High Contrast", ["On", "Off"],
                         self._set_high_contrast, lambda: self._onoff(self.high_contrast))
        self._add_option(parent, "Sound on Key Press", ["On", "Off"],
                         self._set_sound, lambda: self._onoff(self.sound))

        self._section(parent, "AI")
        self._add_option(parent, "Show AI Button", ["On", "Off"],
                         self._set_show_ai, lambda: self._onoff(self.show_ai))

    @staticmethod
    def _onoff(flag):
        return "On" if flag else "Off"

    def _section(self, parent, text):
        label = tk.Label(parent, text=text, font=("Segoe UI", 10, "bold"), anchor=tk.W)
        label.pack(fill=tk.X, pady=(10, 2))
        self._settings_labels.append(label)

    def _add_option(self, parent, label, options, setter, getter):
        row = ttk.Frame(parent, style="Root.TFrame")
        row.pack(fill=tk.X, pady=3, padx=4)
        caption = tk.Label(row, text=label, font=("Segoe UI", 9), width=20, anchor=tk.W)
        caption.pack(side=tk.LEFT)
        self._settings_labels.append(caption)

        buttons = {}
        for option in options:
            button = tk.Button(
                row,
                text=option,
                command=lambda value=option: setter(value),
                borderwidth=0,
                highlightthickness=0,
                font=("Segoe UI", 9),
                padx=12,
                pady=3,
            )
            button.pack(side=tk.LEFT, padx=(0, 5))
            buttons[option] = button
        self._option_groups.append((buttons, getter))

    def _toggle_settings(self):
        if self.settings_visible:
            self._hide_settings()
        else:
            self._show_settings()

    def _show_settings(self):
        self.settings_visible = True
        self.main_view.pack_forget()
        self.settings_view.pack(fill=tk.BOTH, expand=True)
        self._refresh_settings_highlights()

    def _hide_settings(self):
        self.settings_visible = False
        self.settings_view.pack_forget()
        self.main_view.pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------- setters
    def _language_caption(self, name):
        return f"🌐 {name} ▾"

    def _cycle_language(self):
        names = list(LANGUAGES.keys())
        self._set_language(names[(names.index(self.language) + 1) % len(names)])

    def _set_language(self, name):
        if name not in LANGUAGES:
            return
        self.language = name
        self.common_words = LANGUAGES[name]
        self.layout_rows = LAYOUTS[name]["rows"]
        self.shift_map = LAYOUTS[name]["shift"]
        self.shift_active = False
        self.current_word = ""
        self.language_button.config(text=self._language_caption(name))
        self._build_keyboard()
        self._refresh_suggestions()
        self._refresh_settings_highlights()
        self._save_settings()

    def _set_theme(self, name):
        if name not in THEMES:
            return
        self.theme_name = name
        self._apply_theme()
        self._save_settings()

    def _set_scale(self, value):
        if value not in SCALES:
            return
        self.scale_name = value
        self._apply_scale()
        self._refresh_settings_highlights()
        self._save_settings()

    def _set_high_contrast(self, value):
        self.high_contrast = value == "On"
        self._apply_theme()
        self._save_settings()

    def _set_always_on_top(self, value):
        self.always_on_top.set(value == "On")
        self._toggle_topmost()
        self._refresh_settings_highlights()
        self._save_settings()

    def _set_remember_position(self, value):
        self.remember_position = value == "On"
        self._refresh_settings_highlights()
        self._save_settings()

    def _set_suggestions_enabled(self, value):
        self.suggestions_enabled = value == "On"
        self._refresh_suggestions()
        self._refresh_settings_highlights()
        self._save_settings()

    def _set_suggestion_count(self, value):
        self.suggestion_count = int(value)
        self._refresh_suggestions()
        self._refresh_settings_highlights()
        self._save_settings()

    def _set_auto_space(self, value):
        self.auto_space = value == "On"
        self._refresh_settings_highlights()
        self._save_settings()

    def _set_learn_words(self, value):
        self.learn_words = value == "On"
        self._refresh_suggestions()
        self._refresh_settings_highlights()
        self._save_settings()

    def _set_key_animation(self, value):
        self.key_animation = value == "On"
        self._refresh_settings_highlights()
        self._save_settings()

    def _set_sound(self, value):
        self.sound = value == "On"
        self._refresh_settings_highlights()
        self._save_settings()

    def _set_repeat_speed(self, value):
        if value in REPEAT_SPEEDS:
            self.repeat_speed = value
        self._refresh_settings_highlights()
        self._save_settings()

    def _set_show_ai(self, value):
        self.show_ai = value == "On"
        self._build_keyboard()
        self._refresh_settings_highlights()
        self._save_settings()

    # ---------------------------------------------------------------- theming
    def _color_chrome_button(self, button):
        palette = self.palette
        button.config(
            bg=palette["chrome_bg"],
            fg=palette["chrome_fg"],
            activebackground=palette["chrome_active"],
            activeforeground=palette["chrome_fg"],
        )

    def _highlight(self, buttons, active):
        palette = self.palette
        for option, button in buttons.items():
            if option == active:
                button.config(
                    bg=palette["accent"],
                    fg=palette["accent_fg"],
                    activebackground=palette["accent"],
                    activeforeground=palette["accent_fg"],
                )
            else:
                self._color_chrome_button(button)

    def _refresh_settings_highlights(self):
        for buttons, getter in self._option_groups:
            self._highlight(buttons, getter())

    def _apply_theme(self):
        palette = self.palette
        self._configure_styles()
        self.configure(bg=palette["bg"])

        self.language_button.config(
            bg=palette["bg"],
            fg=palette["muted"],
            activebackground=palette["bg"],
            activeforeground=palette["muted"],
        )
        self.status_label.config(bg=palette["bg"], fg=palette["status"])
        self._color_chrome_button(self.clear_button)
        self._color_chrome_button(self.minimize_button)
        self._color_chrome_button(self.settings_button)

        for label in self._settings_labels:
            label.config(bg=palette["bg"], fg=palette["muted"])
        self._color_chrome_button(self._settings_back)
        self._settings_canvas.config(bg=palette["bg"])

        self.suggestions.config(bg=palette["bg"])
        self._refresh_settings_highlights()
        self._refresh_suggestions()

    # ---------------------------------------------------------------- key render
    def _shifted_char(self, key):
        if len(key) == 1 and key.isalpha():
            return key.upper()
        return self.shift_map.get(key, key)

    def _key_label(self, key):
        if key in SPECIAL_LABELS:
            return SPECIAL_LABELS[key]
        if self.shift_active:
            return self._shifted_char(key)
        if self.caps_lock and len(key) == 1 and key.isalpha():
            return key.upper()
        return key

    def _key_weight(self, key):
        if key == "Space":
            return 7
        if key in {"Enter", "Backspace"}:
            return 3
        wide = {"Symbols", "AI", "ShiftLeft", "ShiftRight", "Tab", "Caps"}
        return 2 if key in wide else 1

    def _style_for_key(self, key):
        if key in {"ShiftLeft", "ShiftRight"} and self.shift_active:
            return "Caps.TButton"
        if key == "Caps" and self.caps_lock:
            return "Caps.TButton"
        if key == "Symbols" and self.symbols_visible:
            return "Caps.TButton"
        wide = {
            "Backspace", "Space", "ShiftLeft", "ShiftRight",
            "Symbols", "AI", "Enter", "Tab", "Caps",
        }
        return "Wide.TButton" if key in wide else "Key.TButton"

    # ------------------------------------------------------------ window management
    def _root_hwnd(self):
        # tkinter's winfo_id() returns an inner child window on Windows; the
        # activation-controlling top-level frame is its GA_ROOT ancestor.
        hwnd = self.winfo_id()
        return win.user32.GetAncestor(hwnd, win.GA_ROOT) or hwnd

    def _create_taskbar_anchor(self):
        # The keyboard itself is a non-activating tool window, so it never shows
        # on the taskbar. This tiny, invisible helper window carries the taskbar
        # button instead; minimising/closing it is mirrored to the keyboard.
        anchor = tk.Toplevel(self)
        anchor.title("Virtual Keyboard")
        anchor.geometry("1x1-2000-2000")
        anchor.attributes("-alpha", 0.0)
        anchor.withdraw()
        anchor.protocol("WM_DELETE_WINDOW", self.destroy)
        self.taskbar_anchor = anchor
        self.after(150, self._mark_anchor_as_taskbar)

    def _mark_anchor_as_taskbar(self):
        if not self.taskbar_anchor:
            return
        hwnd = (
            win.user32.GetAncestor(self.taskbar_anchor.winfo_id(), win.GA_ROOT)
            or self.taskbar_anchor.winfo_id()
        )
        style = win.user32.GetWindowLongW(hwnd, win.GWL_EXSTYLE)
        style = (style | win.WS_EX_APPWINDOW) & ~win.WS_EX_TOOLWINDOW
        win.user32.SetWindowLongW(hwnd, win.GWL_EXSTYLE, style)
        self.taskbar_anchor.deiconify()
        self.after(100, self._enable_anchor_mirroring)

    def _enable_anchor_mirroring(self):
        if not self.taskbar_anchor:
            return
        self.taskbar_anchor.bind("<Unmap>", self._on_anchor_unmap)
        self.taskbar_anchor.bind("<Map>", self._on_anchor_map)
        self._anchor_ready = True

    def _on_anchor_unmap(self, _event):
        if self._anchor_ready and self.taskbar_anchor.state() == "iconic":
            self.withdraw()

    def _on_anchor_map(self, _event):
        if not self._anchor_ready:
            return
        self.deiconify()
        self.lift()
        self.after(50, self._make_no_activate)

    def _minimize(self):
        if self.taskbar_anchor is not None:
            self.taskbar_anchor.iconify()
        self.withdraw()

    def _make_no_activate(self):
        hwnd = self._root_hwnd()
        topmost = self.always_on_top.get()
        current_style = win.user32.GetWindowLongW(hwnd, win.GWL_EXSTYLE)
        new_style = current_style | win.WS_EX_NOACTIVATE | win.WS_EX_TOOLWINDOW
        if topmost:
            new_style |= win.WS_EX_TOPMOST
        else:
            new_style &= ~win.WS_EX_TOPMOST
        win.user32.SetWindowLongW(hwnd, win.GWL_EXSTYLE, new_style)
        win.user32.SetWindowPos(
            hwnd,
            win.HWND_TOPMOST if topmost else win.HWND_NOTOPMOST,
            0,
            0,
            0,
            0,
            win.SWP_NOMOVE | win.SWP_NOSIZE | win.SWP_NOACTIVATE,
        )

    def _track_target_window(self):
        hwnd = win.user32.GetForegroundWindow()
        if hwnd and not self._is_own_window(hwnd):
            self.last_target_hwnd = hwnd
        self.after(100, self._track_target_window)

    def _is_own_window(self, hwnd):
        try:
            own_hwnd = self.winfo_id()
        except tk.TclError:
            return False

        root_hwnd = win.user32.GetAncestor(hwnd, win.GA_ROOT) or hwnd
        own_root = win.user32.GetAncestor(own_hwnd, win.GA_ROOT) or own_hwnd
        return root_hwnd == own_root

    def _same_root_window(self, first_hwnd, second_hwnd):
        if not first_hwnd or not second_hwnd:
            return False
        first_root = win.user32.GetAncestor(first_hwnd, win.GA_ROOT) or first_hwnd
        second_root = win.user32.GetAncestor(second_hwnd, win.GA_ROOT) or second_hwnd
        return first_root == second_root

    def _activate_target_window(self, target_hwnd):
        if not target_hwnd or not win.user32.IsWindow(target_hwnd):
            return False

        foreground = win.user32.GetForegroundWindow()
        if self._same_root_window(foreground, target_hwnd):
            return True

        current_thread = win.kernel32.GetCurrentThreadId()
        target_thread = win.user32.GetWindowThreadProcessId(target_hwnd, None)
        foreground_thread = (
            win.user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        )

        attached_target = False
        attached_foreground = False
        try:
            if target_thread and target_thread != current_thread:
                attached_target = bool(
                    win.user32.AttachThreadInput(current_thread, target_thread, True)
                )
            if foreground_thread and foreground_thread != current_thread:
                attached_foreground = bool(
                    win.user32.AttachThreadInput(current_thread, foreground_thread, True)
                )

            if win.user32.IsIconic(target_hwnd):
                win.user32.ShowWindow(target_hwnd, win.SW_RESTORE)

            win.user32.BringWindowToTop(target_hwnd)
            win.user32.SetForegroundWindow(target_hwnd)
        finally:
            if attached_foreground:
                win.user32.AttachThreadInput(current_thread, foreground_thread, False)
            if attached_target:
                win.user32.AttachThreadInput(current_thread, target_thread, False)

        return self._same_root_window(win.user32.GetForegroundWindow(), target_hwnd)

    def _prepare_target_for_input(self):
        foreground = win.user32.GetForegroundWindow()
        if foreground and not self._is_own_window(foreground):
            self.last_target_hwnd = foreground
            return True

        if self.last_target_hwnd and win.user32.IsWindow(self.last_target_hwnd):
            if not self._activate_target_window(self.last_target_hwnd):
                self.status_text.set("Windows blocked focus; click the text field again")
                return False
            self.update_idletasks()
            return True

        self.status_text.set("Click in a text field first")
        return False

    # ----------------------------------------------------------------- drag / move
    def _start_move(self, event):
        self._drag_offset = (
            event.x_root - self.winfo_x(),
            event.y_root - self.winfo_y(),
        )

    def _on_move(self, event):
        x = event.x_root - self._drag_offset[0]
        y = event.y_root - self._drag_offset[1]
        self.geometry(f"+{x}+{y}")

    def _on_move_done(self, _event):
        if self.remember_position:
            self._save_settings()

    # ----------------------------------------------------------------------- typing
    def _clear_text(self):
        if not self._prepare_target_for_input():
            return
        try:
            win.send_ctrl_key(win.VK_A)
            win.send_virtual_key(win.VK_BACK)
        except OSError as exc:
            self.status_text.set(f"Could not clear: {exc}")
            return
        self.current_word = ""
        self.status_text.set("Cleared")
        self._refresh_suggestions()

    def _toggle_topmost(self):
        self.attributes("-topmost", self.always_on_top.get())
        hwnd = self._root_hwnd()
        insert_after = win.HWND_TOPMOST if self.always_on_top.get() else win.HWND_NOTOPMOST
        win.user32.SetWindowPos(
            hwnd,
            insert_after,
            0,
            0,
            0,
            0,
            win.SWP_NOMOVE | win.SWP_NOSIZE | win.SWP_NOACTIVATE,
        )

    def _press_key(self, key, feedback=True):
        if feedback:
            self._flash_key(key)
            self._click_sound()

        # Keys that act on the keyboard itself and never type into the target.
        if key in {"ShiftLeft", "ShiftRight"}:
            self.shift_active = not self.shift_active
            self._rebuild_keyboard_labels()
            return
        if key == "Caps":
            self.caps_lock = not self.caps_lock
            self._rebuild_keyboard_labels()
            return
        if key == "Symbols":
            self.symbols_visible = not self.symbols_visible
            self._rebuild_keyboard_labels()
            self._refresh_suggestions()
            self.status_text.set(
                "Symbols shown above" if self.symbols_visible else "Symbols hidden"
            )
            return
        if key == "AI":
            self.status_text.set("AI is a placeholder for now")
            return

        if not self._prepare_target_for_input():
            return

        try:
            if key == "Backspace":
                win.send_virtual_key(win.VK_BACK)
                self.current_word = self.current_word[:-1]
            elif key == "Enter":
                win.send_virtual_key(win.VK_RETURN)
                self._learn(self.current_word)
                self.current_word = ""
            elif key == "Tab":
                win.send_virtual_key(win.VK_TAB)
                self._learn(self.current_word)
                self.current_word = ""
            elif key == "Esc":
                win.send_virtual_key(win.VK_ESCAPE)
                self.current_word = ""
            elif key == "Space":
                win.send_virtual_key(win.VK_SPACE)
                self._learn(self.current_word)
                self.current_word = ""
            elif key == "Home":
                win.send_virtual_key(win.VK_HOME)
                self.current_word = ""
            elif key == "End":
                win.send_virtual_key(win.VK_END)
                self.current_word = ""
            elif key == "Del":
                win.send_virtual_key(win.VK_DELETE)
                self.current_word = ""
            elif key == "Left":
                win.send_virtual_key(win.VK_LEFT)
                self.current_word = ""
            elif key == "Right":
                win.send_virtual_key(win.VK_RIGHT)
                self.current_word = ""
            elif key == "Up":
                win.send_virtual_key(win.VK_UP)
                self.current_word = ""
            elif key == "Down":
                win.send_virtual_key(win.VK_DOWN)
                self.current_word = ""
            else:
                if self.shift_active:
                    character = self._shifted_char(key)
                elif self.caps_lock and len(key) == 1 and key.isalpha():
                    character = key.upper()
                else:
                    character = key
                win.send_unicode(character)
                if character.isalpha():
                    self.current_word += character.lower()
                else:
                    self._learn(self.current_word)
                    self.current_word = ""
            self.status_text.set("Typed")
        except OSError as exc:
            self.status_text.set(f"Could not type: {exc}")
            return

        # Shift is one-shot: release it after a single key (like a phone keyboard).
        if self.shift_active:
            self.shift_active = False
            self._rebuild_keyboard_labels()
        self._refresh_suggestions()

    def _insert_word(self, word):
        if not self._prepare_target_for_input():
            return
        suffix = " " if self.auto_space else ""
        try:
            win.send_unicode(completion(word, self.current_word) + suffix)
        except OSError as exc:
            self.status_text.set(f"Could not type: {exc}")
            return
        self._learn(word)
        self.current_word = ""
        self.status_text.set(f'Inserted "{word}"')
        self._refresh_suggestions()

    # ------------------------------------------------------------------ suggestions
    def _show_suggestion_bar(self):
        if not self.suggestions.winfo_manager():
            self.suggestions.pack(fill=tk.X, pady=(0, 6), before=self.keyboard_frame)

    def _hide_suggestion_bar(self):
        if self.suggestions.winfo_manager():
            self.suggestions.pack_forget()

    def _refresh_suggestions(self):
        for child in self.suggestions.winfo_children():
            child.destroy()

        if self.symbols_visible:
            self._show_suggestion_bar()
            self._fill_symbol_cells()
            return

        if not self.suggestions_enabled:
            self._hide_suggestion_bar()
            return

        self._show_suggestion_bar()
        frequencies = self.word_freq if self.learn_words else {}
        matches = rank_words(
            self.common_words, frequencies, self.current_word, self.suggestion_count
        )
        if not matches:
            matches = self.common_words[: self.suggestion_count]
        for word in matches:
            self._make_chip(word, lambda value=word: self._insert_word(value))

    def _make_chip(self, text, command):
        """A clickable, pill-shaped suggestion chip drawn on a small canvas."""
        palette = self.palette
        font = tkfont.Font(family="Segoe UI", size=self._scaled(10))
        height = self._scaled(30)
        width = font.measure(text) + self._scaled(28)

        chip = tk.Canvas(
            self.suggestions,
            width=width,
            height=height,
            bg=palette["bg"],
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        radius = height / 2
        shapes = [
            chip.create_oval(0, 0, height, height, width=0),
            chip.create_oval(width - height, 0, width, height, width=0),
            chip.create_rectangle(radius, 0, width - radius, height, width=0),
        ]
        chip.create_text(
            width / 2, height / 2, text=text, fill=palette["chip_fg"], font=font
        )

        def paint(color):
            for shape in shapes:
                chip.itemconfig(shape, fill=color)

        paint(palette["chip"])
        chip.bind("<Enter>", lambda _e: paint(palette["chip_hover"]))
        chip.bind("<Leave>", lambda _e: paint(palette["chip"]))
        chip.bind("<Button-1>", lambda _e: command())
        chip.pack(side=tk.LEFT, padx=(8, 0), pady=6)
        return chip

    def _fill_symbol_cells(self):
        # Even-width cells so any number of symbols fits the bar without overflow.
        palette = self.palette
        self.suggestions.grid_rowconfigure(0, weight=1)
        for index, symbol in enumerate(SYMBOL_ROW):
            self.suggestions.grid_columnconfigure(index, weight=1, uniform="sym")
            button = tk.Button(
                self.suggestions,
                text=symbol,
                command=lambda value=symbol: self._press_key(value),
                bg=palette["chip"],
                fg=palette["chip_fg"],
                activebackground=palette["chip_hover"],
                activeforeground=palette["chip_fg"],
                borderwidth=0,
                highlightthickness=0,
                font=("Segoe UI", self._scaled(10)),
            )
            button.grid(row=0, column=index, sticky="nsew", padx=3, pady=7)

    def _rebuild_keyboard_labels(self):
        for key, buttons in self.key_buttons.items():
            for button in buttons:
                button.configure(text=self._key_label(key), style=self._style_for_key(key))

    def _flash_key(self, key):
        if not self.key_animation:
            return
        buttons = self.key_buttons.get(key)
        if not buttons:
            return
        for button in buttons:
            button.configure(style="Caps.TButton")
        self.after(120, lambda: self._restore_key_style(key))

    def _restore_key_style(self, key):
        for button in self.key_buttons.get(key, []):
            button.configure(style=self._style_for_key(key))

    def _click_sound(self):
        if not self.sound:
            return
        try:
            winsound.MessageBeep(winsound.MB_OK)
        except RuntimeError:
            pass


def main():
    win.enable_dpi_awareness()
    app = VirtualKeyboard()
    app.mainloop()


if __name__ == "__main__":
    main()
