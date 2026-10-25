"""
Show, in the terminal, how the customized tutor answers compared with the plain base model.

    python -m qlora.compare                                   # runs the prompts in qlora/demo_prompts.txt
    python -m qlora.compare "Explain SRTF with an example"    # one prompt
    python -m qlora.compare --chat --models os-tutor          # free chat with one model (type 'exit' to stop)
    python -m qlora.compare --models llama3.1:8b os-tutor-prompt os-tutor

Each answer streams live under a coloured header with the model name and its speed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = os.environ.get("TUTOR_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
HERE = Path(__file__).resolve().parent
COLOURS = ["\033[96m", "\033[93m", "\033[92m", "\033[95m"]
BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
BLURB = {"llama3.1:8b": "base model, no customization", "os-tutor-prompt": "customized with instructions + examples",
         "os-tutor": "fine-tuned with QLoRA"}


def _installed() -> list[str]:
    with urllib.request.urlopen(f"{URL}/api/tags", timeout=5) as r:
        return [m["name"] for m in json.load(r).get("models", [])]


def _has(name: str, installed: list[str]) -> bool:
    return any(m == name or m == f"{name}:latest" or m.split(":")[0] == name for m in installed)


def stream(model: str, messages: list[dict], out=sys.stdout) -> tuple[str, float, int]:
    body = json.dumps({"model": model, "messages": messages, "stream": True}).encode()
    req = urllib.request.Request(f"{URL}/api/chat", data=body, headers={"Content-Type": "application/json"})
    text, t0, tokens = [], time.time(), 0
    with urllib.request.urlopen(req, timeout=600) as r:
        for line in r:
            if not line.strip():
                continue
            chunk = json.loads(line)
            piece = chunk.get("message", {}).get("content", "")
            if piece:
                text.append(piece)
                out.write(piece)
                out.flush()
            if chunk.get("done"):
                tokens = chunk.get("eval_count", 0)
    return "".join(text), time.time() - t0, tokens


def header(i: int, model: str) -> None:
    c = COLOURS[i % len(COLOURS)]
    print(f"\n{c}{BOLD}━━ {model}{RESET}{DIM}  {BLURB.get(model, '')}{RESET}")


def run_prompts(models: list[str], prompts: list[str]) -> None:
    for n, p in enumerate(prompts, 1):
        print(f"\n{BOLD}▶ Prompt {n}/{len(prompts)}:{RESET} {p}")
        for i, m in enumerate(models):
            header(i, m)
            _, secs, toks = stream(m, [{"role": "user", "content": p}])
            print(f"\n{DIM}   {secs:.1f}s" + (f" · {toks / secs:.0f} tokens/s" if toks and secs else "") + RESET)
        if n < len(prompts):
            input(f"\n{DIM}Press Enter for the next prompt…{RESET}")


def chat(model: str) -> None:
    history: list[dict] = []
    print(f"{BOLD}Chatting with {model}{RESET} {DIM}(type 'exit' to stop, 'reset' to clear the conversation){RESET}")
    while True:
        try:
            q = input(f"\n{BOLD}You ›{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ("exit", "quit"):
            break
        if q.lower() == "reset":
            history = []
            print(f"{DIM}(conversation cleared){RESET}")
            continue
        if not q:
            continue
        history.append({"role": "user", "content": q})
        header(0, model)
        reply, _, _ = stream(model, history)
        history.append({"role": "assistant", "content": reply})
        print()


def main() -> None:
    if os.name == "nt":
        os.system("")                      # turns on colour support in the Windows terminal
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prompt", nargs="*", help="prompt to send (default: qlora/demo_prompts.txt)")
    ap.add_argument("--models", nargs="+", default=None)
    ap.add_argument("--chat", action="store_true", help="interactive chat with the first model")
    args = ap.parse_args()
    try:
        installed = _installed()
    except (urllib.error.URLError, OSError):
        raise SystemExit(f"Ollama is not reachable at {URL}. Start the Ollama app (or run 'ollama serve').")
    models = args.models or [m for m in ("llama3.1:8b", "os-tutor-prompt", "os-tutor") if _has(m, installed)]
    missing = [m for m in models if not _has(m, installed)]
    if missing:
        raise SystemExit(f"Not installed in Ollama: {', '.join(missing)}. See qlora/setup_ollama_models.bat.")
    if args.chat:
        chat(models[-1] if not args.models else models[0])
        return
    prompts = [" ".join(args.prompt)] if args.prompt else \
        [l.strip() for l in (HERE / "demo_prompts.txt").read_text(encoding="utf-8").splitlines()
         if l.strip() and not l.startswith("#")]
    run_prompts(models, prompts)


if __name__ == "__main__":
    main()
