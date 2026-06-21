"""Windows-only ctypes plumbing for the virtual keyboard.

Wraps the ``user32`` / ``kernel32`` calls and the ``SendInput`` API used to
inject keystrokes into the foreground window, plus a few window-management
constants the app needs.
"""

import ctypes
import time
from ctypes import wintypes


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ole32 = ctypes.OleDLL("ole32")
crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)

kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
user32.AttachThreadInput.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = (wintypes.HWND,)
user32.BringWindowToTop.restype = wintypes.BOOL
user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetAncestor.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.CountClipboardFormats.argtypes = ()
user32.CountClipboardFormats.restype = ctypes.c_int
user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.OpenClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = ()
user32.EmptyClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = ()
user32.CloseClipboard.restype = wintypes.BOOL
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
VK_C = 0x43
VK_V = 0x56

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9

CRYPTPROTECT_UI_FORBIDDEN = 0x01
RPC_E_CHANGED_MODE = -2147417850

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class DATA_BLOB(ctypes.Structure):
    _fields_ = (
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    )


crypt32.CryptProtectData.argtypes = (
    ctypes.POINTER(DATA_BLOB),
    wintypes.LPCWSTR,
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
)
crypt32.CryptProtectData.restype = wintypes.BOOL
crypt32.CryptUnprotectData.argtypes = (
    ctypes.POINTER(DATA_BLOB),
    ctypes.POINTER(wintypes.LPWSTR),
    ctypes.POINTER(DATA_BLOB),
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(DATA_BLOB),
)
crypt32.CryptUnprotectData.restype = wintypes.BOOL
kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
kernel32.LocalFree.restype = ctypes.c_void_p

ole32.OleInitialize.argtypes = (ctypes.c_void_p,)
ole32.OleInitialize.restype = ctypes.c_long
ole32.OleGetClipboard.argtypes = (ctypes.POINTER(ctypes.c_void_p),)
ole32.OleGetClipboard.restype = ctypes.c_long
ole32.OleSetClipboard.argtypes = (ctypes.c_void_p,)
ole32.OleSetClipboard.restype = ctypes.c_long
ole32.OleFlushClipboard.argtypes = ()
ole32.OleFlushClipboard.restype = ctypes.c_long

_ole_initialized = False


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


def _blob_from_bytes(data):
    buffer = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(
        len(data),
        ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    return blob, buffer


def _bytes_from_blob(blob):
    if not blob.pbData or not blob.cbData:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def protect_data(data, description="Virtual Keyboard AI credentials"):
    """Encrypt bytes for the current Windows user with DPAPI."""
    source, source_buffer = _blob_from_bytes(data)
    output = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(source),
        description,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return _bytes_from_blob(output)
    finally:
        if output.pbData:
            kernel32.LocalFree(output.pbData)
        del source_buffer


def unprotect_data(data):
    """Decrypt DPAPI bytes for the current Windows user."""
    source, source_buffer = _blob_from_bytes(data)
    output = DATA_BLOB()
    description = wintypes.LPWSTR()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source),
        ctypes.byref(description),
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return _bytes_from_blob(output)
    finally:
        if description:
            kernel32.LocalFree(description)
        if output.pbData:
            kernel32.LocalFree(output.pbData)
        del source_buffer


def _check_hresult(result, operation):
    if result < 0:
        raise OSError(f"{operation} failed (HRESULT 0x{result & 0xFFFFFFFF:08X})")


def _ensure_ole_initialized():
    global _ole_initialized
    if _ole_initialized:
        return
    result = ole32.OleInitialize(None)
    if result == RPC_E_CHANGED_MODE:
        raise OSError("Clipboard preservation requires an STA Windows thread")
    _check_hresult(result, "OleInitialize")
    _ole_initialized = True


def _release_com_pointer(pointer):
    if not pointer:
        return
    vtable = ctypes.cast(
        pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
    ).contents
    release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(vtable[2])
    release(pointer)


class ClipboardSnapshot:
    """Owns an OLE IDataObject reference until it is restored or released."""

    def __init__(self, pointer, was_empty=False):
        self._pointer = pointer
        self._was_empty = was_empty

    def restore(self, retries=20, retry_delay=0.025):
        if self._was_empty:
            last_error = 0
            for attempt in range(retries):
                if user32.OpenClipboard(None):
                    try:
                        if user32.EmptyClipboard():
                            self._was_empty = False
                            return
                        last_error = ctypes.get_last_error()
                    finally:
                        user32.CloseClipboard()
                else:
                    last_error = ctypes.get_last_error()
                if attempt + 1 < retries:
                    time.sleep(retry_delay)
            raise ctypes.WinError(last_error)
        if not self._pointer:
            return
        pointer = self._pointer
        result = 0
        for attempt in range(retries):
            result = ole32.OleSetClipboard(pointer)
            if result >= 0:
                self._pointer = None
                _release_com_pointer(pointer)
                return
            if attempt + 1 < retries:
                time.sleep(retry_delay)
        _check_hresult(result, "OleSetClipboard")

    def release(self):
        if self._pointer:
            pointer, self._pointer = self._pointer, None
            _release_com_pointer(pointer)

    def __del__(self):
        self.release()


def capture_clipboard():
    """Capture every clipboard format through OLE for later restoration."""
    _ensure_ole_initialized()
    pointer = ctypes.c_void_p()
    result = ole32.OleGetClipboard(ctypes.byref(pointer))
    if result < 0 and user32.CountClipboardFormats() == 0:
        return ClipboardSnapshot(None, was_empty=True)
    _check_hresult(result, "OleGetClipboard")
    if not pointer.value:
        return ClipboardSnapshot(None, was_empty=True)
    return ClipboardSnapshot(pointer.value)


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
    """Type Unicode text in batches, including supplementary-plane characters."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    pending = []

    def flush():
        if pending:
            _send(tuple(pending))
            pending.clear()

    for char in text:
        if char == "\n":
            flush()
            send_virtual_key(VK_RETURN)
            continue
        if char == "\t":
            flush()
            send_virtual_key(VK_TAB)
            continue

        encoded = char.encode("utf-16-le")
        for index in range(0, len(encoded), 2):
            code_unit = int.from_bytes(encoded[index:index + 2], "little")
            pending.extend(
                (
                    KEYBDINPUT(0, code_unit, KEYEVENTF_UNICODE, 0, 0),
                    KEYBDINPUT(
                        0,
                        code_unit,
                        KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                        0,
                        0,
                    ),
                )
            )
        if len(pending) >= 512:
            flush()
    flush()


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
