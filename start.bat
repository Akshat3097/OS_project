@echo off
REM Start the OS Tutor: makes sure Ollama runs, loads the tutor model on the GPU, then opens http://localhost:8000
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo First run on this machine: running setup.bat first.
  call "%~dp0setup.bat"
)
.venv\Scripts\python -m server.doctor --start
.venv\Scripts\python -m server %*
if errorlevel 1 pause
