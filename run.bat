@echo off
setlocal EnableDelayedExpansion

set VENV=%~dp0venv
if not exist "%VENV%\Scripts\activate.bat" (
    echo [ERROR] Run install.bat first.
    pause & exit /b 1
)
call "%VENV%\Scripts\activate.bat"
cd /d "%~dp0"

:: Start the Python server in the background
echo Starting Craft Corner Label Maker...
start /B python -m uvicorn server.main:app --host 127.0.0.1 --port 8000

:: Wait for it to be ready
timeout /t 2 /nobreak >nul

:: Open the browser
start http://localhost:8000

:: Keep the window open so the server keeps running
echo.
echo App is running at http://localhost:8000
echo Close this window to stop the server.
echo.
pause >nul
endlocal
