import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from keyboard_data import (
    HIGH_CONTRAST,
    LANGUAGES,
    LAYOUTS,
    SPECIAL_LABELS,
    SYMBOL_ROW,
    THEMES,
)

# Keys that are actions, not literal characters to type.
SPECIAL_KEYS = {
    "Backspace", "Del", "Caps", "ShiftLeft", "ShiftRight", "Home", "End",
    "Symbols", "AI", "Enter", "Tab", "Left", "Up", "Down", "Right", "Space",
}

# Every palette must define the same set of colour roles the UI reads.
THEME_KEYS = set(THEMES["Light"].keys())


class LayoutTests(unittest.TestCase):
    def test_languages_and_layouts_match(self):
        self.assertEqual(set(LANGUAGES), set(LAYOUTS))

    def test_shift_map_keys_exist_in_rows(self):
        for name, layout in LAYOUTS.items():
            keys_on_board = {key for row in layout["rows"] for key in row}
            for shift_key in layout["shift"]:
                self.assertIn(
                    shift_key,
                    keys_on_board,
                    msg=f"{name}: shift key {shift_key!r} is not on the board",
                )

    def test_shift_values_are_single_chars(self):
        for name, layout in LAYOUTS.items():
            for base, shifted in layout["shift"].items():
                self.assertEqual(
                    len(shifted), 1, msg=f"{name}: {base!r} -> {shifted!r} not one char"
                )

    def test_every_layout_has_space_and_enter(self):
        for name, layout in LAYOUTS.items():
            flat = {key for row in layout["rows"] for key in row}
            self.assertIn("Space", flat, msg=f"{name} missing Space")
            self.assertIn("Enter", flat, msg=f"{name} missing Enter")

    def test_special_keys_have_labels(self):
        for name, layout in LAYOUTS.items():
            for row in layout["rows"]:
                for key in row:
                    if key in SPECIAL_KEYS and key != "Space":
                        self.assertIn(
                            key,
                            SPECIAL_LABELS,
                            msg=f"{name}: {key!r} has no display label",
                        )


class ThemeTests(unittest.TestCase):
    def test_all_themes_share_the_same_roles(self):
        for name, palette in THEMES.items():
            self.assertEqual(
                set(palette), THEME_KEYS, msg=f"{name} palette has mismatched keys"
            )

    def test_high_contrast_matches_theme_roles(self):
        self.assertEqual(set(HIGH_CONTRAST), THEME_KEYS)


class SymbolRowTests(unittest.TestCase):
    def test_symbols_are_single_chars(self):
        for symbol in SYMBOL_ROW:
            self.assertEqual(len(symbol), 1)

    def test_no_duplicate_symbols(self):
        self.assertEqual(len(SYMBOL_ROW), len(set(SYMBOL_ROW)))


if __name__ == "__main__":
    unittest.main()
