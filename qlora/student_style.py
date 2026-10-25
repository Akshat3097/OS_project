"""
Student-style phrasing for training data v2: rewrite what the student says the way students actually type
("sir pls explain srtf", "whats the wt of p2??", "exam tmrw, rr doubt"), so the fine-tuned model is used to
messy, short, informal questions and not only to clean textbook ones.

Only the prose changes. Numbers, process names (P1, A), acronyms (FCFS, CT) and data lines (tables, P1(0,5),
"P1 0 9 1") are never touched, so the engine-verified answers in the replies stay correct for the new question.
"""
from __future__ import annotations

import random
import re

PREFIXES = ["", "", "", "sir ", "hi, ", "quick doubt: ", "exam tomorrow, ", "pls help - ", "ma'am ", "bro ",
            "CAT doubt: ", "yaar "]
SUFFIXES = ["", "", "", " pls", " asap", " thanks", " (CAT question)", " samjha do", " in simple words"]
SWAPS = [  # (pattern, replacements); applied with some probability each
    (r"\bplease\b", ["pls", "plz"]), (r"\byou\b", ["u"]), (r"\byour\b", ["ur"]), (r"\bwhat is\b", ["whats", "wat is"]),
    (r"\bcan you\b", ["can u", "cn u"]), (r"\bbecause\b", ["bcoz", "cuz"]), (r"\bthe answer\b", ["the ans"]),
    (r"\bi don't\b", ["i dont"]), (r"\bi'm\b", ["im"]), (r"\bisn't\b", ["isnt"]), (r"\bdoesn't\b", ["doesnt"]),
    (r"\balgorithm\b", ["algo"]), (r"\bwaiting time\b", ["WT", "waiting time"]), (r"\bturnaround time\b", ["TAT"]),
    (r"\bcompletion time\b", ["CT"]), (r"\bround robin\b", ["RR", "round robin"]), (r"\bexplain\b", ["explain", "xplain"]),
    (r"\bthanks\b", ["thx", "tnx"]), (r"\btomorrow\b", ["tmrw"]), (r"\bquestion\b", ["qn", "ques"]),
    (r"\bdifference\b", ["diff"]), (r"\band\b", ["n", "and", "and"]),
]
KEEP = re.compile(r"^[A-Z]{1,6}\d*['’]?s?$|\d|^[A-Z]$")       # acronyms, ids, anything with a digit
DATA_LINE = re.compile(r"^\s*(P\d+|[A-E])\b[^a-z]*$|^\s*P\d+\s*[:(]", re.I)      # table rows, "P1: CT 9, ..." answers


def _typo(word: str, rng: random.Random) -> str:
    i = rng.randrange(1, len(word) - 2)
    return word[:i] + word[i + 1] + word[i] + word[i + 2:]


def _prose(line: str, rng: random.Random) -> str:
    for pat, reps in SWAPS:
        if rng.random() < 0.7:
            line = re.sub(pat, lambda m: rng.choice(reps), line, flags=re.I)
    words = line.split(" ")
    out = []
    typo_done = rng.random() > 0.35                 # about one message in three gets a typo
    for w in words:
        if KEEP.search(re.sub(r"[^\w'’]", "", w)) or "(" in w or ")" in w:
            out.append(w)
            continue
        w = w.lower()
        core = re.sub(r"\W", "", w)
        if not typo_done and len(core) >= 6 and core == w:
            w, typo_done = _typo(w, rng), True
        out.append(w)
    line = " ".join(out)
    if rng.random() < 0.5:
        line = line.rstrip(".")
    if line.endswith("?") and rng.random() < 0.3:
        line = line.rstrip("?") + rng.choice(["", "??", " ?"])
    return line


def studentify(text: str, rng: random.Random, first: bool = True) -> str:
    lines = text.split("\n")
    lines = [ln if DATA_LINE.search(ln) else _prose(ln, rng) for ln in lines]
    out = "\n".join(lines).strip()
    if first:
        out = rng.choice(PREFIXES) + out
        if "\n" not in out:
            out += rng.choice(SUFFIXES)
    return out or text


def student_variants(examples: list[dict], rng: random.Random, frac: float) -> list[dict]:
    """A student-style copy of a random `frac` of the examples (every user turn rewritten, replies unchanged)."""
    out = []
    for ex in examples:
        if rng.random() >= frac or ex.get("kind") == "handwritten":
            continue
        msgs, n_user = [], 0
        for m in ex["messages"]:
            if m["role"] == "user":
                msgs.append({"role": "user", "content": studentify(m["content"], rng, first=n_user == 0)})
                n_user += 1
            else:
                msgs.append(dict(m))
        out.append({"kind": ex["kind"] + "_student", "messages": msgs})
    return out
