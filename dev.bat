@echo off
:: dev.bat — run with live-reload for development
:: Opens two windows: Python backend + Vite dev server
:: The browser opens on localhost:5173 (Vite proxies API to :8000)
setlocal

set VENV=%~dp0venv
if not exist "%VENV%\Scripts\activate.bat" (
    echo [ERROR] Run install.bat first.
    pause & exit /b 1
)

cd /d "%~dp0"

:: Start Python backend
start "Label Maker — Backend" cmd /k "call venv\Scripts\activate.bat && python -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --reload"

:: Start Vite dev server
start "Label Maker — Frontend" cmd /k "cd web && npm run dev"

timeout /t 3 /nobreak >nul
start http://localhost:5173

echo Dev servers started.
endlocal
