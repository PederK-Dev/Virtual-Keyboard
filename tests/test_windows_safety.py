import ctypes
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform != "win32":
    raise unittest.SkipTest("Windows API safety tests require Windows")

import winapi as win
from app import (
    VirtualKeyboard,
    decode_ai_keys_payload,
    encode_ai_keys_payload,
    validated_copied_text,
)


@unittest.skipUnless(sys.platform == "win32", "Windows API tests")
class DPAPITests(unittest.TestCase):
    def test_round_trip_is_user_protected(self):
        plaintext = b'secret-value-that-should-not-appear-in-the-file'
        protected = win.protect_data(plaintext)

        self.assertNotEqual(protected, plaintext)
        self.assertEqual(win.unprotect_data(protected), plaintext)

    def test_ai_key_payload_round_trip(self):
        keys = {
            "OpenRouter": {
                "base_url": "https://example.test/v1",
                "key": "private-key",
                "model": "example-model",
            }
        }

        payload = encode_ai_keys_payload(keys)
        decoded, needs_migration = decode_ai_keys_payload(payload)

        self.assertEqual(payload["format"], "dpapi-v1")
        self.assertNotIn("private-key", payload["protected"])
        self.assertEqual(decoded, keys)
        self.assertFalse(needs_migration)

    def test_plaintext_payload_requests_migration(self):
        payload = {"OpenRouter": {"key": "old-plaintext-key"}}
        decoded, needs_migration = decode_ai_keys_payload(payload)

        self.assertEqual(decoded, payload)
        self.assertTrue(needs_migration)


class ClipboardValidationTests(unittest.TestCase):
    def test_rejects_unchanged_marker(self):
        marker = "VirtualKeyboard-copy-marker"
        self.assertIsNone(validated_copied_text(marker, marker))

    def test_rejects_empty_copy(self):
        self.assertIsNone(validated_copied_text("   ", "marker"))

    def test_accepts_fresh_copy(self):
        self.assertEqual(validated_copied_text("hello", "marker"), "hello")


class SuggestionRenderTests(unittest.TestCase):
    def test_same_signature_keeps_existing_widgets(self):
        keyboard = mock.Mock()
        keyboard._suggestion_signature = None
        keyboard.palette = {"bg": "#ffffff"}

        with mock.patch("app.tk.Frame") as frame:
            first = VirtualKeyboard._begin_suggestion_render(keyboard, ("symbols",))
            second = VirtualKeyboard._begin_suggestion_render(keyboard, ("symbols",))

        self.assertTrue(first)
        self.assertFalse(second)
        frame.assert_called_once()

    def test_new_content_is_placed_before_old_content_is_destroyed(self):
        keyboard = mock.Mock()
        old_content = mock.Mock()
        new_content = mock.Mock()
        keyboard._suggestion_content = old_content
        keyboard._pending_suggestion_content = new_content

        VirtualKeyboard._commit_suggestion_render(keyboard)

        new_content.place.assert_called_once_with(x=0, y=0, relwidth=1, relheight=1)
        new_content.lift.assert_called_once_with()
        new_content.update_idletasks.assert_called_once_with()
        old_content.destroy.assert_called_once_with()


@unittest.skipUnless(sys.platform == "win32", "Windows API tests")
class ClipboardSnapshotTests(unittest.TestCase):
    def test_ole_restore_retries_without_flushing_or_losing_pointer(self):
        snapshot = win.ClipboardSnapshot(1234)
        with (
            mock.patch.object(win.ole32, "OleSetClipboard", side_effect=[-1, 0]) as set_clipboard,
            mock.patch.object(win.ole32, "OleFlushClipboard") as flush_clipboard,
            mock.patch.object(win, "_release_com_pointer") as release,
            mock.patch.object(win.time, "sleep"),
        ):
            snapshot.restore(retries=2, retry_delay=0)

        self.assertEqual(set_clipboard.call_count, 2)
        flush_clipboard.assert_not_called()
        release.assert_called_once_with(1234)
        self.assertIsNone(snapshot._pointer)

    def test_empty_clipboard_restore_retries_open(self):
        snapshot = win.ClipboardSnapshot(None, was_empty=True)
        with (
            mock.patch.object(win.user32, "OpenClipboard", side_effect=[False, True]) as open_clipboard,
            mock.patch.object(win.user32, "EmptyClipboard", return_value=True),
            mock.patch.object(win.user32, "CloseClipboard"),
            mock.patch.object(win.time, "sleep"),
        ):
            snapshot.restore(retries=2, retry_delay=0)

        self.assertEqual(open_clipboard.call_count, 2)
        self.assertFalse(snapshot._was_empty)


@unittest.skipUnless(sys.platform == "win32", "Windows API tests")
class SendInputTests(unittest.TestCase):
    def test_input_structure_matches_windows_abi(self):
        expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(ctypes.sizeof(win.INPUT), expected)

    def test_unicode_uses_utf16_surrogates_and_special_keys(self):
        with mock.patch.object(win, "_send") as send:
            win.send_unicode("A😀\n\t")

        calls = [call.args[0] for call in send.call_args_list]
        unicode_down_events = calls[0][::2]
        self.assertEqual(
            [event.wScan for event in unicode_down_events],
            [ord("A"), 0xD83D, 0xDE00],
        )
        self.assertEqual(calls[1][0].wVk, win.VK_RETURN)
        self.assertEqual(calls[2][0].wVk, win.VK_TAB)

    def test_crlf_is_one_return_key(self):
        with mock.patch.object(win, "_send") as send:
            win.send_unicode("first\r\nsecond")

        calls = [call.args[0] for call in send.call_args_list]
        return_taps = [events for events in calls if events[0].wVk == win.VK_RETURN]
        self.assertEqual(len(return_taps), 1)


if __name__ == "__main__":
    unittest.main()
