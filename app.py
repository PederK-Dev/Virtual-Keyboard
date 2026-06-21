import sys


if sys.platform != "win32":
    raise SystemExit("This virtual keyboard currently supports Windows only.")

import base64
import json
import math
import os
import queue
import random
import struct
import tempfile
import threading
import tkinter as tk
import urllib.error
import urllib.request
import uuid
import wave
import winsound
from dataclasses import dataclass
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
from text_logic import completion, looks_like_word, rank_words


SCALES = {"Small": 0.85, "Normal": 1.0, "Large": 1.2, "Extra Large": 1.45}
# (initial delay, repeat interval) in milliseconds for hold-to-repeat keys.
REPEAT_SPEEDS = {"Slow": (500, 110), "Normal": (400, 60), "Fast": (320, 40)}

DEFAULTS = {
    "theme": "Light",
    "high_contrast": False,
    "language": "Norsk",
    "ai_pinned_language": "Off",
    "scale": "Normal",
    "always_on_top": True,
    "remember_position": True,
    "suggestions_enabled": True,
    "suggestion_count": 6,
    "auto_space": True,
    "learn_words": True,
    "repeat_speed": "Normal",
    "key_animation": True,
    "sound": "Off",
    "show_ai": True,
    "ai_enabled": False,
    "ai_provider": "LM Studio",
    "ai_translate_pinned": "Off",
    "ai_translate_language": "English",
}

SOUND_MODES = ("Off", "Clicky", "Tactile")
AI_PROVIDERS = ("LM Studio", "OpenRouter", "OpenCode", "Other")

# A browser-like User-Agent so Cloudflare-fronted gateways don't 403 the default
# "Python-urllib/x.y" agent.
AI_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 VirtualKeyboard/1.0"
)

# AI menu actions: (button label, instruction). "Translate" opens a language
# picker (see _ai_show_translate_menu) instead of using a fixed instruction.
AI_ACTIONS = [
    ("Fix", "Fix the spelling and grammar of the following text"),
    ("Rewrite", "Rewrite the following text to be clearer and more natural"),
    ("Formal", "Rewrite the following text in a formal, professional tone"),
    ("Continue", "Continue the following text naturally; return the original "
                 "text followed by your continuation"),
    ("Translate", None),
]

# Languages offered in the Translate picker. The first few are the most popular;
# the rest are alphabetical. "Auto" detects the source language automatically.
TRANSLATE_LANGUAGES = [
    "English", "Norwegian", "Spanish", "French", "German",
    "Arabic", "Chinese", "Danish", "Dutch", "Finnish", "Greek",
    "Hindi", "Italian", "Japanese", "Korean", "Polish", "Portuguese",
    "Russian", "Swedish", "Turkish", "Urdu",
]

# Maps keyboard language names (LANGUAGES keys) to translate-language names
# (TRANSLATE_LANGUAGES) so the pinned keyboard language can be shown in the
# translate picker with a ★ marker.
KEYBOARD_TO_TRANSLATE = {
    "Norsk": "Norwegian",
    "English": "English",
    "Español": "Spanish",
    "Français": "French",
    "Deutsch": "German",
    "Italiano": "Italian",
}


@dataclass
class AIRequest:
    request_id: int
    instruction: str
    target_hwnd: int
    clipboard_marker: str
    clipboard_snapshot: object
    original_text: str = ""
    result: str = ""
    apply_job: object = None
    copy_failed: bool = False


def encode_ai_keys_payload(ai_keys):
    raw = json.dumps(ai_keys, ensure_ascii=False).encode("utf-8")
    protected = base64.b64encode(win.protect_data(raw)).decode("ascii")
    return {"format": "dpapi-v1", "protected": protected}


def decode_ai_keys_payload(payload):
    if not isinstance(payload, dict):
        return {}, False
    if payload.get("format") != "dpapi-v1":
        return payload, True
    encrypted = base64.b64decode(payload["protected"], validate=True)
    decoded = win.unprotect_data(encrypted).decode("utf-8")
    data = json.loads(decoded)
    return (data if isinstance(data, dict) else {}), False


def validated_copied_text(text, marker):
    if not text or not text.strip() or text == marker:
        return None
    return text

# OpenAI-compatible provider config. base_url / key / model can be overridden via
# environment variables; LM Studio needs no real key.
def ai_provider_config(provider):
    if provider == "OpenRouter":
        return {
            "base_url": os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            "key": os.environ.get("OPENROUTER_API_KEY", ""),
            "model": os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
        }
    if provider == "OpenCode":
        return {
            "base_url": os.environ.get("OPENCODE_BASE_URL", "http://localhost:4096/v1"),
            "key": os.environ.get("OPENCODE_API_KEY", ""),
            "model": os.environ.get("OPENCODE_MODEL", ""),
        }
    if provider == "Other":
        return {
            "base_url": os.environ.get("AI_BASE_URL", "http://localhost:1234/v1"),
            "key": os.environ.get("AI_API_KEY", ""),
            "model": os.environ.get("AI_MODEL", "local-model"),
        }
    return {  # LM Studio (local)
        "base_url": os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1"),
        "key": os.environ.get("LMSTUDIO_API_KEY", "lm-studio"),
        "model": os.environ.get("LMSTUDIO_MODEL", "local-model"),
    }


def _ai_urlopen(request, timeout, retries=1):
    """urlopen that turns HTTP errors into a message including the response body.

    Retries once on transient errors (429 Too Many Requests, 503 Service
    Unavailable) after a short backoff, since AI gateways often have brief
    rate-limit windows. Other errors (403, 401, 400, 404) fail immediately.
    """
    import time
    for attempt in range(retries + 1):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace").strip()
            except Exception:
                pass
            snippet = f" — {detail[:200]}" if detail else ""
            # Retry on transient gateway errors; final attempt raises.
            if exc.code in (429, 503) and attempt < retries:
                time.sleep(1.5)
                continue
            raise RuntimeError(f"HTTP {exc.code} {exc.reason}{snippet}") from None


