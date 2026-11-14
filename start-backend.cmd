@echo off
cd /d "%~dp0"
if not defined FIREWATCH_ARCHIVE_DB (
    if exist "%~dp0backend\data\firewatch.sqlite" (
        set "FIREWATCH_ARCHIVE_DB=%~dp0backend\data\firewatch.sqlite"
    ) else (
        set "FIREWATCH_ARCHIVE_DB=%~dp0..\firewatch-command-center-preview\backend\data\firewatch.sqlite"
    )
)
echo Starting read-only archive API at http://127.0.0.1:8021
"%~dp0.venv\Scripts\python.exe" -B -m uvicorn backend.api:app --host 127.0.0.1 --port 8021
if errorlevel 1 pause
