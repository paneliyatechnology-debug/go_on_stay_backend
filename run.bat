@echo off
echo Starting BookMyRoom Backend on 0.0.0.0:8000 (LAN enabled)...
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
) else (
    python manage.py runserver 0.0.0.0:8000
)
pause

