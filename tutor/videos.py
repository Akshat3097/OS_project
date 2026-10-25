"""
Lecture clips: the part of a YouTube lecture that explains a lesson's topic, cued to the right seconds.

videos/videos.json lists the lectures:

    [{"url": "https://www.youtube.com/watch?v=XXXXXXXXXXX", "title": "CPU scheduling, lecture 1",
      "transcript": "lecture1.txt",
      "clips": [{"lesson": "srtf", "start": "3:10", "end": "5:40"}]}]      <- optional: pinned by hand, always wins

A pinned clip with no "end" plays to the end of the video (used when there is no transcript); its "chapters"
([{"start": "2:11", "label": ...}], approximate section times) are shown as buttons to jump to. "auto": false keeps
a lecture to its pinned clips (a talk on another topic that only mentions "priority" or "producer").
A clip's "lesson" can also be a topic outside the lessons ("fork", "ipc"): tutor/faq.py names those.

A transcript can be pasted from YouTube's "Show transcript" panel (a time, then the words), or be an .srt / .vtt file.
It is cut into segments of about a minute, each segment is tagged with the lesson whose words it uses most, and the
best continuous stretch for each lesson (at most four minutes) becomes its clip.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import config

SEGMENT = 60          # seconds per segment
MAX_CLIP = 240        # longest clip
MIN_SCORE = 2         # topic words a segment needs before it counts for a lesson

# words that show a lecture is on a lesson's topic (lower case; matched as whole words or phrases)
TOPIC_WORDS: dict[str, list[str]] = {
    "basics": ["turnaround", "waiting time", "completion time", "response time", "gantt", "burst time", "arrival time",
               "cpu scheduler", "scheduling criteria", "throughput", "cpu utilization", "cpu utilisation"],
    "fcfs": ["fcfs", "first come first serve", "first come first served", "first-come", "convoy"],
    "sjf": ["sjf", "shortest job", "shortest job first", "next cpu burst"],
    "srtf": ["srtf", "shortest remaining", "remaining time", "preemptive sjf", "preempt"],
    "rr": ["round robin", "time quantum", "quantum", "time slice", "ready queue"],
    "priority": ["priority", "aging", "ageing", "starvation", "lower number"],
    "critical_section": ["critical section", "race condition", "mutual exclusion", "bounded waiting",
                         "peterson", "entry section", "exit section"],
    "semaphores": ["semaphore", "semaphores", "wait operation", "signal operation", "binary semaphore",
                   "counting semaphore", "p operation", "v operation"],
    "bounded_buffer": ["producer", "consumer", "bounded buffer", "bounded-buffer", "buffer is full", "buffer is empty"],
    "readers_writers": ["reader", "readers", "writer", "writers", "readcount", "read count"],
    "dining": ["philosopher", "philosophers", "chopstick", "chopsticks", "dining"],
    "deadlock": ["deadlock", "deadlocks", "circular wait", "hold and wait", "no preemption", "resource allocation graph",
                 "wait-for graph", "wait for graph"],
    "bankers": ["banker", "bankers", "safe state", "safe sequence", "unsafe state", "need matrix", "max matrix",
                "allocation matrix", "available vector"],
}


def video_id(url: str) -> str | None:
    m = re.search(r"(?:youtu\.be/|[?&]v=|/embed/|/shorts/|/live/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else (url if re.fullmatch(r"[A-Za-z0-9_-]{11}", url or "") else None)


def seconds(t: str | int | float) -> int:
    """"3:10" → 190, "1:02:03" → 3723, "00:01:04,500" → 64, 75 → 75."""
    if isinstance(t, (int, float)):
        return int(t)
    parts = [float(p.replace(",", ".")) for p in str(t).strip().split(":")]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return int(total)


def clock(s: int) -> str:
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


_TIME = r"(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?"


def parse_transcript(text: str) -> list[tuple[int, str]]:
    """(start second, words) for each line of a YouTube transcript, an .srt or a .vtt file."""
    lines = [ln.strip() for ln in text.replace("﻿", "").splitlines()]
    out: list[tuple[int, str]] = []
    if any("-->" in ln for ln in lines):                                   # SRT / VTT cues
        start, words = None, []
        for ln in lines + [""]:
            m = re.match(rf"({_TIME})\s*-->", ln)
            if m:
                start, words = seconds(m.group(1)), []
            elif ln and start is not None and not ln.isdigit() and not ln.upper().startswith("WEBVTT"):
                words.append(re.sub(r"<[^>]+>", "", ln))
            elif not ln and start is not None and words:
                out.append((start, " ".join(words)))
                start, words = None, []
        return _dedupe(out)
    pending = None                                                        # "Show transcript": time then words
    for ln in lines:
        if not ln:
            continue
        m = re.fullmatch(rf"({_TIME})\s*(.*)", ln)
        if m:
            if m.group(2):
                out.append((seconds(m.group(1)), m.group(2)))
                pending = None
            else:
                pending = seconds(m.group(1))
        elif pending is not None:
            out.append((pending, ln))
            pending = None
        elif out:                                                         # a wrapped line belongs to the last time
            out[-1] = (out[-1][0], out[-1][1] + " " + ln)
    return _dedupe(out)


def _dedupe(rows: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Auto-generated captions repeat each line in the next cue; keep the words once."""
    out: list[tuple[int, str]] = []
    for t, words in rows:
        if out and words.startswith(out[-1][1]):
            words = words[len(out[-1][1]):].strip()
        if words:
            out.append((t, words))
    return out


