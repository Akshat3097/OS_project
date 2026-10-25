@echo off
REM One-click start for Windows: the original tabbed interface
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  call .venv\Scripts\activate
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate
)
if not exist rag\index\chunks.json python -m rag.ingest
streamlit run app.py
