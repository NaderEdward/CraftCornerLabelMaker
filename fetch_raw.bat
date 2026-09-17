@echo off
setlocal

set VENV=%~dp0venv
if not exist "%VENV%\Scripts\activate.bat" (
    echo [ERROR] Run install.bat first.
    pause & exit /b 1
)
call "%VENV%\Scripts\activate.bat"
cd /d "%~dp0"

python fetch_raw.py
endlocal
