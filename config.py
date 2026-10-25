"""Central settings. Override with environment variables if needed."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.environ.get("TUTOR_DB", DATA_DIR / "tutor.db"))
CHAT_DIR = Path(os.environ.get("TUTOR_CHAT_DIR", DATA_DIR / "chats"))   # saved conversations, one folder per student
NOTES_DIR = Path(os.environ.get("TUTOR_NOTES_DIR", DATA_DIR / "notes"))  # the student's own notes, one file per student
VIDEO_DIR = Path(os.environ.get("TUTOR_VIDEO_DIR", ROOT / "videos"))     # videos.json + transcripts of YouTube lectures

# Ollama (local LLM server). Separate variable from OLLAMA_HOST on purpose:
# OLLAMA_HOST is the server's bind address and is often "0.0.0.0", which is not a URL a client can call.
# 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 first and adds about 2 s to every call.
OLLAMA_URL = os.environ.get("TUTOR_OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("TUTOR_MODEL", "llama3.1:8b")
EMBED_MODEL = os.environ.get("TUTOR_EMBED_MODEL", "nomic-embed-text")
# num_predict caps a reply (~450 words): with no cap a fine-tuned model that falls into a repetition loop never stops
# (found 23 Oct: "A semaphore is a variable… It is a way to protect shared data…" until the 3-minute timeout).
# Ollama 0.40 runs with repeat_penalty 1.0 unless asked, so ask for a mild one.
LLM_OPTIONS = {"temperature": 0.3, "num_ctx": 4096, "num_predict": 600, "repeat_penalty": 1.1, "repeat_last_n": 256}
KEEP_ALIVE = "30m"   # keep the model on the GPU between replies (Ollama's default unloads it after 5 minutes)
# Judge for "Explain it back": the plain instruct model agreed best with a human examiner on eval/teachback_cases.py
# (eval/results_teachback.md); the chat keeps the fine-tuned os-tutor. Falls back to the chat model if not installed.
JUDGE_MODEL = os.environ.get("TUTOR_JUDGE_MODEL", "llama3.1:8b")

# RAG
KNOWLEDGE_DIR = ROOT / "rag" / "knowledge"   # seed notes shipped with the project
SOURCES_DIR = ROOT / "rag" / "sources"       # put your own PDFs / notes / question papers here
INDEX_DIR = ROOT / "rag" / "index"
TOP_K = 3

# Bayesian Knowledge Tracing parameters (Corbett & Anderson, 1995)
BKT = {"p_init": 0.25, "p_learn": 0.15, "p_slip": 0.10, "p_guess": 0.20}
MASTERY_THRESHOLDS = (0.45, 0.80)   # below first -> easy, below second -> medium, else hard
RECURRING_WINDOW = 8                # look at the last N submissions
RECURRING_MIN = 2                   # same error this many times = recurring misconception

# Speech-to-text for "Explain it back" (optional: pip install faster-whisper)
# small.en: on the laptop plugged in (Turbo) 68 s of speech took 10.8 s and was word-perfect; base.en took 3.6 s but
# heard "burst time" as "first time". On battery small.en is several times slower: set TUTOR_WHISPER_MODEL=base.en.
WHISPER_MODEL = os.environ.get("TUTOR_WHISPER_MODEL", "small.en")     # tiny.en / base.en / small.en
WHISPER_DEVICE = os.environ.get("TUTOR_WHISPER_DEVICE", "cpu")        # "cuda" to use the GPU
