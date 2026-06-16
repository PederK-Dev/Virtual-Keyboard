import ctypes
import sys
import tkinter as tk
from ctypes import wintypes
from tkinter import ttk


if sys.platform != "win32":
    raise SystemExit("This virtual keyboard currently supports Windows only.")


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
user32.AttachThreadInput.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = (wintypes.HWND,)
user32.BringWindowToTop.restype = wintypes.BOOL
user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetAncestor.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
)
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.IsIconic.restype = wintypes.BOOL
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL
user32.SetFocus.argtypes = (wintypes.HWND,)
user32.SetFocus.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.ShowWindow.restype = wintypes.BOOL

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
GWL_EXSTYLE = -20
GA_ROOT = 2
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_ESCAPE = 0x1B
VK_A = 0x41
VK_SPACE = 0x20
VK_HOME = 0x24

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class INPUT_UNION(ctypes.Union):
    _fields_ = (
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    )


class INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("union", INPUT_UNION))


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def _check_send_input(result, inputs):
    if result != inputs:
        error = ctypes.get_last_error()
        raise ctypes.WinError(error)


def send_unicode(text):
    for char in text:
        code = ord(char)
        down = INPUT(
            type=INPUT_KEYBOARD,
            union=INPUT_UNION(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0)),
        )
        up = INPUT(
            type=INPUT_KEYBOARD,
            union=INPUT_UNION(
                ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)
            ),
        )
        batch = (INPUT * 2)(down, up)
        sent = user32.SendInput(2, batch, ctypes.sizeof(INPUT))
        _check_send_input(sent, 2)


def send_virtual_key(vk_code):
    down = INPUT(
        type=INPUT_KEYBOARD,
        union=INPUT_UNION(ki=KEYBDINPUT(vk_code, 0, 0, 0, 0)),
    )
    up = INPUT(
        type=INPUT_KEYBOARD,
        union=INPUT_UNION(ki=KEYBDINPUT(vk_code, 0, KEYEVENTF_KEYUP, 0, 0)),
    )
    batch = (INPUT * 2)(down, up)
    sent = user32.SendInput(2, batch, ctypes.sizeof(INPUT))
    _check_send_input(sent, 2)


def send_ctrl_key(vk_code):
    sequence = (
        KEYBDINPUT(VK_CONTROL, 0, 0, 0, 0),
        KEYBDINPUT(vk_code, 0, 0, 0, 0),
        KEYBDINPUT(vk_code, 0, KEYEVENTF_KEYUP, 0, 0),
        KEYBDINPUT(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0, 0),
    )
    batch = (INPUT * len(sequence))(
        *[INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(ki=key)) for key in sequence]
    )
    sent = user32.SendInput(len(sequence), batch, ctypes.sizeof(INPUT))
    _check_send_input(sent, len(sequence))


class VirtualKeyboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Virtual Keyboard")
        self.geometry("560x285")
        self.minsize(520, 245)
        self.configure(bg="#ffffff")
        self.attributes("-topmost", True)
        # Remove the native OS title bar so the keyboard has a single, clearly
        # styled Exit button instead of the OS close button plus a custom one.
        self.overrideredirect(True)
        self._drag_offset = (0, 0)

        self.caps = False
        self.symbols_visible = False
        self.always_on_top = tk.BooleanVar(value=True)
        self.current_word = ""
        self.status_text = tk.StringVar(value="Click where text should go, then use the keys")
        self.key_buttons = {}
        self.last_target_hwnd = None

        self.common_words = [
            "og",
            "jeg",
            "det",
            "du",
            "er",
            "ikke",
            "til",
            "med",
            "for",
            "som",
            "hei",
            "takk",
            "ja",
            "nei",
            "kan",
            "skrive",
            "norsk",
            "keyboard",
            "virtual",
            "klikke",
            "ord",
            "hvor",
            "når",
            "hva",
            "bra",
            "veldig",
        ]

        self.taskbar_anchor = None
        self._anchor_ready = False

        self._build_styles()
        self._build_ui()
        self._create_taskbar_anchor()
        self.after(200, self._make_no_activate)
        self.after(250, self._track_target_window)

    def _build_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Root.TFrame", background="#ffffff")
        style.configure("Keyboard.TFrame", background="#ffffff")
        style.configure("Key.TButton", font=("Segoe UI", 10), padding=(7, 5))
        style.configure("Wide.TButton", font=("Segoe UI", 10), padding=(7, 5))
        style.configure("Word.TButton", font=("Segoe UI", 9), padding=(8, 4))
        style.configure(
            "Caps.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=(7, 5),
            foreground="#111111",
            background="#d7eaff",
        )
        for button_style in ("Key.TButton", "Wide.TButton", "Word.TButton"):
            style.configure(
                button_style,
                foreground="#333333",
                background="#f2f2f2",
                bordercolor="#d2d2d2",
                lightcolor="#f7f7f7",
                darkcolor="#d2d2d2",
                relief=tk.FLAT,
            )
            style.map(
                button_style,
                background=[("active", "#e6e6e6"), ("pressed", "#dadada")],
            )

    def _build_ui(self):
        root = ttk.Frame(self, style="Root.TFrame", padding=8)
        root.pack(fill=tk.BOTH, expand=True)

        top_bar = ttk.Frame(root, style="Root.TFrame")
        top_bar.pack(fill=tk.X, pady=(0, 4))

        title = tk.Label(
            top_bar,
            text="Norsk",
            bg="#ffffff",
            fg="#777777",
            font=("Segoe UI", 10),
        )
        title.pack(side=tk.LEFT)

        status = tk.Label(
            top_bar,
            textvariable=self.status_text,
            bg="#ffffff",
            fg="#999999",
            font=("Segoe UI", 8),
        )
        status.pack(side=tk.LEFT, padx=(8, 0))

        # No OS title bar anymore, so let the user drag the window by the top bar.
        for widget in (top_bar, title, status):
            widget.bind("<Button-1>", self._start_move)
            widget.bind("<B1-Motion>", self._on_move)

        exit_button = tk.Button(
            top_bar,
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
        exit_button.pack(side=tk.RIGHT, padx=(6, 0))

        clear_button = tk.Button(
            top_bar,
            text="Clear",
            command=self._clear_text,
            bg="#eeeeee",
            fg="#555555",
            activebackground="#e0e0e0",
            activeforeground="#333333",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            padx=10,
        )
        clear_button.pack(side=tk.RIGHT)

        self.suggestions = ttk.Frame(root, style="Root.TFrame")
        self.suggestions.pack(fill=tk.X, pady=(0, 4))
        self._refresh_suggestions()

        keyboard = ttk.Frame(root, style="Keyboard.TFrame")
        keyboard.pack(fill=tk.BOTH, expand=True)

        rows = [
            ["|", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "+", "\\", "Backspace"],
            ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "å", "¨"],
            ["Home", "a", "s", "d", "f", "g", "h", "j", "k", "l", "ø", "æ", "'"],
            ["ShiftLeft", "<", "z", "x", "c", "v", "b", "n", "m", ",", ".", "-", "ShiftRight"],
            ["Symbols", "Space", "AI"],
        ]

        for row in rows:
            frame = ttk.Frame(keyboard, style="Keyboard.TFrame")
            frame.pack(fill=tk.BOTH, expand=True, pady=2)
            for column, item in enumerate(row):
                weight = self._key_weight(item)
                frame.columnconfigure(column, weight=weight, uniform="keys")
                button = ttk.Button(
                    frame,
                    text=self._key_label(item),
                    style=self._style_for_key(item),
                    command=lambda value=item: self._press_key(value),
                )
                button.grid(row=0, column=column, sticky="nsew", padx=2)
                self.key_buttons.setdefault(item, []).append(button)
            frame.rowconfigure(0, weight=1)

    def _key_label(self, key):
        labels = {
            "Backspace": "⌫",
            "ShiftLeft": "⇧",
            "ShiftRight": "⇧",
            "Home": "⌂",
            "Symbols": "@#&",
            "AI": "✨ AI",
        }
        if key in labels:
            return labels[key]
        if len(key) == 1 and key.isalpha():
            return key.upper() if self.caps else key
        return key

    def _key_weight(self, key):
        if key == "Space":
            return 7
        if key in {"Symbols", "AI"}:
            return 2
        if key in {"Backspace", "Home", "ShiftLeft", "ShiftRight"}:
            return 2
        return 1

    def _style_for_key(self, key):
        if key in {"ShiftLeft", "ShiftRight"} and self.caps:
            return "Caps.TButton"
        if key == "Symbols" and self.symbols_visible:
            return "Caps.TButton"
        if key in {"Backspace", "Space", "Home", "ShiftLeft", "ShiftRight", "Symbols", "AI"}:
            return "Wide.TButton"
        return "Key.TButton"

    def _root_hwnd(self):
        # tkinter's winfo_id() returns an inner child window on Windows; the
        # activation-controlling top-level frame is its GA_ROOT ancestor.
        hwnd = self.winfo_id()
        return user32.GetAncestor(hwnd, GA_ROOT) or hwnd

    def _create_taskbar_anchor(self):
        # The keyboard itself is a non-activating tool window, so it never shows
        # on the taskbar. This tiny, invisible helper window carries the taskbar
        # button instead; minimising/closing it is mirrored to the keyboard.
        anchor = tk.Toplevel(self)
        anchor.title("Virtual Keyboard")
        anchor.geometry("1x1-2000-2000")
        anchor.attributes("-alpha", 0.0)
        anchor.protocol("WM_DELETE_WINDOW", self.destroy)
        anchor.bind("<Unmap>", self._on_anchor_unmap)
        anchor.bind("<Map>", self._on_anchor_map)
        self.taskbar_anchor = anchor
        self.after(150, self._mark_anchor_as_taskbar)

    def _mark_anchor_as_taskbar(self):
        if not self.taskbar_anchor:
            return
        hwnd = (
            user32.GetAncestor(self.taskbar_anchor.winfo_id(), GA_ROOT)
            or self.taskbar_anchor.winfo_id()
        )
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        # Re-show so Windows re-evaluates the taskbar flag.
        user32.ShowWindow(hwnd, SW_HIDE)
        user32.ShowWindow(hwnd, SW_SHOW)
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

    def _make_no_activate(self):
        hwnd = self._root_hwnd()
        current_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        new_style = current_style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
        user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )

    def _track_target_window(self):
        hwnd = user32.GetForegroundWindow()
        if hwnd and not self._is_own_window(hwnd):
            self.last_target_hwnd = hwnd
        self.after(100, self._track_target_window)

    def _is_own_window(self, hwnd):
        try:
            own_hwnd = self.winfo_id()
        except tk.TclError:
            return False

        root_hwnd = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
        own_root = user32.GetAncestor(own_hwnd, GA_ROOT) or own_hwnd
        return root_hwnd == own_root

    def _same_root_window(self, first_hwnd, second_hwnd):
        if not first_hwnd or not second_hwnd:
            return False
        first_root = user32.GetAncestor(first_hwnd, GA_ROOT) or first_hwnd
        second_root = user32.GetAncestor(second_hwnd, GA_ROOT) or second_hwnd
        return first_root == second_root

    def _activate_target_window(self, target_hwnd):
        if not target_hwnd or not user32.IsWindow(target_hwnd):
            return False

        foreground = user32.GetForegroundWindow()
        if self._same_root_window(foreground, target_hwnd):
            return True

        current_thread = kernel32.GetCurrentThreadId()
        target_thread = user32.GetWindowThreadProcessId(target_hwnd, None)
        foreground_thread = (
            user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        )

        attached_target = False
        attached_foreground = False
        try:
            if target_thread and target_thread != current_thread:
                attached_target = bool(
                    user32.AttachThreadInput(current_thread, target_thread, True)
                )
            if foreground_thread and foreground_thread != current_thread:
                attached_foreground = bool(
                    user32.AttachThreadInput(current_thread, foreground_thread, True)
                )

            if user32.IsIconic(target_hwnd):
                user32.ShowWindow(target_hwnd, SW_RESTORE)

            user32.BringWindowToTop(target_hwnd)
            user32.SetForegroundWindow(target_hwnd)
        finally:
            if attached_foreground:
                user32.AttachThreadInput(current_thread, foreground_thread, False)
            if attached_target:
                user32.AttachThreadInput(current_thread, target_thread, False)

        return self._same_root_window(user32.GetForegroundWindow(), target_hwnd)

    def _prepare_target_for_input(self):
        foreground = user32.GetForegroundWindow()
        if foreground and not self._is_own_window(foreground):
            self.last_target_hwnd = foreground
            return True

        if self.last_target_hwnd and user32.IsWindow(self.last_target_hwnd):
            if not self._activate_target_window(self.last_target_hwnd):
                self.status_text.set("Windows blocked focus; click the text field again")
                return False
            self.update_idletasks()
            return True

        self.status_text.set("Click in a text field first")
        return False

    def _start_move(self, event):
        self._drag_offset = (
            event.x_root - self.winfo_x(),
            event.y_root - self.winfo_y(),
        )

    def _on_move(self, event):
        x = event.x_root - self._drag_offset[0]
        y = event.y_root - self._drag_offset[1]
        self.geometry(f"+{x}+{y}")

    def _clear_text(self):
        if not self._prepare_target_for_input():
            return
        try:
            send_ctrl_key(VK_A)
            send_virtual_key(VK_BACK)
        except OSError as exc:
            self.status_text.set(f"Could not clear: {exc}")
            return
        self.current_word = ""
        self.status_text.set("Cleared")
        self._refresh_suggestions()

    def _toggle_topmost(self):
        self.attributes("-topmost", self.always_on_top.get())
        hwnd = self._root_hwnd()
        insert_after = HWND_TOPMOST if self.always_on_top.get() else HWND_NOTOPMOST
        user32.SetWindowPos(
            hwnd,
            insert_after,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )

    def _press_key(self, key):
        try:
            if key not in {"ShiftLeft", "ShiftRight", "Symbols", "AI"}:
                if not self._prepare_target_for_input():
                    return

            if key == "Backspace":
                send_virtual_key(VK_BACK)
                self.current_word = self.current_word[:-1]
            elif key == "Enter":
                send_virtual_key(VK_RETURN)
                self.current_word = ""
            elif key == "Tab":
                send_virtual_key(VK_TAB)
                self.current_word = ""
            elif key == "Esc":
                send_virtual_key(VK_ESCAPE)
                self.current_word = ""
            elif key == "Space":
                send_virtual_key(VK_SPACE)
                self.current_word = ""
            elif key == "Home":
                send_virtual_key(VK_HOME)
                self.current_word = ""
            elif key in {"ShiftLeft", "ShiftRight"}:
                self.caps = not self.caps
                self._rebuild_keyboard_labels()
            elif key == "Symbols":
                self.symbols_visible = not self.symbols_visible
                self._rebuild_keyboard_labels()
                self._refresh_suggestions()
                self.status_text.set(
                    "Symbols shown above" if self.symbols_visible else "Symbols hidden"
                )
                return
            elif key == "AI":
                self.status_text.set("AI is a placeholder for now")
                return
            else:
                character = key.upper() if self.caps and key.isalpha() else key
                send_unicode(character)
                if character.isalpha():
                    self.current_word += character.lower()
                else:
                    self.current_word = ""
            self.status_text.set("Typed")
            self._refresh_suggestions()
        except OSError as exc:
            self.status_text.set(f"Could not type: {exc}")

    def _insert_word(self, word):
        if not self._prepare_target_for_input():
            return

        suffix = " "
        replacement = word[len(self.current_word) :] + suffix
        if replacement:
            send_unicode(replacement)
        self.current_word = ""
        self.status_text.set(f'Inserted "{word}"')
        self._refresh_suggestions()

    def _refresh_suggestions(self):
        for child in self.suggestions.winfo_children():
            child.destroy()

        if self.symbols_visible:
            self._fill_symbol_row()
            return

        matches = self._matching_words()
        if not matches:
            matches = self.common_words[:6]

        for word in matches[:6]:
            button = ttk.Button(
                self.suggestions,
                text=word,
                style="Word.TButton",
                command=lambda value=word: self._insert_word(value),
            )
            button.pack(side=tk.LEFT, padx=2)

    def _fill_symbol_row(self):
        symbols = [
            "!", "?", "@", "#", "&", "%", "*",
            "(", ")", "=", "/", "_", ":", '"',
        ]
        for index, symbol in enumerate(symbols):
            self.suggestions.columnconfigure(index, weight=1, uniform="words")
            button = ttk.Button(
                self.suggestions,
                text=symbol,
                style="Word.TButton",
                command=lambda value=symbol: self._press_key(value),
            )
            button.grid(row=0, column=index, sticky="ew", padx=2)

    def _matching_words(self):
        if not self.current_word:
            return self.common_words[:8]
        exact_prefix = [
            word for word in self.common_words if word.startswith(self.current_word)
        ]
        return exact_prefix or [self.current_word]

    def _rebuild_keyboard_labels(self):
        for key, buttons in self.key_buttons.items():
            for button in buttons:
                button.configure(text=self._key_label(key), style=self._style_for_key(key))


def main():
    app = VirtualKeyboard()
    app.mainloop()


if __name__ == "__main__":
    main()