def _ai_apply_headers(request, base_url, key, json_body=False):
    """Attach browser-like headers so WAF/Cloudflare-fronted gateways don't 403.

    Plain urllib's default User-Agent and TLS fingerprint trip bot filters on
    endpoints like opencode.ai even when the API key is valid. We can't fully
    impersonate a browser's TLS handshake without a third-party lib, but sending
    the full set of browser headers is usually enough to get past header-based
    checks. The Authorization header is only added when a key is present.
    """
    request.add_header("User-Agent", AI_USER_AGENT)
    request.add_header("Accept", "application/json")
    request.add_header("Accept-Language", "en-US,en;q=0.9")
    request.add_header("sec-ch-ua", '"Chromium";v="124", "Google Chrome";v="124", "Not.A/Brand";v="99"')
    request.add_header("sec-ch-ua-mobile", "?0")
    request.add_header("sec-ch-ua-platform", '"Windows"')
    request.add_header("Sec-Fetch-Site", "same-site")
    request.add_header("Sec-Fetch-Mode", "cors")
    request.add_header("Sec-Fetch-Dest", "empty")
    # Origin/Referer help some gateways validate the request; derive a host root
    # from the base URL so it works for any provider (localhost, opencode.ai, …).
    try:
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        if parsed.scheme and parsed.netloc:
            root = f"{parsed.scheme}://{parsed.netloc}"
            request.add_header("Origin", root)
            request.add_header("Referer", root + "/")
    except Exception:
        pass
    if json_body:
        request.add_header("Content-Type", "application/json")
    if key:
        request.add_header("Authorization", f"Bearer {key}")


def _ai_strip_reasoning(content):
    """Remove chain-of-thought / reasoning leakage from a model's reply.

    Reasoning models (GPT-OSS, GLM, QwQ, R1, etc.) often emit their thinking
    before the answer — either inside  。
    or as plain prose like "The user wants me to ...". We strip the tagged
    blocks entirely, and if untagged reasoning is present we keep only the
    final line block that looks like the actual answer.
    """
    if not content:
        return ""
    import re
    original = content
    # 1) Remove explicit  ...  blocks (and similar tag variants).
    content = re.sub(r"<\s*(think|thinking|reasoning|reflection)\s*>.*?</\s*\1\s*>",
                     "", content, flags=re.DOTALL | re.IGNORECASE)
    # 2) Remove  blocks (non-greedy). Only matches when BOTH
    #    opening and closing  tags exist as literal text; won't eat
    #    content that just contains the word "think".
    _think_open = "<" + "think" + ">"
    _think_close = "</" + "think" + ">"
    if _think_open in content and _think_close in content:
        content = re.sub(
            re.escape(_think_open) + ".*?" + re.escape(_think_close),
            "", content, flags=re.DOTALL | re.IGNORECASE,
        )

    # 2b) Strip markdown code fences that some models wrap the answer in:
    #     ```text\n...answer...\n```  ->  ...answer...
    content = re.sub(
        r"^\s*```[a-zA-Z]*\s*\n(.*?)\n\s*```\s*$",
        r"\1", content, flags=re.DOTALL,
    )

    # 3) Handle untagged reasoning: a leading emoji, numbered reasoning steps
    #    (1. 2. 3. …), or narration ("The user wants me to…") followed by the
    #    real answer. When reasoning markers are present, the answer is the
    #    LAST non-reasoning line. We never return empty.
    lines = [ln.rstrip() for ln in content.splitlines() if ln.strip()]
    if len(lines) > 1:
        reasoning_starts = (
            "the user wants", "i need to", "i should", "i'll", "i will",
            "let me", "i have to", "i must", "i am going", "i'm going",
        )

        def _is_reasoning(ln):
            s = ln.strip()
            return (s.startswith("\U0001F9D0") or
                    bool(re.match(r"^\d+\.\s", s)) or
                    s.startswith(("* ", "- ")) or
                    s.startswith(("    *", "    -")) or
                    s.lower().startswith(reasoning_starts))

        has_reasoning = any(_is_reasoning(ln) for ln in lines)
        if has_reasoning:
            # Walk backwards; the answer is the last non-reasoning line.
            for idx in range(len(lines) - 1, -1, -1):
                if not _is_reasoning(lines[idx]):
                    lines = lines[idx:]
                    break
        content = "\n".join(lines)

    # 4) If we stripped everything, fall back to the original so the user sees
    #    something rather than "AI returned nothing".
    if not content.strip():
        return original
    return content


