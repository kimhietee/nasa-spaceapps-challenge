@echo off
if not exist "%~dp0frontend\command-center\package.json" (
    echo Could not find the frontend package.json.
    pause
    exit /b 1
)
echo Starting frontend at http://127.0.0.1:8081/#map
echo Press Ctrl+C to stop the server.
call npm.cmd --prefix "%~dp0frontend\command-center" run dev -- --host 127.0.0.1 --port 8081
if errorlevel 1 pause
