"""
Check the examples NotebookLM wrote (qlora/notebooklm_pack.py has the prompt) and turn them into chat training data.

    python -m qlora.import_notebooklm pasted\\*.txt          → qlora/data/notebooklm.jsonl, and a report

Paste each NotebookLM answer into a text file (one per topic is easiest). Lines that are not JSON are skipped.
An example is dropped when it is too short or long, repeats another one, contains a new numerical example, or says one
of the things this course marks wrong (an unsafe state is a deadlock, Round Robin starves processes, ...).
Read the sample the report prints before training: a wrong reply that passed these checks is still wrong.
Then: python -m qlora.build_chat_dataset --extra qlora/data/notebooklm.jsonl --out qlora/data/v3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

from qlora.chat_style import CHAT_SYSTEM

OUT = Path(__file__).resolve().parent / "data" / "notebooklm.jsonl"

# claims the course marks wrong (see rag/sources/notes_conventions_checked.md and tutor/faq.py)
WRONG = [
    (r"unsafe state (is|means|=) (a |already )?deadlock", "unsafe state = deadlock"),
    (r"round robin (can |will |does )?(cause|lead to|suffer from)s? starvation", "RR starves"),
    (r"(lower|smaller) (priority )?number (means|=|is) (a )?lower priority", "priority number backwards"),
    (r"higher (priority )?number (means|=|is) (a )?higher priority", "priority number backwards"),
    (r"preempted process (joins|goes|is placed)[^.]{0,30}before[^.]{0,30}(new|arriv)", "RR queue order"),
    (r"(a )?cycle (always )?(means|implies|guarantees) (a )?deadlock(?![^.]{0,40}single)", "cycle = deadlock"),
    (r"safe sequence is (always )?unique", "unique safe sequence"),
    (r"wt\s*=\s*ct\s*[-−]\s*at\b", "WT formula"),
    (r"here'?s a hint", "hint template"),
]
WRONG = [(re.compile(p, re.I), why) for p, why in WRONG]
# a made-up numerical example: process tables, Gantt charts, matrices
NUMERIC = re.compile(r"\bP\d\b[^.\n]{0,25}\b\d+\b[^.\n]{0,25}\bP\d\b[^.\n]{0,25}\b\d+\b|\|\s*\d+\s*\|\s*\d+\s*\||"
                     r"\b\d+\s*[-–]\s*\d+\b[^.\n]{0,15}\b\d+\s*[-–]\s*\d+\b", re.I)


def rows(paths: list[Path]):
    for path in paths:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip().strip(",")
            if not line.startswith("{"):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                yield None, "not valid JSON"
                continue
            yield d, None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    kept, dropped, seen = [], Counter(), set()
    for d, err in rows(a.files):
        if err:
            dropped[err] += 1
            continue
        user, reply = str(d.get("user", "")).strip(), str(d.get("assistant", "")).strip()
        words = len(reply.split())
        why = None
        if not user or not reply:
            why = "empty"
        elif not 30 <= words <= 260:
            why = "too short or long"
        elif NUMERIC.search(reply):
            why = "made-up numerical example"
        else:
            why = next((w for rx, w in WRONG if rx.search(reply)), None)
        key = hashlib.sha1(re.sub(r"\W+", " ", user.lower()).encode()).hexdigest()
        if why is None and key in seen:
            why = "duplicate question"
        if why:
            dropped[why] += 1
            continue
        seen.add(key)
        kept.append({"kind": "notebooklm", "topic": d.get("topic", ""),
                     "messages": [{"role": "system", "content": CHAT_SYSTEM}, {"role": "user", "content": user},
                                  {"role": "assistant", "content": reply}]})
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in kept)
    print(f"kept {len(kept)}, dropped {sum(dropped.values())}: {dict(dropped)}")
    print("by topic:", dict(Counter(r["topic"] for r in kept)))
    print(f"wrote {a.out}\n\nRead these before training:\n")
    for r in random.Random(1).sample(kept, min(8, len(kept))):
        print(f"> {r['messages'][1]['content']}\n{r['messages'][2]['content']}\n")


if __name__ == "__main__":
    main()
