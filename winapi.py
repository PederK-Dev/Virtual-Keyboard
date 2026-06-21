"""Windows-only ctypes plumbing for the virtual keyboard.

Wraps the ``user32`` / ``kernel32`` calls and the ``SendInput`` API used to
inject keystrokes into the foreground window, plus a few window-management
constants the app needs.
"""

import ctypes
from ctypes import wintypes


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
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetWindowLongW.restype = wintypes.LONG
user32.SetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.LONG)
user32.SetWindowLongW.restype = wintypes.LONG
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
VK_SPACE = 0x20
VK_END = 0x23
VK_HOME = 0x24
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_DELETE = 0x2E
VK_A = 0x41

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
        raise ctypes.WinError(ctypes.get_last_error())


def _send(sequence):
    batch = (INPUT * len(sequence))(
        *[INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(ki=key)) for key in sequence]
    )
    sent = user32.SendInput(len(sequence), batch, ctypes.sizeof(INPUT))
    _check_send_input(sent, len(sequence))


def send_unicode(text):
    """Type ``text`` character by character as Unicode key events."""
    for char in text:
        code = ord(char)
        _send(
            (
                KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0),
                KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0),
            )
        )


def send_virtual_key(vk_code):
    """Tap a single virtual key (down then up)."""
    _send(
        (
            KEYBDINPUT(vk_code, 0, 0, 0, 0),
            KEYBDINPUT(vk_code, 0, KEYEVENTF_KEYUP, 0, 0),
        )
    )


def send_ctrl_key(vk_code):
    """Send Ctrl + ``vk_code`` (e.g. Ctrl+A)."""
    _send(
        (
            KEYBDINPUT(VK_CONTROL, 0, 0, 0, 0),
            KEYBDINPUT(vk_code, 0, 0, 0, 0),
            KEYBDINPUT(vk_code, 0, KEYEVENTF_KEYUP, 0, 0),
            KEYBDINPUT(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0, 0),
        )
    )


def enable_dpi_awareness():
    """Make the process DPI-aware so Tk renders crisply on high-DPI displays.

    Must be called before any window is created. Best-effort: silently does
    nothing on systems where the calls are unavailable.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # System DPI aware
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass
