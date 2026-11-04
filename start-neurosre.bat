@echo off
rem Double-click to start NeuroSRE. Close this window (or press Ctrl+C) to stop it.
title NeuroSRE
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo First run: creating the Python environment and installing libraries. This takes a few minutes...
  python -m venv .venv || (echo Python 3.11+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (echo Installing libraries failed. & pause & exit /b 1)
)
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env. Add your Groq API key to it to use the AI; without a key NeuroSRE runs in offline rule-based mode.
)

echo Starting NeuroSRE... the browser opens at http://localhost:8000 in about 20 seconds.
start "" /min cmd /c "timeout /t 20 /nobreak >nul & start http://localhost:8000"
".venv\Scripts\python.exe" -m neurosre.api
echo.
echo NeuroSRE has stopped.
pause
