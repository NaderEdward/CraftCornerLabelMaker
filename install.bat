@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo  Craft Corner Label Maker -- Setup
echo ============================================================
echo.

:: ── Python ───────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Download from https://www.python.org/
    echo Make sure to tick "Add Python to PATH" during installation.
    pause & exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [ok] Python %PY_VER%

:: ── Node ─────────────────────────────────────────────────────
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Download from https://nodejs.org/
    pause & exit /b 1
)
for /f %%v in ('node --version') do set NODE_VER=%%v
echo [ok] Node.js %NODE_VER%

:: ── Python venv ───────────────────────────────────────────────
set VENV=%~dp0venv
if not exist "%VENV%\Scripts\activate.bat" (
    echo Creating Python virtual environment...
    python -m venv "%VENV%"
    if errorlevel 1 ( echo [ERROR] venv failed. & pause & exit /b 1 )
)
call "%VENV%\Scripts\activate.bat"

echo Installing Python dependencies...
python -m pip install --upgrade pip --quiet
pip install -r "%~dp0requirements.txt" --quiet
if errorlevel 1 ( echo [ERROR] Python install failed. & pause & exit /b 1 )
echo [ok] Python dependencies installed

:: ── Node deps ─────────────────────────────────────────────────
echo Installing Node dependencies...
cd /d "%~dp0web"
call npm install --silent
if errorlevel 1 ( echo [ERROR] npm install failed. & pause & exit /b 1 )
echo [ok] Node dependencies installed

:: ── Build frontend ────────────────────────────────────────────
echo Building frontend...
call npm run build --silent
if errorlevel 1 ( echo [ERROR] Frontend build failed. & pause & exit /b 1 )
echo [ok] Frontend built

:: ── Doctor ────────────────────────────────────────────────────
cd /d "%~dp0"
echo.
echo Running installation check...
python -m cli doctor
echo.
echo ============================================================
echo  Setup complete. Run run.bat to start the app.
echo ============================================================
echo.
pause
endlocal
