@echo off
setlocal

set VENV=%~dp0venv

if not exist "%VENV%\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

call "%VENV%\Scripts\activate.bat"
cd /d "%~dp0"

echo ============================================================
echo  Craft Corner Label Maker -- Installation Check
echo ============================================================
echo.
python -m cli doctor
echo.
echo ============================================================
echo.
pause
endlocal
