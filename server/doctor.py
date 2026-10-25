"""
Check that everything the OS Tutor needs is in place, fix what can be fixed, and get Ollama ready for the first reply.

    python -m server.doctor            check only
    python -m server.doctor --fix      also build the notes index, start Ollama, pull missing models, create
                                       os-tutor-prompt / os-tutor, download the speech model (used by setup.bat)
    python -m server.doctor --start    quick: start Ollama if needed and load the tutor model on the GPU (used by start.bat)
"""
from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import config

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ["fastapi", "uvicorn", "requests", "pydantic", "pypdf"]
CHAT_MODELS = ("os-tutor", "os-tutor-prompt", "llama3.1:8b")
ok_count = {"ok": 0, "warn": 0, "bad": 0}


def say(kind: str, text: str, fix: str = "") -> None:
    ok_count[kind] += 1
    mark = {"ok": "[ ok ]", "warn": "[note]", "bad": "[FAIL]"}[kind]
    print(f"  {mark} {text}" + (f"\n         -> {fix}" if fix else ""))


def ollama_models() -> list[str] | None:
    import requests
    try:
        r = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=3)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return None


def has(models: list[str], name: str) -> bool:
    return any(m == name or m.split(":")[0] == name.split(":")[0] for m in models)


def start_ollama(wait: float = 20) -> list[str] | None:
    """Start the Ollama server in the background if it is installed but not running."""
    exe = shutil.which("ollama")
    if not exe:
        return None
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    config.DATA_DIR.mkdir(exist_ok=True)
    log = open(config.DATA_DIR / "ollama.log", "ab")       # kept so a hang can be looked into afterwards
    subprocess.Popen([exe, "serve"], stdout=log, stderr=log, creationflags=flags)
    t0 = time.time()
    while time.time() - t0 < wait:
        models = ollama_models()
        if models is not None:
            return models
        time.sleep(1)
    return None


def warm(model: str) -> bool:
    """Load the model into GPU memory and keep it there for an hour, so the first reply in the demo is quick."""
    import requests
    try:
        requests.post(f"{config.OLLAMA_URL}/api/generate", json={"model": model, "keep_alive": "60m"}, timeout=180)
        return True
    except Exception:
        return False


def preferred_chat_model(models: list[str]) -> str | None:
    return next((m for name in CHAT_MODELS for m in models if has([m], name)), None)


def run(fix: bool) -> int:
    print("\nOS Tutor check\n")
    # ---------------------------------------------------------------- Python and packages
    v = sys.version_info
    say("ok" if v >= (3, 10) else "bad", f"Python {v.major}.{v.minor}", "" if v >= (3, 10) else "Install Python 3.11 or 3.12")
    missing = [m for m in REQUIRED if importlib.util.find_spec(m) is None]
    say("bad" if missing else "ok", "Python packages" + (f": missing {', '.join(missing)}" if missing else ""),
        "Run setup.bat (or: .venv\\Scripts\\python -m pip install -r requirements.txt)" if missing else "")
    if missing:
        return 1
    # ---------------------------------------------------------------- the web page and the notes
    dist = ROOT / "web" / "dist" / "index.html"
    say("ok" if dist.exists() else "bad", "Web page (web/dist)", "" if dist.exists() else "cd web, npm install, npm run build")
    index = ROOT / "rag" / "index" / "chunks.json"
    if not index.exists() and fix:
        from rag.store import KnowledgeBase
        print("         building the notes index...")
        for _ in KnowledgeBase().build():
            pass
    say("ok" if index.exists() else "warn", "Notes index (rag/index)",
        "" if index.exists() else "It is built automatically when the app starts (a few seconds)")
    # ---------------------------------------------------------------- Ollama and the models
    models = ollama_models()
    if models is None and fix:
        print("         Ollama is not running; starting it...")
        models = start_ollama()
    if models is None:
        say("warn", "Ollama is not running: replies will use templates (every number is still checked by the engine)",
            "Start the Ollama app, or install it from https://ollama.com")
    else:
        say("ok", f"Ollama is running ({len(models)} models)")
        if fix:
            for name in ("llama3.1:8b", "nomic-embed-text"):
                if not has(models, name):
                    print(f"         pulling {name} (a few GB the first time)...")
                    subprocess.run(["ollama", "pull", name])
            models = ollama_models() or models
            if has(models, "llama3.1:8b") and not has(models, "os-tutor-prompt"):
                subprocess.run(["ollama", "create", "os-tutor-prompt", "-f", str(ROOT / "qlora" / "Modelfile.prompt")])
            if not has(models, "os-tutor") and (ROOT / "qlora" / "os-tutor.gguf").exists():
                subprocess.run([sys.executable, "-m", "qlora.create_finetuned"], cwd=ROOT)
            if not has(models, "os-tutor-v2") and (ROOT / "qlora" / "os-tutor-v2.gguf").exists():
                subprocess.run([sys.executable, "-m", "qlora.create_finetuned", "--name", "os-tutor-v2"], cwd=ROOT)
            models = ollama_models() or models
        chat = preferred_chat_model(models)
        say("ok" if has(models, "os-tutor") else "warn" if chat else "bad",
            f"Tutor model: {chat or 'none'}",
            "" if has(models, "os-tutor") else
            "Save os-tutor.gguf from Google Drive as qlora\\os-tutor.gguf and run setup.bat again" if chat else
            "Run setup.bat (it pulls llama3.1:8b)")
    # ---------------------------------------------------------------- speech to text
    from tutor import speech
    if not speech.available():
        say("warn", "Microphone transcription (faster-whisper) is not installed: typing and Win + H still work",
            ".venv\\Scripts\\python -m pip install faster-whisper")
    else:
        SIZE = {"tiny.en": "about 75 MB", "base.en": "about 150 MB", "small.en": "about 460 MB"}
        try:
            from huggingface_hub import try_to_load_from_cache
            cached = try_to_load_from_cache(f"Systran/faster-whisper-{config.WHISPER_MODEL}", "model.bin") not in (None,)
        except Exception:
            cached = False
        if not cached and fix:
            print(f"         downloading the speech model ({config.WHISPER_MODEL}, {SIZE.get(config.WHISPER_MODEL, 'a few hundred MB')})...")
            try:
                speech._load()
                cached = True
            except Exception as e:
                print(f"         download failed: {e}")
        say("ok" if cached else "warn", f"Microphone transcription (faster-whisper, {config.WHISPER_MODEL})",
            "" if cached else "The first recording downloads the speech model first; run setup.bat to do it now")
    print(f"\n  {ok_count['ok']} ok, {ok_count['warn']} notes, {ok_count['bad']} problems\n")
    return 1 if ok_count["bad"] else 0


def quick_start() -> None:
    """For start.bat: make sure Ollama runs, then load the tutor model in the background while the server starts."""
    models = ollama_models()
    if models is None:
        print("  Starting Ollama...")
        models = start_ollama()
    if models is None:
        print("  Ollama is not available: the tutor will use template replies (the engine still checks every number).")
        return
    chat = preferred_chat_model(models)
    if chat:
        print(f"  Loading {chat} on the GPU in the background...")
        threading.Thread(target=warm, args=(chat,), daemon=False).start()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--start", action="store_true")
    args = ap.parse_args()
    if args.start:
        quick_start()
        return
    sys.exit(run(args.fix))


if __name__ == "__main__":
    main()
