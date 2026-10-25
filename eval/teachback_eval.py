"""
How well does each teach-back judge agree with a fair examiner? Scores every judge on eval/teachback_cases.py.

    python -m eval.teachback_eval                       keyword rubric + every installed judge model
    python -m eval.teachback_eval --models os-tutor     only these

For every case and idea, "credited" means clear or partial. A judge should credit the ideas the student stated
("yes") and nothing else; borderline ideas ("either") are not scored. Writes eval/results_teachback.md.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from eval.teachback_cases import CASES
from tutor import lessons as L
from tutor import teachback as TB
from tutor.llm import OllamaClient

OUT = Path(__file__).resolve().parent


def score(judged: list[dict]) -> dict:
    """judged: [{"case": ..., "a": assessment}] → agreement, false credits, misses, misconceptions found."""
    s = Counter()
    false_by_kind = Counter()
    for j in judged:
        case, a = j["case"], j["a"]
        either = case.get("either", set())
        for idea in L.LESSON_BY_ID[case["lesson"]]["ideas"]:
            k = idea["id"]
            if k in either:
                continue
            credited = a["ideas"][k] != "missing"
            should = k in case["yes"]
            s["decisions"] += 1
            s["agree"] += credited == should
            if should:
                s["should"] += 1
                s["missed"] += not credited
            else:
                s["should_not"] += 1
                s["false_credit"] += credited
                false_by_kind[case["kind"]] += credited
        exp, got = case.get("mis", set()), set(a.get("misconceptions", []))
        s["mis_expected"] += len(exp)
        s["mis_found"] += len(exp & got)
        s["mis_false"] += len(got - exp)
    s["false_by_kind"] = dict(false_by_kind)
    return s


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f}% ({a}/{b})" if b else "–"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--evidence-only", action="store_true", help="skip the ratings-only judges")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    probe = OllamaClient()
    installed = probe.list_models()
    models = args.models or [m for m in ("os-tutor", "llama3.1:8b") if any(i.split(":")[0] == m.split(":")[0] for i in installed)]
    print(f"{len(CASES)} labelled explanations; judges: keyword rubric + {', '.join(models) or 'none (Ollama offline)'}")

    rows = []
    kw = [{"case": c, "a": TB.combine(TB.keyword_assess(L.LESSON_BY_ID[c["lesson"]], c["text"]), None)} for c in CASES]
    rows.append(("Keyword rubric (offline)", score(kw), 0.0))
    for model in models:
        client = OllamaClient(model=model)
        for evidence in ((True,) if args.evidence_only else (False, True)):
            raw, t0 = [], time.time()
            for n, c in enumerate(CASES, 1):
                lesson = L.LESSON_BY_ID[c["lesson"]]
                raw.append((c, TB.keyword_assess(lesson, c["text"]), TB.llm_assess(client, lesson, c["text"], evidence)))
                print(f"  {model} {'evidence' if evidence else 'plain   '} {n}/{len(CASES)}", end="\r")
            secs = (time.time() - t0) / len(CASES)
            failed = sum(r is None for _, _, r in raw)
            name = f"{model}, {'evidence quotes checked' if evidence else 'ratings only'}"
            for cap in (False, True):
                judged = [{"case": c, "a": TB.combine(k, r, cap)} for c, k, r in raw]
                label = name + (" + keyword cap" if cap else "") + (f" ({failed} unreadable replies)" if failed else "")
                rows.append((label, score(judged), secs))
        print()

    head = ("| Judge | Agrees with the examiner | Credits what was NOT said | Misses what WAS said | "
            "Wrong beliefs caught | Wrong beliefs invented | s / explanation |\n|---|---|---|---|---|---|---|")
    lines = [f"| {name} | {pct(s['agree'], s['decisions'])} | {pct(s['false_credit'], s['should_not'])} | "
             f"{pct(s['missed'], s['should'])} | {pct(s['mis_found'], s['mis_expected'])} | {s['mis_false']} | "
             f"{secs:.1f} |" for name, s, secs in rows]
    kinds = Counter(c["kind"] for c in CASES)
    notes = ["", f"{len(CASES)} explanations: " + ", ".join(f"{n} {k}" for k, n in kinds.items()) + ".",
             "False credits by kind of explanation:"]
    notes += [f"- {name}: " + (", ".join(f"{k} {v}" for k, v in s["false_by_kind"].items() if v) or "none")
              for name, s, _ in rows]
    report = "\n".join([head, *lines, *notes])
    print(report)
    (OUT / "results_teachback.md").write_text(report + "\n", encoding="utf-8")
    (OUT / "results_teachback.json").write_text(json.dumps(
        [{"judge": n, **{k: v for k, v in s.items()}, "seconds": t} for n, s, t in rows], indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
