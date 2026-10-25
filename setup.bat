@echo off
REM One-time setup on a new Windows machine: Python packages, the notes index, Ollama models, the speech model.
REM Safe to run again; it only adds what is missing. Needs Python 3.11+ (python.org) and Ollama (ollama.com).
cd /d "%~dp0"
echo.
echo === OS Tutor setup ===
if not exist .venv\Scripts\python.exe (
  where py >nul 2>nul && (py -3 -m venv .venv) || (python -m venv .venv)
)
if not exist .venv\Scripts\python.exe (
  echo Could not create the Python environment. Install Python 3.11 or newer from python.org ^(tick "Add to PATH"^), then run this again.
  pause
  exit /b 1
)
.venv\Scripts\python -m pip install --upgrade pip >nul
echo Installing the exact package versions the app was tested with (requirements-lock.txt)...
.venv\Scripts\python -m pip install -r requirements-lock.txt
if errorlevel 1 (
  echo Those exact versions do not install on this Python. Installing the newest compatible versions instead.
  .venv\Scripts\python -m pip install -r requirements.txt faster-whisper
  if errorlevel 1 (
    echo Installing the packages failed. Check the internet connection and run this again.
    pause
    exit /b 1
  )
)
.venv\Scripts\python -m server.doctor --fix
echo Setup finished. Start the tutor with start.bat
pause
