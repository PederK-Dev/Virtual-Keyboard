$ErrorActionPreference = "Stop"

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name VirtualKeyboard `
    --icon assets\VirtualKeyboard.ico `
    --add-data "assets\VirtualKeyboard.ico;assets" `
    app.py

Write-Host "Built dist\VirtualKeyboard.exe"
