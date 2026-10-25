"""
Build the QLoRA instruction dataset (teaches tutoring BEHAVIOUR, not textbook content).

Pipeline (proposal section 5.2):
  generate scenarios -> draft replies -> clean -> remove duplicates
  -> remove incorrect/poor replies (automatic checks) -> format for instruction tuning
  -> train/validation split -> human review sheet

Each example uses exactly the prompt format the app sends at runtime, so the model learns
to follow STRATEGY / REVEAL_ANSWER / FACTS blocks.

Where do the replies come from?
  --draft-with MODEL : a model served by Ollama drafts K candidates per prompt; candidates that
                       pass the verifier checks are kept (verifier-filtered self-training: the
                       OS Engine facts make "correct" checkable). Then review a sample by hand.
  (default)          : offline template replies, so the pipeline can run end-to-end without a GPU.
                       These are only a seed and should be replaced by reviewed drafts.

    python -m qlora.build_dataset --n 600
    python -m qlora.build_dataset --n 600 --draft-with llama3.1:8b --candidates 3
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

from rag.store import KnowledgeBase
from qlora.scenarios import make_scenarios
from tutor import prompts
from tutor.llm import OllamaClient

OUT = Path(__file__).resolve().parent / "data"
ASKING = {"START_HINT", "SOCRATIC_HINT", "TARGETED_HINT", "ALGORITHM_REMINDER", "FORMULA_REMINDER", "CONFIRM_AND_EXTEND"}


def quality(text: str, strat) -> tuple[bool, list[str]]:
    reasons = []
    words = len(text.split())
    if words < 12:
        reasons.append("too short")
    if words > 170 and strat.action != "WORKED_EXAMPLE":
        reasons.append("too long")
    for issue in prompts.check_response(text, strat):
        reasons.append(issue["type"])
    if strat.action in ASKING and not strat.reveal and "?" not in text:
        reasons.append("no guiding question")
    return not reasons, reasons


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=600, help="number of scenarios")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--draft-with", default=None, help="Ollama model that drafts replies")
    ap.add_argument("--candidates", type=int, default=3)
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--no-templates", action="store_true", help="drop scenarios with no accepted model draft")
    args = ap.parse_args()

    kb = KnowledgeBase()
    kb.load_or_build()
    client = None
    if args.draft_with:
        client = OllamaClient(model=args.draft_with)
        if not client.available():
            raise SystemExit("Ollama is not running.")
    scenarios = make_scenarios(args.n, args.seed, kb)
    print(f"generated {len(scenarios)} unique scenarios")

    examples, review, rejected = [], [], Counter()
    seen_replies: set[str] = set()
    for i, sc in enumerate(scenarios):
        st = sc["strategy"]
        chosen, source, checks = None, None, []
        if client:
            for _ in range(args.candidates):
                try:
                    cand = client.chat(sc["messages"], options={"temperature": 0.7}).strip()
                except Exception as e:  # keep going on a bad call
                    rejected["llm error"] += 1
                    print("  LLM error:", e)
                    break
                ok, reasons = quality(cand, st)
                if ok:
                    chosen, source = cand, f"draft:{args.draft_with}"
                    break
                rejected.update(reasons)
            if (i + 1) % 25 == 0:
                print(f"  drafted {i + 1}/{len(scenarios)}")
        if chosen is None and not args.no_templates:
            chosen, source = prompts.template_response(st), "template"
        if chosen is None:
            continue
        norm = " ".join(chosen.lower().split())
        if norm in seen_replies:
            rejected["duplicate reply"] += 1
            continue
        seen_replies.add(norm)
        ok, checks = quality(chosen, st)
        examples.append({"messages": sc["messages"] + [{"role": "assistant", "content": chosen}],
                         "meta": {"id": sc["id"], "topic": sc["topic"], "difficulty": sc["difficulty"],
                                  "action": st.action, "reveal": st.reveal, "level": sc["level"],
                                  "answer_type": sc["answer_type"], "source": source}})
        review.append({"id": sc["id"], "action": st.action, "topic": sc["topic"], "source": source,
                       "checks": "ok" if ok else "; ".join(checks), "reply": chosen,
                       "facts": " | ".join(st.facts)[:800], "approved (y/n)": ""})

    # stratified split by action so every strategy appears in validation
    rng = random.Random(args.seed)
    by_action: dict[str, list] = {}
    for ex in examples:
        by_action.setdefault(ex["meta"]["action"], []).append(ex)
    train, val = [], []
    for group in by_action.values():
        rng.shuffle(group)
        k = max(1, round(len(group) * args.val_frac)) if len(group) > 3 else 0
        val += group[:k]
        train += group[k:]
    rng.shuffle(train)

    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train.jsonl", train), ("val.jsonl", val)):
        with open(OUT / name, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT / "review.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(review[0].keys()))
        w.writeheader()
        w.writerows(review)
    stats = {"scenarios": len(scenarios), "examples": len(examples), "train": len(train), "val": len(val),
             "by_action": dict(Counter(e["meta"]["action"] for e in examples)),
             "by_topic": dict(Counter(e["meta"]["topic"] for e in examples)),
             "by_source": dict(Counter(e["meta"]["source"] for e in examples)),
             "rejected_candidates": dict(rejected)}
    (OUT / "stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))
    print(f"wrote {OUT / 'train.jsonl'}, {OUT / 'val.jsonl'} and {OUT / 'review.csv'}")


if __name__ == "__main__":
    main()
