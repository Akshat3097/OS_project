"""
Tutoring scenarios for fine-tuning and evaluation.

A scenario = (problem, simulated student answer, history) -> the exact prompt the
runtime tutor would send to the LLM. Because the OS Engine and error analysis are
deterministic, every scenario comes with verified facts and a list of things the
reply must NOT reveal, so replies can be checked automatically.
"""
from __future__ import annotations

import random

from engine import generator, scheduling
from engine.scheduling import ALGORITHMS
from rag.store import KnowledgeBase
from tutor import prompts, strategy as strat_mod
from tutor.error_analysis import analyse_bankers, analyse_scheduling, analyse_semaphore
from ui import bankers_presets, scheduling_presets, semaphore_presets, swap_two_blocks

LEVELS = ["beginner", "intermediate", "advanced"]


def _local_mistake(problem, rng: random.Random):
    """Swap two adjacent Gantt blocks: a realistic single wrong decision."""
    g = [(s.pid, s.start, s.end) for s in problem.solve().gantt]
    return swap_two_blocks(g, rng.randrange(1, max(2, len(g) - 1)))


def scheduling_scenarios(problem, rng: random.Random) -> list[tuple[str, dict]]:
    presets = scheduling_presets(problem)
    out = [(name, ans) for name, ans in presets.items() if "Empty" not in name]
    lm = _local_mistake(problem, rng)
    if lm:
        out.append(("local wrong decision", {"gantt": lm, "metrics": {}}))
    return out


def make_scenarios(n: int, seed: int, kb: KnowledgeBase | None = None) -> list[dict]:
    rng = random.Random(seed)
    topics = list(ALGORITHMS) + ["BANKERS", "SEMAPHORE"]
    out: list[dict] = []
    seen_prompts: set[str] = set()
    tries = 0
    while len(out) < n and tries < n * 20:
        tries += 1
        topic = rng.choice(topics)
        diff = rng.choice([1, 2, 3])
        s = rng.randrange(10**9)
        if topic == "BANKERS":
            prob = generator.generate_bankers(diff, s)
            answers = [(k, v) for k, v in bankers_presets(prob).items() if "Empty" not in k]
        elif topic == "SEMAPHORE":
            prob = generator.generate_semaphore(diff, s)
            answers = [(k, v) for k, v in semaphore_presets(prob).items() if "Empty" not in k]
        else:
            prob = generator.generate_scheduling(topic, diff, s)
            answers = scheduling_scenarios(prob, rng)
        name, ans = rng.choice(answers)
        if prob.kind == "scheduling":
            analysis = analyse_scheduling(prob, ans.get("gantt"), ans.get("metrics"))
        elif prob.kind == "bankers":
            seq = [x for x in ans["sequence"].replace(" ", "").split(",") if x]
            analysis = analyse_bankers(prob, ans["need"], ans["safe"], seq)
        else:
            analysis = analyse_semaphore(prob, ans["final"], ans["blocked"])
        roll = rng.random()
        if roll < 0.12:
            analysis_used, attempt, hints = None, 1, rng.choice([1, 2, 3])        # hint before answering
        else:
            analysis_used, attempt, hints = analysis, rng.choice([1, 1, 2, 3, 4]), rng.choice([0, 0, 1])
        recurring = []
        if analysis_used and not analysis_used["correct"] and rng.random() < 0.15 and analysis_used.get("root_cause"):
            rc = analysis_used["root_cause"]
            recurring = [{"type": rc["type"], "count": 2, "label": rc["label"], "skill": rc["skill"]}]
        level = rng.choice(LEVELS)
        st = strat_mod.decide(prob, analysis_used, level, recurring, attempt, hints)
        notes = []
        if kb is not None:
            from rag.store import ALGO_TO_SUBTOPIC
            q = " ".join(f for f in st.facts if f.startswith(("Likely misconception", "Detected error", "Rule")))
            notes = kb.search(q or st.topic, k=2, subtopic=ALGO_TO_SUBTOPIC.get(st.topic))
        msgs = prompts.feedback_messages(st, notes)
        key = msgs[1]["content"]
        if key in seen_prompts:
            continue
        seen_prompts.add(key)
        out.append({"id": f"s{seed}-{len(out)}", "topic": topic, "difficulty": diff, "answer_type": name,
                    "strategy": st, "messages": msgs, "level": level})
    return out