def ai_chat(cfg, instruction, text, timeout=60):
    """Call an OpenAI-compatible /chat/completions endpoint and return the text.

    ``cfg`` is a {"base_url", "key", "model"} dict (see ai_provider_config).
    Temperature and max_tokens are tuned per action: deterministic for Fix/
    Translate, more creative for Continue.
    """
    base_url = (cfg.get("base_url") or "").strip()
    if not base_url:
        raise ValueError("No base URL — set one in Settings → AI → Edit credentials")
    if not (cfg.get("model") or "").strip():
        raise ValueError("No model — pick one in Settings → AI → Edit credentials")

    # Tune sampling per action: Fix/Translate want determinism, Continue wants
    # creativity, Rewrite/Formal sit in between.
    instr_lower = instruction.lower()
    if "continue" in instr_lower:
        temperature, max_tokens = 0.6, 2048
    elif "rewrite" in instr_lower or "formal" in instr_lower:
        temperature, max_tokens = 0.4, 1024
    else:  # Fix, Translate, and anything else
        temperature, max_tokens = 0.0, 1024

    _think_tag = "<" + "think" + ">"
    payload = {
        "model": cfg["model"],
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a text editor. Apply the user's instruction to the "
                    "given text and return ONLY the final edited text.\n"
                    "Rules:\n"
                    "- No preamble, no explanation, no reasoning, no commentary.\n"
                    "- Do NOT describe what you are doing or what the user wants.\n"
                    f"- Do NOT output {_think_tag} blocks or any chain-of-thought.\n"
                    "- Do NOT wrap the result in quotes or markdown fences.\n"
                    "- Preserve the original language and meaning unless told to "
                    "translate.\n"
                    "- Output the edited text and nothing else."
                ),
            },
            {"role": "user", "content": f"{instruction}:\n\n{text}"},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    _ai_apply_headers(request, base_url, cfg.get("key"), json_body=True)
    with _ai_urlopen(request, timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    return _ai_strip_reasoning(content).strip()


def ai_list_models(base_url, key, timeout=15):
    """Fetch model IDs from an OpenAI-compatible /v1/models endpoint."""
    base_url = (base_url or "").strip()
    if not base_url:
        raise ValueError("No base URL")
    request = urllib.request.Request(base_url.rstrip("/") + "/models", method="GET")
    _ai_apply_headers(request, base_url, key, json_body=False)
    with _ai_urlopen(request, timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    items = body.get("data", body if isinstance(body, list) else [])
    return sorted(m["id"] for m in items if isinstance(m, dict) and "id" in m)

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
        self.ai_pinned_language = s.get("ai_pinned_language", "Off")
        if self.ai_pinned_language == "Off" and s.get("pinned_language", "Off") != "Off":
            old_pin = s.get("pinned_language", "Off")
            self.ai_pinned_language = KEYBOARD_TO_TRANSLATE.get(old_pin, "Off")
        elif self.ai_pinned_language not in TRANSLATE_LANGUAGES:
            self.ai_pinned_language = "Off"
        self.scale_name = s["scale"] if s["scale"] in SCALES else "Normal"
        self.remember_position = bool(s["remember_position"])
        self.suggestions_enabled = bool(s["suggestions_enabled"])
        self.suggestion_count = s["suggestion_count"] if s["suggestion_count"] in (3, 6, 9) else 6
        self.auto_space = bool(s["auto_space"])
        self.learn_words = bool(s["learn_words"])
        self.repeat_speed = s["repeat_speed"] if s["repeat_speed"] in REPEAT_SPEEDS else "Normal"
        self.key_animation = bool(s["key_animation"])
        sound = s["sound"]
        if isinstance(sound, bool):  # migrate the old On/Off boolean
            sound = "Clicky" if sound else "Off"
        self.sound = sound if sound in SOUND_MODES else "Off"
        self.show_ai = bool(s["show_ai"])
        self.ai_enabled = bool(s["ai_enabled"])
        self.ai_provider = s["ai_provider"] if s["ai_provider"] in AI_PROVIDERS else "LM Studio"
        self.ai_translate_pinned = s.get("ai_translate_pinned", "Off") in ("On", True)
        self.ai_translate_language = s.get("ai_translate_language", "English")
        if self.ai_translate_language not in TRANSLATE_LANGUAGES:
            self.ai_translate_language = "English"
        self._ai_keys_need_migration = False
        self.ai_keys = self._load_ai_keys()
        self.always_on_top = tk.BooleanVar(value=bool(s["always_on_top"]))
        self.word_freq = self._load_word_freq()
        self._click_paths = self._build_clicks()

        self.shift_active = False
        self.caps_lock = False
        self.symbols_visible = False
        self.ai_menu_visible = False
        self.ai_translate_menu_visible = False  # language picker submenu
        self._ai_status_anim_id = None  # animated "Asking…" timer
        self._ai_last_text = None       # original text, for undo
        self._ai_last_target_hwnd = None
        self._ai_undo_pending = False   # True until user types or undoes
        self._ai_request_counter = 0
        self._ai_active_request = None
        self._ui_queue = queue.Queue()
        self._closing = False
        self.settings_visible = False
        self.current_word = ""
        self.status_text = tk.StringVar(value="Click where text should go, then use the keys")
        self.key_buttons = {}
        self._suggestion_signature = None
        self._suggestion_content = None
        self._pending_suggestion_content = None
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
        self.after(50, self._drain_ui_queue)
        if self._ai_keys_need_migration:
            self.after(0, self._migrate_ai_keys)
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
            "ai_pinned_language": self.ai_pinned_language,
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
            "ai_enabled": self.ai_enabled,
            "ai_provider": self.ai_provider,
            "ai_translate_pinned": "On" if self.ai_translate_pinned else "Off",
            "ai_translate_language": self.ai_translate_language,
            "x": self.winfo_x(),
            "y": self.winfo_y(),
        }
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
        except OSError:
            pass

    def _ai_keys_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_keys.json")

    def _load_ai_keys(self):
        try:
            with open(self._ai_keys_path(), encoding="utf-8") as handle:
                payload = json.load(handle)
            data, needs_migration = decode_ai_keys_payload(payload)
            self._ai_keys_need_migration = needs_migration
            return data
        except (OSError, ValueError, KeyError, UnicodeError):
            return {}

    def _save_ai_keys(self):
        try:
            payload = encode_ai_keys_payload(self.ai_keys)
            path = self._ai_keys_path()
            temporary = path + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            os.replace(temporary, path)
            self._ai_keys_need_migration = False
            return True
        except (OSError, ValueError):
            return False

    def _migrate_ai_keys(self):
        if self._ai_keys_need_migration and not self._save_ai_keys():
            self.status_text.set("Could not encrypt saved AI credentials")

    def _resolve_ai_config(self):
        # Start from env/defaults, then let stored per-provider values win.
        cfg = ai_provider_config(self.ai_provider)
        stored = self.ai_keys.get(self.ai_provider, {})
        if stored.get("base_url"):
            cfg["base_url"] = stored["base_url"]
        if stored.get("key"):
            cfg["key"] = stored["key"]
        if stored.get("model"):
            cfg["model"] = stored["model"]
        return cfg

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
        if not looks_like_word(word):
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
        style.configure(
            "Settings.TCombobox",
            foreground=palette["key_fg"],
            fieldbackground=palette["key_bg"],
            background=palette["key_bg"],
            arrowcolor=palette["key_fg"],
            bordercolor=palette["key_border"],
            lightcolor=palette["key_border"],
            darkcolor=palette["key_border"],
            padding=(self._scaled(6), self._scaled(3)),
        )
        style.map(
            "Settings.TCombobox",
            foreground=[("readonly", palette["key_fg"])],
            fieldbackground=[("readonly", palette["key_bg"])],
            selectforeground=[("readonly", palette["key_fg"])],
            selectbackground=[("readonly", palette["key_bg"])],
        )
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
        style.configure(
            "Flash.TButton",
            font=key_font,
            padding=pad,
            foreground=palette["key_fg"],
            background=palette["accent"],
            bordercolor=palette["key_border"],
            lightcolor=palette["accent"],
            darkcolor=palette["key_border"],
            relief=tk.FLAT,
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

        # Language dropdown — a real dropdown (OptionMenu) instead of a cycle
        # button, so all languages are visible and selectable directly.
        self.language_var = tk.StringVar(value=self._language_caption(self.language))
        self.language_button = tk.OptionMenu(
            self.top_bar,
            self.language_var,
            self._language_caption(self.language),
            *[self._language_caption(n) for n in LANGUAGES.keys()],
        )
        # Map displayed labels back to language names via the menu commands.
        self._language_menu = self.language_button["menu"]
        self._language_menu.delete(0, "end")
        for name in LANGUAGES.keys():
            self._language_menu.add_command(
                label=self._language_caption(name),
                command=lambda value=name: self._set_language(value),
            )
        self.language_button.config(
            font=("Segoe UI", 10),
            borderwidth=0,
            highlightthickness=0,
            indicatoron=False,
            relief=tk.FLAT,
            padx=2,
            cursor="hand2",
        )
        self.language_button.pack(side=tk.LEFT)

        self.clear_button = self._make_icon_button("Clear", self._clear_text)
        self.clear_button.pack(side=tk.LEFT, padx=(12, 0))

        # Undo button — only shown after an AI paste so the user can revert it.
        # Uses U+E7A7 (Segoe MDL2 Assets "Undo") with a text fallback.
        self.undo_button = self._make_icon_button(
            "⮌", self._ai_undo, font_family="Segoe MDL2 Assets", size=10,
            fixed_width=40,
        )
        # Hidden by default; _ai_apply packs it, _ai_undo / typing hides it.
        self._undo_visible = False

        self.status_label = tk.Label(
            self.top_bar, textvariable=self.status_text, font=("Segoe UI", 8)
        )
        self.status_label.pack(side=tk.LEFT, padx=(8, 0))

        # No OS title bar anymore, so let the user drag the window by the top bar.
        for widget in (self.top_bar, self.status_label):
            widget.bind("<Button-1>", self._start_move)
            widget.bind("<B1-Motion>", self._on_move)
            widget.bind("<ButtonRelease-1>", self._on_move_done)

        self.exit_button = self._make_icon_button("", self.destroy, danger=True, font_family="Segoe MDL2 Assets", size=11, fixed_width=40)
        self.exit_button.pack(side=tk.RIGHT, padx=(6, 0))

        self.minimize_button = self._make_icon_button("", self._minimize, font_family="Segoe MDL2 Assets", size=11, fixed_width=40)
        self.minimize_button.pack(side=tk.RIGHT, padx=(6, 0))

        # U+E713 is the settings gear in the Segoe MDL2 Assets font (Windows' own
        # settings icon); falls back to a substitute glyph if the font is absent.
        self.settings_button = self._make_icon_button("", self._toggle_settings, font_family="Segoe MDL2 Assets", size=11, fixed_width=40)
        self.settings_button.pack(side=tk.RIGHT, padx=(6, 0))

        self._icon_buttons = [
            self.clear_button,
            self.exit_button,
            self.minimize_button,
            self.settings_button,
        ]

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
        self._settings_dropdowns = []
        self._settings_buttons = []

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

        self._section(parent, "Accessibility")
        self._add_option(parent, "Key Repeat Speed", list(REPEAT_SPEEDS.keys()),
                         self._set_repeat_speed, lambda: self.repeat_speed)
        self._add_option(parent, "High Contrast", ["On", "Off"],
                         self._set_high_contrast, lambda: self._onoff(self.high_contrast))
        self._add_option(parent, "Key Sound", list(SOUND_MODES),
                         self._set_sound, lambda: self.sound)

        self._section(parent, "AI")
        self._add_option(parent, "Enable AI Features", ["On", "Off"],
                         self._set_ai_enabled, lambda: self._onoff(self.ai_enabled))
        self._add_option(parent, "AI Provider", list(AI_PROVIDERS),
                         self._set_ai_provider, lambda: self.ai_provider)
        self._add_action_row(parent, "API key / model", "Edit credentials…",
                             self._open_ai_keys_dialog)
        self._add_option(parent, "Show AI Button", ["On", "Off"],
                         self._set_show_ai, lambda: self._onoff(self.show_ai))
        self._add_dropdown(parent, "Pin Language", ["Off", *TRANSLATE_LANGUAGES],
                           self._set_ai_pinned_language, lambda: self.ai_pinned_language)

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

    def _add_action_row(self, parent, label, button_text, command):
        row = ttk.Frame(parent, style="Root.TFrame")
        row.pack(fill=tk.X, pady=3, padx=4)
        caption = tk.Label(row, text=label, font=("Segoe UI", 9), width=20, anchor=tk.W)
        caption.pack(side=tk.LEFT)
        self._settings_labels.append(caption)
        button = tk.Button(
            row,
            text=button_text,
            command=command,
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 9),
            padx=12,
            pady=3,
        )
        button.pack(side=tk.LEFT, padx=(0, 5))
        self._settings_buttons.append(button)
        return button

    def _add_dropdown(self, parent, label, options, setter, getter):
        row = ttk.Frame(parent, style="Root.TFrame")
        row.pack(fill=tk.X, pady=3, padx=4)
        caption = tk.Label(row, text=label, font=("Segoe UI", 9), width=20, anchor=tk.W)
        caption.pack(side=tk.LEFT)
        self._settings_labels.append(caption)

        value = tk.StringVar(value=getter())
        dropdown = ttk.Combobox(
            row,
            textvariable=value,
            values=options,
            state="readonly",
            style="Settings.TCombobox",
            width=20,
            font=("Segoe UI", 9),
        )
        dropdown.bind("<<ComboboxSelected>>", lambda _event: setter(value.get()))
        dropdown.pack(side=tk.LEFT, padx=(0, 5))
        self._settings_dropdowns.append((dropdown, value, getter))
        return dropdown

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
        self.language_var.set(self._language_caption(name))
        self._build_keyboard()
        self._refresh_suggestions()
        self._refresh_settings_highlights()
        self._save_settings()

    def _set_ai_pinned_language(self, value):
        if value not in TRANSLATE_LANGUAGES and value != "Off":
            return
        self.ai_pinned_language = value
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
        if value not in SOUND_MODES:
            return
        self.sound = value
        if value != "Off":
            self._click_sound()  # instant preview
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

    def _set_ai_enabled(self, value):
        self.ai_enabled = value == "On"
        self._refresh_settings_highlights()
        self._save_settings()

    def _set_translate_pinned(self, value):
        self.ai_translate_pinned = value == "On"
        self._refresh_settings_highlights()
        self._save_settings()

    def _set_translate_language(self, value):
        if value in TRANSLATE_LANGUAGES:
            self.ai_translate_language = value
        self._refresh_settings_highlights()
        self._save_settings()

    def _set_ai_provider(self, value):
        if value in AI_PROVIDERS:
            self.ai_provider = value
        self._refresh_settings_highlights()
        self._save_settings()

    # ---------------------------------------------------------------- theming
    @staticmethod
    def _round_rect(canvas, x0, y0, x1, y1, r):
        points = [
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
            x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
            x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
        ]
        return canvas.create_polygon(points, smooth=True, splinesteps=16, width=0)

    def _make_icon_button(self, text, command, *, danger=False, bold=False,
                          font_family="Segoe UI", size=10, fixed_width=None):
        font = tkfont.Font(family=font_family, size=size, weight="bold" if bold else "normal")
        height = 30
        width = fixed_width if fixed_width else max(font.measure(text) + 24, height)
        canvas = tk.Canvas(
            self.top_bar,
            width=width,
            height=height,
            bg=self.palette["bg"],
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        shape = self._round_rect(canvas, 1, 1, width - 1, height - 1, 8)
        label = canvas.create_text(
            round(width / 2), round(height / 2), text=text, font=font, anchor="center"
        )
        # Recenter on the glyph's actual bounds — icon-font glyphs often have
        # uneven side bearings, so anchor-centering alone can look slightly off.
        bbox = canvas.bbox(label)
        if bbox:
            canvas.move(
                label,
                round(width / 2 - (bbox[0] + bbox[2]) / 2),
                round(height / 2 - (bbox[1] + bbox[3]) / 2),
            )
        canvas._meta = {"shape": shape, "label": label, "danger": danger}
        canvas.bind("<Enter>", lambda _e, c=canvas: self._paint_icon_button(c, True))
        canvas.bind("<Leave>", lambda _e, c=canvas: self._paint_icon_button(c, False))
        canvas.bind("<Button-1>", lambda _e: command())
        self._paint_icon_button(canvas, False)
        return canvas

    def _paint_icon_button(self, canvas, hover):
        meta = canvas._meta
        palette = self.palette
        if meta["danger"]:
            fill = "#c62828" if hover else "#e53935"
            fg = "#ffffff"
        else:
            fill = palette["chrome_active"] if hover else palette["chrome_bg"]
            fg = palette["chrome_fg"]
        canvas.config(bg=palette["bg"])
        canvas.itemconfig(meta["shape"], fill=fill)
        canvas.itemconfig(meta["label"], fill=fg)

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
        for dropdown, value, getter in self._settings_dropdowns:
            selected = getter()
            if value.get() != selected:
                value.set(selected)

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
        for button in self._icon_buttons:
            self._paint_icon_button(button, False)

        for label in self._settings_labels:
            label.config(bg=palette["bg"], fg=palette["muted"])
        self._color_chrome_button(self._settings_back)
        for button in self._settings_buttons:
            self._color_chrome_button(button)
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
        if key == "AI" and self.ai_menu_visible:
            return "Caps.TButton"
        wide = {
            "Backspace", "Space", "ShiftLeft", "ShiftRight",
            "Symbols", "AI", "Enter", "Tab", "Caps",
        }
        return "Wide.TButton" if key in wide else "Key.TButton"

    # ------------------------------------------------------------ window management
    def _post_ui(self, callback, *args):
        if not self._closing:
            self._ui_queue.put((callback, args))

    def _drain_ui_queue(self):
        if self._closing:
            return
        while True:
            try:
                callback, args = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args)
            except tk.TclError:
                pass
        self.after(50, self._drain_ui_queue)

    def destroy(self):
        if self._closing:
            return
        self._closing = True
        request = self._ai_active_request
        if request is not None:
            if request.apply_job is not None:
                try:
                    self.after_cancel(request.apply_job)
                except tk.TclError:
                    pass
            snapshot = request.clipboard_snapshot
            request.clipboard_snapshot = None
            if snapshot is not None:
                try:
                    snapshot.restore()
                except OSError:
                    snapshot.release()
        super().destroy()

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

    def _current_target_hwnd(self):
        foreground = win.user32.GetForegroundWindow()
        if foreground and not self._is_own_window(foreground):
            return foreground
        if self.last_target_hwnd and win.user32.IsWindow(self.last_target_hwnd):
            return self.last_target_hwnd
        return None

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
            if key != "Symbols":
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
            if self.symbols_visible:
                self.ai_menu_visible = False
            self._rebuild_keyboard_labels()
            self._refresh_suggestions()
            self.status_text.set(
                "Symbols shown above" if self.symbols_visible else "Symbols hidden"
            )
            return
        if key == "AI":
            if not self.ai_enabled:
                self.status_text.set("AI is off — enable it in Settings")
                return
            # Toggling AI closes any open translate submenu.
            if self.ai_translate_menu_visible:
                self.ai_translate_menu_visible = False
                self.ai_menu_visible = False
            else:
                self.ai_menu_visible = not self.ai_menu_visible
            if self.ai_menu_visible:
                self.symbols_visible = False
            self._rebuild_keyboard_labels()
            self._refresh_suggestions()
            self.status_text.set(
                "Pick an AI action above" if self.ai_menu_visible else "AI menu hidden"
            )
            return

        if not self._prepare_target_for_input():
            return

        # The user typed something — the AI undo window is over.
        if self._ai_undo_pending:
            self._ai_undo_pending = False
            self._hide_undo_button()

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

    # ----------------------------------------------------------------------- AI
    def _ai_instruction(self, label, target_language=None):
        if label == "Translate":
            target = target_language or self.ai_translate_language
            return f"Translate the following text to {target}"
        for name, instruction in AI_ACTIONS:
            if name == label and instruction:
                return instruction
        return "Rewrite the following text"

    def _open_ai_keys_dialog(self):
        provider = self.ai_provider
        palette = self.palette
        stored = self.ai_keys.get(provider, {})
        defaults = ai_provider_config(provider)

        dialog = tk.Toplevel(self)
        dialog.title(f"{provider} credentials")
        dialog.configure(bg=palette["bg"])
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.geometry(f"+{self.winfo_x() + 40}+{self.winfo_y() + 40}")

        base_var = tk.StringVar(value=stored.get("base_url", "") or defaults["base_url"])
        key_var = tk.StringVar(value=stored.get("key", ""))
        model_var = tk.StringVar(value=stored.get("model", "") or defaults["model"])

        def add_field(text, var, show=None):
            tk.Label(
                dialog, text=text, bg=palette["bg"], fg=palette["muted"],
                font=("Segoe UI", 9), anchor=tk.W,
            ).pack(fill=tk.X, padx=12, pady=(10, 0))
            entry = tk.Entry(
                dialog, textvariable=var, show=show, width=46,
                bg=palette["chip"], fg=palette["chip_fg"],
                insertbackground=palette["chip_fg"], relief=tk.FLAT,
            )
            entry.pack(fill=tk.X, padx=12, pady=(2, 0))
            return entry

        add_field("Base URL", base_var)
        key_entry = add_field("API key (blank = use environment variable)", key_var, show="•")

        # Model picker — combobox the user can type into or fill from the server.
        tk.Label(
            dialog, text="Model", bg=palette["bg"], fg=palette["muted"],
            font=("Segoe UI", 9), anchor=tk.W,
        ).pack(fill=tk.X, padx=12, pady=(10, 0))
        model_row = tk.Frame(dialog, bg=palette["bg"])
        model_row.pack(fill=tk.X, padx=12, pady=(2, 0))
        model_box = ttk.Combobox(model_row, textvariable=model_var)
        model_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        fetch_button = tk.Button(
            model_row, text="Fetch", bg=palette["chrome_bg"], fg=palette["chrome_fg"],
            activebackground=palette["chrome_active"], activeforeground=palette["chrome_fg"],
            borderwidth=0, highlightthickness=0, font=("Segoe UI", 9), padx=10,
        )
        fetch_button.pack(side=tk.LEFT, padx=(6, 0))

        status_label = tk.Label(
            dialog, text="", bg=palette["bg"], fg=palette["status"], font=("Segoe UI", 8),
        )
        status_label.pack(fill=tk.X, padx=12, pady=(4, 0))

        def set_dialog_status(text):
            if dialog.winfo_exists():
                status_label.config(text=text)

        def fetch_models():
            base = base_var.get().strip()
            key = key_var.get().strip() or defaults["key"]
            status_label.config(text="Fetching models…")

            def worker():
                try:
                    models = ai_list_models(base, key)
                except Exception as exc:  # network / HTTP / parse vary
                    msg = str(exc) or exc.__class__.__name__
                    self._post_ui(set_dialog_status, f"Failed: {msg}")
                    return

                def apply(found_models):
                    if dialog.winfo_exists():
                        model_box.configure(values=found_models)
                        status_label.config(text=f"{len(found_models)} models found")
                self._post_ui(apply, models)

            threading.Thread(target=worker, daemon=True).start()

        fetch_button.configure(command=fetch_models)

        def test_connection():
            base = base_var.get().strip()
            key = key_var.get().strip() or defaults["key"]
            model = model_var.get().strip()
            status_label.config(text="Testing…")

            def worker():
                try:
                    if model:
                        ai_chat(
                            {"base_url": base, "key": key, "model": model},
                            "Reply with the single word OK", "ping", timeout=20,
                        )
                        text = "Connected ✓"
                    else:
                        models = ai_list_models(base, key)
                        text = f"Reachable ✓ ({len(models)} models) — pick one"
                except Exception as exc:  # network / HTTP / parse vary
                    msg = str(exc) or exc.__class__.__name__
                    self._post_ui(set_dialog_status, f"Failed: {msg}")
                    return
                self._post_ui(set_dialog_status, text)

            threading.Thread(target=worker, daemon=True).start()

        buttons = tk.Frame(dialog, bg=palette["bg"])
        buttons.pack(fill=tk.X, padx=12, pady=12)

        tk.Button(
            buttons, text="Test connection", command=test_connection,
            bg=palette["chrome_bg"], fg=palette["chrome_fg"],
            activebackground=palette["chrome_active"], activeforeground=palette["chrome_fg"],
            borderwidth=0, highlightthickness=0, font=("Segoe UI", 9), padx=12, pady=4,
        ).pack(side=tk.LEFT)

        def save():
            self.ai_keys[provider] = {
                "base_url": base_var.get().strip(),
                "key": key_var.get().strip(),
                "model": model_var.get().strip(),
            }
            if not self._save_ai_keys():
                status_label.config(text="Could not encrypt and save credentials")
                return
            self.status_text.set(f"{provider} credentials saved")
            dialog.destroy()

        tk.Button(
            buttons, text="Save", command=save, bg=palette["accent"],
            fg=palette["accent_fg"], activebackground=palette["accent"],
            activeforeground=palette["accent_fg"], borderwidth=0,
            highlightthickness=0, font=("Segoe UI", 9, "bold"), padx=14, pady=4,
        ).pack(side=tk.RIGHT)
        tk.Button(
            buttons, text="Cancel", command=dialog.destroy, bg=palette["chrome_bg"],
            fg=palette["chrome_fg"], activebackground=palette["chrome_active"],
            activeforeground=palette["chrome_fg"], borderwidth=0,
            highlightthickness=0, font=("Segoe UI", 9), padx=14, pady=4,
        ).pack(side=tk.RIGHT, padx=(0, 6))

        dialog.lift()
        dialog.focus_force()
        key_entry.focus_set()

    def _ai_action(self, label, target_language=None):
        # Translate → always show the language picker first (unless a specific
        # target was already chosen from the picker).
        if label == "Translate" and not target_language:
            self._ai_show_translate_menu()
            return
        if self._ai_active_request is not None:
            self.status_text.set("An AI request is already running")
            return
        instruction = self._ai_instruction(label, target_language)
        self.ai_menu_visible = False
        self.ai_translate_menu_visible = False
        self._rebuild_keyboard_labels()
        self._refresh_suggestions()
        if not self._prepare_target_for_input():
            return
        target_hwnd = self._current_target_hwnd()
        if not target_hwnd:
            self.status_text.set("Click in a text field first")
            return

        try:
            snapshot = win.capture_clipboard()
        except OSError as exc:
            self.status_text.set(f"Could not preserve clipboard: {exc}")
            return

        self._ai_request_counter += 1
        request = AIRequest(
            request_id=self._ai_request_counter,
            instruction=instruction,
            target_hwnd=target_hwnd,
            clipboard_marker=f"VirtualKeyboard-copy-{uuid.uuid4().hex}",
            clipboard_snapshot=snapshot,
        )
        self._ai_active_request = request
        try:
            self.clipboard_clear()
            self.clipboard_append(request.clipboard_marker)
            self.update_idletasks()
            win.send_ctrl_key(win.VK_A)
            win.send_ctrl_key(win.VK_C)
        except (OSError, tk.TclError) as exc:
            self._restore_request_clipboard(request)
            self._ai_active_request = None
            self.status_text.set(f"AI error: {exc}")
            return
        self.status_text.set("Reading text…")
        self.after(160, lambda request_id=request.request_id: self._ai_collect(request_id))

    def _ai_show_translate_menu(self):
        """Replace the AI action chips with a language picker for Translate."""
        self.ai_menu_visible = False
        self.ai_translate_menu_visible = True
        self._refresh_suggestions()

    def _ai_back_from_translate(self):
        """Go back from the language picker to the main AI action menu."""
        self.ai_translate_menu_visible = False
        self.ai_menu_visible = True
        self._refresh_suggestions()

    def _restore_request_clipboard(self, request):
        snapshot = request.clipboard_snapshot
        if snapshot is None:
            return True
        try:
            snapshot.restore()
            request.clipboard_snapshot = None
            return True
        except OSError as exc:
            self.status_text.set(f"Clipboard restore failed: {exc}")
            return False

    def _ai_collect(self, request_id):
        request = self._ai_active_request
        if request is None or request.request_id != request_id:
            return
        if not request.original_text and not request.copy_failed:
            try:
                text = self.clipboard_get()
            except tk.TclError:
                text = ""
            text = validated_copied_text(text, request.clipboard_marker)
            if text is None:
                request.copy_failed = True
            else:
                request.original_text = text
        if not self._restore_request_clipboard(request):
            self.status_text.set("Clipboard is busy — retrying restoration")
            self.after(250, lambda value=request_id: self._ai_collect(value))
            return
        if request.copy_failed:
            self._ai_active_request = None
            self.status_text.set("Could not copy text from the selected field")
            return
        text = request.original_text
        self._ai_undo_pending = False
        self._hide_undo_button()
        self._ai_start_status_anim()
        config = self._resolve_ai_config()
        threading.Thread(
            target=self._ai_worker,
            args=(request.request_id, config, request.instruction, text),
            daemon=True,
        ).start()

    def _ai_start_status_anim(self):
        """Animate the 'Asking…' status so the user knows the AI is working."""
        self._ai_stop_status_anim()
        dots = ["", ".", "..", "..."]
        step = [0]

        def tick():
            label = f"Asking {self.ai_provider}…{dots[step[0] % len(dots)]}"
            self.status_text.set(label)
            step[0] += 1
            self._ai_status_anim_id = self.after(500, tick)

        tick()

    def _ai_stop_status_anim(self):
        if self._ai_status_anim_id is not None:
            self.after_cancel(self._ai_status_anim_id)
            self._ai_status_anim_id = None

    def _ai_worker(self, request_id, config, instruction, text):
        try:
            result = ai_chat(config, instruction, text)
        except Exception as exc:  # network / HTTP / parse errors vary widely
            message = str(exc) or exc.__class__.__name__
            self._post_ui(self._ai_fail, request_id, message)
            return
        self._post_ui(self._ai_result_ready, request_id, result)

    def _ai_fail(self, request_id, message):
        request = self._ai_active_request
        if request is None or request.request_id != request_id:
            return
        self._ai_stop_status_anim()
        if request.apply_job is not None:
            self.after_cancel(request.apply_job)
        self._restore_request_clipboard(request)
        self._ai_active_request = None
        self._hide_undo_button()
        self.status_text.set(f"AI failed: {message}")

    def _ai_result_ready(self, request_id, result):
        request = self._ai_active_request
        if request is None or request.request_id != request_id:
            return
        self._ai_stop_status_anim()
        if not result:
            self._ai_fail(request_id, "AI returned nothing")
            return
        request.result = result
        self._try_apply_ai_result(request_id)

    def _try_apply_ai_result(self, request_id):
        request = self._ai_active_request
        if request is None or request.request_id != request_id:
            return
        request.apply_job = None
        if not win.user32.IsWindow(request.target_hwnd):
            self._ai_fail(request_id, "The original target window was closed")
            return

        foreground = win.user32.GetForegroundWindow()
        if not self._same_root_window(foreground, request.target_hwnd):
            self.status_text.set("AI ready — return to the original text field")
            request.apply_job = self.after(
                250, lambda value=request_id: self._try_apply_ai_result(value)
            )
            return

        try:
            win.send_ctrl_key(win.VK_A)
            win.send_unicode(request.result)
        except OSError as exc:
            self._ai_fail(request_id, f"Could not type the result: {exc}")
            return
        self._ai_last_text = request.original_text
        self._ai_last_target_hwnd = request.target_hwnd
        self._ai_undo_pending = True
        self._ai_active_request = None
        self._show_undo_button()
        self.status_text.set("AI done — click ⮌ to undo")

    def _ai_undo(self):
        """Revert the last AI replacement in its original target window."""
        if not self._ai_undo_pending or not self._ai_last_text:
            self.status_text.set("Nothing to undo")
            return
        if not self._ai_last_target_hwnd or not win.user32.IsWindow(
            self._ai_last_target_hwnd
        ):
            self._ai_undo_pending = False
            self._hide_undo_button()
            self.status_text.set("The original target window was closed")
            return
        foreground = win.user32.GetForegroundWindow()
        if not self._same_root_window(foreground, self._ai_last_target_hwnd):
            self.status_text.set("Return to the original text field to undo")
            return
        try:
            win.send_ctrl_key(win.VK_A)
            win.send_unicode(self._ai_last_text)
        except OSError as exc:
            self.status_text.set(f"Undo failed: {exc}")
            return
        self._ai_undo_pending = False
        self._hide_undo_button()
        self.status_text.set("Undone")

    def _show_undo_button(self):
        if not self._undo_visible:
            self.undo_button.pack(side=tk.LEFT, padx=(8, 0),
                                  after=self.clear_button)
            self._undo_visible = True

    def _hide_undo_button(self):
        if self._undo_visible:
            self.undo_button.pack_forget()
            self._undo_visible = False

    # ------------------------------------------------------------------ suggestions
    def _show_suggestion_bar(self):
        if not self.suggestions.winfo_manager():
            self.suggestions.pack(fill=tk.X, pady=(0, 6), before=self.keyboard_frame)

    def _hide_suggestion_bar(self):
        if self.suggestions.winfo_manager():
            self.suggestions.pack_forget()

    def _begin_suggestion_render(self, signature):
        if signature == self._suggestion_signature:
            return False
        self._suggestion_signature = signature
        self._pending_suggestion_content = tk.Frame(
            self.suggestions,
            bg=self.palette["bg"],
            borderwidth=0,
            highlightthickness=0,
        )
        return True

    def _commit_suggestion_render(self, visible=True):
        new_content = self._pending_suggestion_content
        self._pending_suggestion_content = None
        old_content = self._suggestion_content

        if visible:
            new_content.place(x=0, y=0, relwidth=1, relheight=1)
            new_content.lift()
            new_content.update_idletasks()
            self._suggestion_content = new_content
        else:
            new_content.destroy()
            self._suggestion_content = None

        if old_content is not None:
            old_content.destroy()

    def _refresh_suggestions(self):
        visual = (self.theme_name, self.high_contrast, self.scale_name)

        if self.symbols_visible:
            signature = ("symbols", visual, tuple(SYMBOL_ROW))
            if not self._begin_suggestion_render(signature):
                return
            self._show_suggestion_bar()
            self._fill_symbol_cells()
            self._commit_suggestion_render()
            return

        if self.ai_menu_visible:
            labels = tuple(label for label, _instruction in AI_ACTIONS)
            signature = ("ai", visual, labels)
            if not self._begin_suggestion_render(signature):
                return
            self._show_suggestion_bar()
            for label, _instruction in AI_ACTIONS:
                self._make_chip(label, lambda value=label: self._ai_action(value))
            self._commit_suggestion_render()
            return

        if self.ai_translate_menu_visible:
            pinned_translate = (
                self.ai_pinned_language if self.ai_pinned_language != "Off" else None
            )
            ordered_languages = []
            if pinned_translate and pinned_translate in TRANSLATE_LANGUAGES:
                ordered_languages.append((f"★ {pinned_translate}", pinned_translate))
            ordered_languages.extend(
                (language, language)
                for language in TRANSLATE_LANGUAGES
                if language != pinned_translate
            )
            signature = ("translate", visual, tuple(ordered_languages))
            if not self._begin_suggestion_render(signature):
                return
            self._show_suggestion_bar()
            self._make_chip("‹ Back", lambda: self._ai_back_from_translate())
            for label, language in ordered_languages:
                self._make_chip(
                    label,
                    lambda value=language: self._ai_action("Translate", value),
                )
            self._commit_suggestion_render()
            return

        if not self.suggestions_enabled:
            if not self._begin_suggestion_render(("hidden", visual)):
                return
            self._commit_suggestion_render(visible=False)
            self._hide_suggestion_bar()
            return

        frequencies = self.word_freq if self.learn_words else {}
        matches = rank_words(
            self.common_words, frequencies, self.current_word, self.suggestion_count
        )
        if not matches:
            matches = self.common_words[: self.suggestion_count]
        signature = ("words", visual, tuple(matches))
        if not self._begin_suggestion_render(signature):
            return
        self._show_suggestion_bar()
        for word in matches:
            self._make_chip(word, lambda value=word: self._insert_word(value))
        self._commit_suggestion_render()

    def _make_chip(self, text, command):
        """A clickable, pill-shaped suggestion chip drawn on a small canvas."""
        palette = self.palette
        parent = self._pending_suggestion_content or self.suggestions
        font = tkfont.Font(family="Segoe UI", size=self._scaled(10))
        height = self._scaled(30)
        width = font.measure(text) + self._scaled(28)

        chip = tk.Canvas(
            parent,
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
        parent = self._pending_suggestion_content or self.suggestions
        parent.grid_rowconfigure(0, weight=1)
        for index, symbol in enumerate(SYMBOL_ROW):
            parent.grid_columnconfigure(index, weight=1, uniform="sym")
            button = tk.Button(
                parent,
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

    @staticmethod
    def _blend(start, end, t):
        a = start.lstrip("#")
        b = end.lstrip("#")
        channels = [
            round(int(a[i:i + 2], 16) + (int(b[i:i + 2], 16) - int(a[i:i + 2], 16)) * t)
            for i in (0, 2, 4)
        ]
        return "#{:02x}{:02x}{:02x}".format(*channels)

    _FLASH_STEPS = 5

    def _flash_key(self, key):
        if not self.key_animation:
            return
        buttons = self.key_buttons.get(key)
        if buttons:
            self._animate_press(buttons, key, 0)

    def _animate_press(self, buttons, key, step):
        if step >= self._FLASH_STEPS:
            for button in buttons:
                button.configure(style=self._style_for_key(key))
            return
        palette = self.palette
        color = self._blend(palette["accent"], palette["key_bg"], step / self._FLASH_STEPS)
        self._style.configure("Flash.TButton", background=color, lightcolor=color)
        self._style.map("Flash.TButton", background=[("active", color), ("pressed", color)])
        for button in buttons:
            button.configure(style="Flash.TButton")
        self.after(28, lambda: self._animate_press(buttons, key, step + 1))

    # Per-profile synthesis parameters for the key-press sound.
    _SOUND_PROFILES = {
        # Bright, sharp blue-switch click with a "clack" bottom-out.
        "Clicky": dict(body=200, body_dec=0.010, click_dec=0.0015, click_amp=0.50,
                       tick=2600, tick_step=350, tick_dec=0.0018, tick_amp=0.45,
                       clack=0.35, gain=0.50),
        # Softer, muted brown-switch click — quieter and rounder, no clack.
        "Tactile": dict(body=160, body_dec=0.012, click_dec=0.0022, click_amp=0.30,
                        tick=1150, tick_step=180, tick_dec=0.0026, tick_amp=0.25,
                        clack=0.0, gain=0.50),
    }

    @classmethod
    def _build_clicks(cls):
        # Render a few slightly varied WAV variants per sound profile (so rapid
        # typing doesn't sound robotic). Temp files are used because winsound
        # cannot play from memory asynchronously.
        rate = 44100
        samples = int(rate * 0.04)
        result = {}
        for name, p in cls._SOUND_PROFILES.items():
            paths = []
            for index in range(3):
                body_freq = p["body"] + index * 15
                tick_freq = p["tick"] + index * p["tick_step"]
                frames = bytearray()
                for i in range(samples):
                    t = i / rate
                    body = math.sin(2 * math.pi * body_freq * t) * math.exp(-t / p["body_dec"])
                    click = random.uniform(-1.0, 1.0) * math.exp(-t / p["click_dec"]) * p["click_amp"]
                    tick = math.sin(2 * math.pi * tick_freq * t) * math.exp(-t / p["tick_dec"]) * p["tick_amp"]
                    sample = 0.4 * body + click + tick
                    if p["clack"] and t > 0.005:
                        sample += random.uniform(-1.0, 1.0) * math.exp(-(t - 0.005) / 0.0015) * p["clack"]
                    sample = max(-1.0, min(1.0, sample * p["gain"]))
                    frames += struct.pack("<h", int(sample * 32767))
                path = os.path.join(tempfile.gettempdir(), f"vk_click_{name.lower()}_{index}.wav")
                try:
                    with wave.open(path, "wb") as writer:
                        writer.setnchannels(1)
                        writer.setsampwidth(2)
                        writer.setframerate(rate)
                        writer.writeframes(bytes(frames))
                    paths.append(path)
                except OSError:
                    pass
            result[name] = paths
        return result

    def _click_sound(self):
        paths = self._click_paths.get(self.sound)
        if not paths:
            return
        try:
            winsound.PlaySound(
                random.choice(paths),
                winsound.SND_FILENAME | winsound.SND_ASYNC,
            )
        except RuntimeError:
            pass


def main():
    win.enable_dpi_awareness()
    app = VirtualKeyboard()
    app.mainloop()


if __name__ == "__main__":
    main()
