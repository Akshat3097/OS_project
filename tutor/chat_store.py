"""
Saved conversations, one JSON file per chat: data/chats/<student>/<chat id>.json.
Used by both chat interfaces (chat_app.py and the FastAPI server), so a conversation can be continued later.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

import config
from tutor.chat_agent import new_state

CHAT_DIR = config.CHAT_DIR


def slug(sid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", sid.strip())[:40] or "student"


def _dir(sid: str) -> Path:
    return CHAT_DIR / slug(sid)


def _title(state: dict) -> str:
    first = next((m["content"] for m in state.get("messages", []) if m.get("role") == "user" and m.get("content")), "")
    first = " ".join(first.split())
    return (first[:57] + "…") if len(first) > 58 else (first or "New chat")


def new_chat(sid: str) -> dict:
    state = new_state(sid)
    state.update({"id": uuid.uuid4().hex[:12], "created": time.time(), "updated": time.time(), "title": "New chat"})
    return state


def list_chats(sid: str) -> list[dict]:
    out = []
    for p in _dir(sid).glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not any(m.get("role") == "user" for m in d.get("messages", [])):
            continue                                   # never show empty chats
        out.append({"id": d.get("id", p.stem), "title": d.get("title") or _title(d), "updated": d.get("updated", 0)})
    return sorted(out, key=lambda c: -c["updated"])


def load_chat(sid: str, chat_id: str | None = None) -> dict:
    """A saved chat, or the most recent one, or a new one."""
    if chat_id is None:
        chats = list_chats(sid)
        if not chats:
            return new_chat(sid)
        chat_id = chats[0]["id"]
    p = _dir(sid) / f"{re.sub(r'[^a-f0-9]', '', chat_id)}.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, dict) and "messages" in d:
            return {**new_chat(sid), **d, "sid": sid}
    except (OSError, ValueError):
        pass
    return new_chat(sid)


def save_chat(state: dict) -> None:
    state.setdefault("id", uuid.uuid4().hex[:12])
    state["updated"] = time.time()
    state["title"] = _title(state)
    try:
        d = _dir(state["sid"])
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{state['id']}.json").write_text(json.dumps(state, default=str), encoding="utf-8")
    except OSError:
        pass


def delete_chat(sid: str, chat_id: str) -> None:
    p = _dir(sid) / f"{re.sub(r'[^a-f0-9]', '', chat_id)}.json"
    try:
        p.unlink()
    except OSError:
        pass