def topic_score(text: str) -> dict[str, int]:
    low = " " + re.sub(r"[^a-z0-9()' -]+", " ", text.lower()) + " "
    scores = {}
    for lid, words in TOPIC_WORDS.items():
        n = sum(len(re.findall(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low)) for w in words)
        if n:
            scores[lid] = n
    return scores


def segments(rows: list[tuple[int, str]], end_time: int | None = None) -> list[dict]:
    """About a minute each: start, end, words, and the lesson it is about (None when no topic stands out)."""
    out, cur = [], []
    for i, (t, words) in enumerate(rows):
        cur.append((t, words))
        nxt = rows[i + 1][0] if i + 1 < len(rows) else (end_time or t + 10)
        if nxt - cur[0][0] >= SEGMENT or i + 1 == len(rows):
            text = " ".join(w for _, w in cur)
            sc = topic_score(text)
            best = max(sc, key=sc.get) if sc else None
            out.append({"start": cur[0][0], "end": nxt, "text": text,
                        "lesson": best if best and sc[best] >= MIN_SCORE else None, "score": sc.get(best, 0) if best else 0})
            cur = []
    return out


def auto_clips(video: dict, segs: list[dict]) -> list[dict]:
    """For each lesson, its best continuous run of segments, trimmed to MAX_CLIP around the strongest part."""
    clips = []
    runs: list[list[dict]] = []
    for s in segs:
        if s["lesson"] and runs and runs[-1][-1]["lesson"] == s["lesson"] and runs[-1][-1]["end"] >= s["start"] - 1:
            runs[-1].append(s)
        elif s["lesson"]:
            runs.append([s])
    best: dict[str, list[dict]] = {}
    for run in runs:
        lid = run[0]["lesson"]
        if lid not in best or sum(x["score"] for x in run) > sum(x["score"] for x in best[lid]):
            best[lid] = run
    for lid, run in best.items():
        while run[-1]["end"] - run[0]["start"] > MAX_CLIP and len(run) > 1:   # drop the weaker end
            run = run[1:] if run[0]["score"] <= run[-1]["score"] else run[:-1]
        clips.append(_clip(video, lid, run[0]["start"], min(run[-1]["end"], run[0]["start"] + MAX_CLIP),
                           " ".join(x["text"] for x in run), "auto", sum(x["score"] for x in run)))
    return clips


def _clip(video: dict, lid: str, start: int, end: int | None, text: str, how: str, score: int) -> dict:
    words = text.split()
    when = f"{clock(start)}–{clock(end)}" if end is not None else ("whole video" if start == 0 else f"from {clock(start)}")
    return {"lesson": lid, "video": video["id"], "title": video.get("title") or "Lecture", "start": start, "end": end,
            "when": when, "excerpt": " ".join(words[:70]) + (" …" if len(words) > 70 else ""),
            "how": how, "score": score,
            # section times from notes on the lecture, not from a transcript: approximate, so offered as jump buttons
            "chapters": [{"start": seconds(c["start"]), "label": c["label"]} for c in video.get("chapters") or []]
            if end is None and start == 0 else []}


_cache: dict = {"key": None, "clips": []}


def load(folder: Path | None = None) -> list[dict]:
    """Every clip from videos/videos.json, re-read when the folder changes."""
    folder = Path(folder or config.VIDEO_DIR)
    manifest = folder / "videos.json"
    if not manifest.exists():
        return []
    key = tuple(sorted((p.name, p.stat().st_mtime) for p in folder.iterdir() if p.is_file()))
    if _cache["key"] == (str(folder), key):
        return _cache["clips"]
    clips: list[dict] = []
    for v in json.loads(manifest.read_text(encoding="utf-8")):
        vid = video_id(v.get("url") or v.get("id") or "")
        if not vid:
            continue
        video = {**v, "id": vid}
        rows: list[tuple[int, str]] = []
        if v.get("transcript") and (folder / v["transcript"]).exists():
            rows = parse_transcript((folder / v["transcript"]).read_text(encoding="utf-8", errors="replace"))
        pinned = []
        for c in v.get("clips") or []:
            s, e = seconds(c.get("start", 0)), (seconds(c["end"]) if c.get("end") else None)
            said = " ".join(w for t, w in rows if s <= t and (e is None or t < e))
            pinned.append(_clip(video, c["lesson"], s, e, said, "pinned", 10**6))
        auto = auto_clips(video, segments(rows)) if rows and v.get("auto", True) else []
        clips += pinned + [c for c in auto if c["lesson"] not in {p["lesson"] for p in pinned}]
    _cache.update(key=(str(folder), key), clips=clips)
    return clips


def clips_for(lesson: str, folder: Path | None = None, limit: int = 2) -> list[dict]:
    """The best clips for a lesson: pinned ones first, then the strongest automatic matches."""
    return sorted((c for c in load(folder) if c["lesson"] == lesson), key=lambda c: -c["score"])[:limit]
