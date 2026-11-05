# GoOnStay Backend Server PowerShell Launcher
$Host.UI.RawUI.WindowTitle = "GoOnStay Backend Server (Port 8000)"
Set-Location -Path $PSScriptRoot

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "         GOONSTAY / BOOKMYROOM BACKEND DEVELOPMENT SERVER" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# Locate Python
$pyCmd = "python"
if (Test-Path "venv\Scripts\python.exe") {
    $pyCmd = "venv\Scripts\python.exe"
} elseif (Test-Path "..\venv\Scripts\python.exe") {
    $pyCmd = "..\venv\Scripts\python.exe"
} elseif (Test-Path ".venv\Scripts\python.exe") {
    $pyCmd = ".venv\Scripts\python.exe"
}

Write-Host "`n[1/3] Using Python: $pyCmd" -ForegroundColor Yellow

Write-Host "`n[2/3] Checking migrations..." -ForegroundColor Yellow
& $pyCmd manage.py migrate --noinput

Write-Host "`n[3/3] Starting Django on 0.0.0.0:8000..." -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  Server is live at:" -ForegroundColor White
Write-Host "  - Localhost (This PC) : http://localhost:8000/" -ForegroundColor Green
Write-Host "  - LAN IP (Partner PC) : http://<your-ip>:8000/" -ForegroundColor Green
Write-Host "`n  Press CTRL+C to stop." -ForegroundColor White
Write-Host "======================================================================`n" -ForegroundColor Cyan

& $pyCmd manage.py runserver 0.0.0.0:8000

