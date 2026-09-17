@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=%~dp0venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo [ERROR] The program dependencies are not installed yet.
    echo Run install.bat once, then run this diagnostic again.
    pause
    exit /b 1
)

echo.
echo Running iron-on diagnostic...
echo This creates a sample iron-on and records every packing and export step.
echo.
"%PYTHON%" "%~dp0diagnose_ironons.py"
set "RESULT=%ERRORLEVEL%"

echo.
echo Results are in the diagnostics folder beside this file.
if not "%RESULT%"=="0" echo Review diagnostic.log and packing_plan.json for the failed step.
pause
exit /b %RESULT%