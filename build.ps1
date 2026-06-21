$ErrorActionPreference = "Stop"

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name VirtualKeyboard `
    app.py

Write-Host "Built dist\VirtualKeyboard.exe"
