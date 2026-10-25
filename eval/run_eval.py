"""
Automatic evaluation of the LLM side of the tutor (proposal section 7, ablation ladder).

Runs the SAME held-out tutoring scenarios through several model variants and measures
what can be checked automatically thanks to the OS Engine:

  leak_rate          replies that reveal a hidden answer when REVEAL_ANSWER = no (lower is better)
  unverified_nums    replies containing numbers that are not in the engine facts (hallucination proxy)
  asks_question      hint replies that end with a guiding question (instruction following)
  within_length      replies within the 120-word budget (WORKED_EXAMPLE allowed longer)
  latency_s          average seconds per reply

    python -m eval.run_eval --models llama3.1:8b --n 60
    python -m eval.run_eval --models llama3.1:8b os-tutor gemma3:4b --n 60
    python -m eval.run_eval --models llama3.1:8b --no-rag      # Llama vs Llama + RAG

Learning gains (pre-test / post-test with students) are measured separately.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from qlora.scenarios import make_scenarios
from rag.store import KnowledgeBase
from tutor import prompts
from tutor.llm import OllamaClient

OUT = Path(__file__).resolve().parent / "results"
HINTS = {"START_HINT", "SOCRATIC_HINT", "TARGETED_HINT", "ALGORITHM_REMINDER", "FORMULA_REMINDER"}


def score(text: str, st) -> dict:
    issues = prompts.check_response(text, st)
    words = len(text.split())
    return {
        "leak": any(i["type"] == "revealed_answer" for i in issues) if not st.reveal else None,
        "unverified": any(i["type"] == "unverified_number" for i in issues),
        "asks_question": ("?" in text) if (st.action in HINTS and not st.reveal) else None,
        "within_length": words <= (220 if st.action == "WORKED_EXAMPLE" else 140),
        "words": words,
    }


def summarise(rows: list[dict]) -> dict:
    def rate(key):
        vals = [r[key] for r in rows if r[key] is not None]
        return round(100 * sum(vals) / len(vals), 1) if vals else None
    lat = [r["latency"] for r in rows if r["latency"] is not None]
    return {"n": len(rows), "leak_rate_%": rate("leak"), "unverified_nums_%": rate("unverified"),
            "asks_question_%": rate("asks_question"), "within_length_%": rate("within_length"),
            "avg_words": round(sum(r["words"] for r in rows) / len(rows), 1),
            "latency_s": round(sum(lat) / len(lat), 2) if lat else None}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", default=["llama3.1:8b"])
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=999, help="different from the training seed")
    ap.add_argument("--no-rag", action="store_true", help="send prompts without course notes")
    ap.add_argument("--include-template", action="store_true", help="also score the offline template baseline")
    args = ap.parse_args()

    kb = None
    if not args.no_rag:
        kb = KnowledgeBase()
        kb.load_or_build()
    scenarios = make_scenarios(args.n, args.seed, kb)
    variants = (["template"] if args.include_template else []) + args.models
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    all_rows, summary = [], {}
    for v in variants:
        rows = []
        client = None if v == "template" else OllamaClient(model=v)
        if client and not client.available():
            raise SystemExit("Ollama is not running.")
        for i, sc in enumerate(scenarios):
            st = sc["strategy"]
            t0 = time.time()
            text = prompts.template_response(st) if client is None else client.chat(sc["messages"]).strip()
            lat = None if client is None else time.time() - t0
            r = {"variant": v + ("" if not args.no_rag else " (no RAG)"), "id": sc["id"], "action": st.action,
                 "topic": sc["topic"], "reveal": st.reveal, "latency": lat, **score(text, st), "reply": text}
            rows.append(r)
            if client and (i + 1) % 10 == 0:
                print(f"  {v}: {i + 1}/{len(scenarios)}")
        summary[r["variant"]] = summarise(rows)
        all_rows += rows
    with open(OUT / f"eval-{stamp}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)
    (OUT / f"summary-{stamp}.json").write_text(json.dumps(summary, indent=2))
    cols = list(next(iter(summary.values())).keys())
    print("\n| variant | " + " | ".join(cols) + " |\n|---|" + "---|" * len(cols))
    for k, s in summary.items():
        print(f"| {k} | " + " | ".join(str(s[c]) for c in cols) + " |")
    print(f"\nPer-reply results: {OUT / f'eval-{stamp}.csv'}")


if __name__ == "__main__":
    main()
