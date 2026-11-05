@echo off
title GoOnStay Backend Server (Port 8000)
cd /d "%~dp0"

echo ======================================================================
echo          GOONSTAY / BOOKMYROOM BACKEND DEVELOPMENT SERVER
echo ======================================================================
echo.

:: Detect Python executable in virtual environment or fallback to system python
set "PY_CMD="
if exist "venv\Scripts\python.exe" (
    set "PY_CMD=venv\Scripts\python.exe"
) else if exist "..\venv\Scripts\python.exe" (
    set "PY_CMD=..\venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
) else (
    set "PY_CMD=python"
)

echo [1/3] Using Python: %PY_CMD%
echo.

echo [2/3] Checking and applying database migrations...
%PY_CMD% manage.py migrate --noinput
if errorlevel 1 (
    echo [WARNING] Migration check failed. Continuing with server start...
)
echo.

echo [3/3] Starting Django Server on 0.0.0.0:8000...
echo.
echo ======================================================================
echo   Server is running at:
echo   - Localhost (This Machine) : http://localhost:8000/
echo   - Local Network (Partner)  : http://0.0.0.0:8000/
echo.
echo   Press CTRL + C or close this window to stop the server.
echo ======================================================================
echo.

%PY_CMD% manage.py runserver 0.0.0.0:8000

echo.
echo Server stopped.
pause

