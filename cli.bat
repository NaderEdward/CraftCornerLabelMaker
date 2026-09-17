@echo off
:: Usage: cli.bat <command> [args...]
:: Examples:
::   cli.bat doctor
::   cli.bat list-templates
::   cli.bat validate-regions --template basic_sheets_NCS_stitches_AR --render-preview out\
::   cli.bat export --run-dir %USERPROFILE%\.craftcorner_labelmaker\runs\2026-08-04T14-32-05
::   cli.bat prune-runs --dry-run

setlocal

set VENV=%~dp0venv

if not exist "%VENV%\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

call "%VENV%\Scripts\activate.bat"
cd /d "%~dp0"

if "%~1"=="" (
    echo Usage: cli.bat ^<command^> [args...]
    echo.
    python -m cli --help
    echo.
    pause
    exit /b 0
)

python -m cli %*
endlocal
