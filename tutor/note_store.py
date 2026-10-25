"""
The student's own notes (the Notes tab): one JSON file per student, data/notes/<student>.json.
A note is saved from a tutor reply ("Save to notes") or written by hand; each has a pastel colour like a sticky note.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

import config
from tutor.chat_store import slug

COLORS = ("butter", "peach", "lilac", "sky", "mint")
MAX_TEXT = 8000
MAX_TITLE = 120
_lock = threading.Lock()


def _file(sid: str) -> Path:
    return Path(config.NOTES_DIR) / f"{slug(sid)}.json"


def _read(sid: str) -> list[dict]:
    f = _file(sid)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _write(sid: str, notes: list[dict]) -> None:
    f = _file(sid)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)


def _ordered(notes: list[dict]) -> list[dict]:
    return sorted(notes, key=lambda n: (not n.get("pinned"), -n.get("updated", 0)))


def list_notes(sid: str) -> list[dict]:
    with _lock:
        return _ordered(_read(sid))


def add_note(sid: str, text: str, title: str = "", color: str | None = None, source: str = "") -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("a note needs some text")
    with _lock:
        notes = _read(sid)
        if color not in COLORS:
            color = COLORS[len(notes) % len(COLORS)]
        now = time.time()
        note = {"id": uuid.uuid4().hex[:10], "title": (title or "").strip()[:MAX_TITLE], "text": text[:MAX_TEXT],
                "color": color, "source": (source or "").strip()[:MAX_TITLE], "pinned": False,
                "created": now, "updated": now}
        notes.append(note)
        _write(sid, notes)
        return note


def update_note(sid: str, note_id: str, **changes) -> dict:
    with _lock:
        notes = _read(sid)
        note = next((n for n in notes if n["id"] == note_id), None)
        if note is None:
            raise KeyError(note_id)
        if changes.get("text") is not None:
            text = changes["text"].strip()
            if not text:
                raise ValueError("a note needs some text")
            note["text"] = text[:MAX_TEXT]
        if changes.get("title") is not None:
            note["title"] = changes["title"].strip()[:MAX_TITLE]
        if changes.get("color") in COLORS:
            note["color"] = changes["color"]
        if changes.get("pinned") is not None:
            note["pinned"] = bool(changes["pinned"])
        note["updated"] = time.time()
        _write(sid, notes)
        return note


def delete_note(sid: str, note_id: str) -> None:
    with _lock:
        notes = _read(sid)
        kept = [n for n in notes if n["id"] != note_id]
        if len(kept) == len(notes):
            raise KeyError(note_id)
        _write(sid, kept)
