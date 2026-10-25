"""Training data v2: the student-style rewrite changes the wording only, never the numbers or names the
engine-verified replies depend on."""
import random
import re
from collections import Counter

from qlora.student_style import student_variants, studentify

SAMPLES = [
    "Can you schedule these with SJF? P1 arrives at 0 and needs 9 ms; P2 arrives at 2 and needs 2 ms.",
    "I solved this with preemptive SJF: P1 (AT 0, BT 6); P2 (AT 0, BT 2). My answer:\nP1: CT 10, TAT 10, WT 4",
    "Find the average waiting time with RR (q = 4)\nProcess AT BT\nP1 0 9\nP2 1 3",
    "Trace this: counting semaphore(s) start at S = 1. P1: wait(S), P2: signal(S). What is the final value?",
    "Is the system safe?\nAllocation\nP0 0 1 0\nP1 2 0 0\nAvailable 3 3 2",
]


def test_numbers_ids_and_tables_survive():
    rng = random.Random(1)
    for _ in range(40):
        for s in SAMPLES:
            out = studentify(s, rng)
            assert re.findall(r"\d+", out) == re.findall(r"\d+", s)
            assert re.findall(r"P\d+|\bS\b", out) == re.findall(r"P\d+|\bS\b", s)      # process and semaphore names
            names = Counter(re.findall(r"\b[A-Z]{2,}\b", s))                            # acronyms may be added
            assert not names - Counter(re.findall(r"\b[A-Z]{2,}\b", out))               # ("waiting time" → WT), never lost
            for line in s.splitlines():
                if re.match(r"^\s*P\d+\s", line):
                    assert line in out                       # table rows are copied unchanged


def test_variants_rewrite_users_only():
    ex = [{"kind": "explain", "messages": [{"role": "system", "content": "sys"},
                                            {"role": "user", "content": "Please explain round robin to me."},
                                            {"role": "assistant", "content": "Round Robin gives each process q."}]}] * 50
    out = student_variants(ex, random.Random(2), 0.5)
    assert 10 < len(out) < 40
    for v in out:
        assert v["kind"] == "explain_student"
        assert v["messages"][0] == ex[0]["messages"][0] and v["messages"][2] == ex[0]["messages"][2]
    assert any(v["messages"][1]["content"] != ex[0]["messages"][1]["content"] for v in out)
