# Virtual Keyboard

A Windows desktop virtual keyboard prototype inspired by Google's compact
on-screen keyboard. Click the keys to type into the active application, or click a
suggested word to finish the word you started.

Built with **Python and Tkinter**, using the Windows **SendInput** API — no third-party packages required.

![Virtual Keyboard](./screenshots/keyboard.jpg)

## Run

```powershell
python app.py
```

You can also double-click `run.bat`.

## Features

- Compact keyboard layout with Norwegian and English layouts (incl. `å`, `ø`, `æ`)
- Clickable letters, numbers, punctuation, space, **Tab**, **Enter**, shift, and
  backspace
- **Navigation keys**: arrow keys, **Home**, **End**, and **Delete** for editing
- **Hold to repeat**: holding Backspace, Delete, or an arrow key repeats it
- **Real Shift**: types shifted punctuation (`!  "  #  %  &  /  (  )  =  ?` …) and
  capital letters, then auto-releases after one key (like a phone keyboard)
- **Focus-safe typing**: the window never steals focus, so it types into apps that
  close on focus loss (Windows Search, Explorer folders, etc.)
- **Symbols toggle** (`@#&` key): swaps the suggestion strip for extra symbols
  (`! ? @ # & % * ( ) = / _ : "`) that aren't already on the keyboard; press again
  to go back
- **Word suggestions** that insert the rest of the word plus a trailing space
- **Clear** button: selects all and clears the focused text field
- **AI** key: placeholder for a future AI assistant
- Custom title bar with a clearly marked red **Exit** button, draggable anywhere
  along the top bar
- **Taskbar icon** via a lightweight helper window, while the keyboard itself stays
  non-activating
- **High-DPI aware** so it renders crisply on scaled displays
- Pure standard library — Tkinter UI and the Windows `SendInput` API

## Settings

Click the **⚙** button in the top bar to open the scrollable settings panel:

**Appearance**
- **Theme** — Light or Dark (recolors the whole keyboard live)
- **Keyboard Scale** — Small / Normal / Large / Extra Large (resizes keys + window)
- **Key Press Animation** — briefly highlight a key when pressed

**Behavior**
- **Always on Top** — keep the keyboard floating above other windows, or not
- **Remember Position** — restore the window's last on-screen position on launch

**Suggestions**
- **Enable Suggestions** — show or hide the word-prediction bar
- **Number of Suggestions** — 3 / 6 / 9
- **Auto-Insert Space** — add a trailing space after inserting a suggestion
- **Learn Words** — remember the words you use most and rank them first
  (stored locally in `learned_words.json`)

**Language**
- **Language** — Norsk or English (also via the `🌐 … ▾` button, top-left)

**Accessibility**
- **Key Repeat Speed** — Slow / Normal / Fast (for held Backspace/arrows)
- **High Contrast** — black/white/yellow palette for visibility
- **Sound on Key Press** — play a click on each key (off by default)

**AI**
- **Show AI Button** — hide or show the AI key

All choices — plus the window position — are saved to `settings.json` next to
`app.py` and restored on the next launch.

## Project structure

| File | Purpose |
| --- | --- |
| `app.py` | Tkinter UI and Windows window management |
| `winapi.py` | `ctypes`/Win32 plumbing: `SendInput`, constants, DPI awareness |
| `keyboard_data.py` | Themes, layouts, Shift maps, languages, symbols, labels |
| `text_logic.py` | Pure word-suggestion logic (no Tk/Win32 dependencies) |
| `tests/` | Unit tests for `text_logic` |

## Tests

```powershell
python -m unittest discover -s tests
```

These pure-logic and data tests (no Tk/Win32 needed) also run automatically on
every push via GitHub Actions (`.github/workflows/tests.yml`).

## Notes

- This prototype is Windows-only. Click into the app where you want text to go, then
  click keys on the virtual keyboard.
- Switching language changes the key layout, the Shift mapping, the word
  suggestions, and the header label.
- Sending input to an app running as administrator requires running the keyboard as
  administrator too.
