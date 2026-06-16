# Virtual Keyboard

A Windows desktop virtual keyboard prototype inspired by Google's compact
on-screen keyboard. Click the keys to type into the active application, or click a
suggested word to finish the word you started.

## Run

```powershell
python app.py
```

You can also double-click `run.bat`.

## Features

- Compact light keyboard layout.
- Norwegian-style keys, including `å`, `ø`, and `æ`.
- Clickable letters, numbers, punctuation, space, home, shift, and backspace.
- Word suggestions that can insert the rest of the word plus a trailing space.
- Always-on-top desktop window.
- Uses Python's built-in Tkinter UI and the Windows `SendInput` API, so no Python
  packages are required.

## Notes

This first version is Windows-only. Click into the app where you want text to go,
then click keys on the virtual keyboard.
