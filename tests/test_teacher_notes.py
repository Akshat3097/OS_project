"""The worked examples in the BCSE303L class notes (data/question_bank/teacher_notes_examples.json)."""
import pytest

from engine import question_bank, semaphore
from engine.advanced import Job, QueueSpec, performance, simulate
from engine.generator import SemaphoreProblem
from tutor.error_analysis import analyse_semaphore

# Slips in the slides (explained in each item's "notes"); the engine's value is the corrected one.
KNOWN_SLIPS = {"NOTES-FCFS-EX5", "NOTES-RR-EX3", "NOTES-IO-RR", "NOTES-IO-PRIO"}
NOTES = [i for i in question_bank.load() if question_bank.is_notes_example(i)]


@pytest.mark.parametrize("item", NOTES, ids=[i["id"] for i in NOTES])
def test_notes_examples(item):
    row = question_bank.check(item)
    if item["id"] in KNOWN_SLIPS:
        assert row["match"] is False, f"{item['id']} now matches; remove it from KNOWN_SLIPS"
    elif item.get("official"):
        failed = [n for n, ok in row["checks"] if not ok]
        assert row["match"], f"{item['id']}: {failed} — engine says {row['engine']}"


def test_slip_corrections():
    by_id = {i["id"]: i for i in NOTES}
    rr3 = question_bank.to_problem(by_id["NOTES-RR-EX3"]).solve()
    assert rr3.results["P5"].completion == 17 and abs(rr3.avg_tat - 20.2) < 1e-9 and abs(rr3.avg_wt - 14.6) < 1e-9
    io = question_bank.to_problem(by_id["NOTES-IO-PRIO"]).solve()
    assert io.results["P4"].waiting_incl_io == 6 and io.avg("turnaround") == 8.75 and io.avg("waiting_incl_io") == 4.5


def test_mlfq_gantt_matches_notes():
    jobs = [Job("P1", 0, [("CPU", 8)]), Job("P2", 1, [("CPU", 4)]), Job("P3", 2, [("CPU", 2)]),
            Job("P4", 4, [("CPU", 1)]), Job("P5", 6, [("CPU", 5)]), Job("P6", 8, [("CPU", 3)])]
    qs = [QueueSpec(1, "RR", 2), QueueSpec(2, "RR", 4), QueueSpec(3, "FCFS")]
    res = simulate(jobs, queues=qs, feedback=True)
    assert [p for p, _, _ in res.gantt] == ["P1", "P2", "P3", "P4", "P5", "P6", "P1", "P2", "P5", "P6", "P1"]
    assert performance(res.gantt, 6)["context_switches"] == 10


def test_performance_counts_like_the_notes():
    # FCFS with I/O example: idle gap between two runs of P5 is not a context switch
    g = [("IDLE", 0, 2), ("P1", 2, 5), ("P2", 5, 7), ("P3", 7, 11), ("P4", 11, 13), ("P1", 13, 15), ("P2", 15, 17),
         ("P3", 17, 18), ("P4", 18, 20), ("P5", 20, 22), ("IDLE", 22, 24), ("P5", 24, 25)]
    pf = performance(g, 5)
    assert pf == {"cpu_busy": 21, "total_time": 25, "cpu_utilization": 84.0, "throughput": 0.2, "context_switches": 8}


def test_semaphore_busy_wait_definition():
    ops = [{"pid": "P1", "op": "wait", "sem": "S"}, {"pid": "P2", "op": "wait", "sem": "S"},
           {"pid": "P3", "op": "wait", "sem": "S"}, {"pid": "P1", "op": "signal", "sem": "S"}]
    blocking = semaphore.trace({"S": 1}, ops)
    busy = semaphore.trace({"S": 1}, ops, "busy_wait")
    assert blocking["final_values"] == {"S": -1} and busy["final_values"] == {"S": 0}
    assert blocking["blocked"] == busy["blocked"] == ["P3"]
    assert all(s["value_after"] >= 0 for s in busy["steps"])
    prob = SemaphoreProblem(2, {"S": 1}, ops)
    for final in ({"S": -1}, {"S": 0}):           # both definitions are accepted
        a = analyse_semaphore(prob, final, ["P3"])
        assert a["correct"], final
    assert analyse_semaphore(prob, {"S": 0}, ["P3"])["semaphore_mode"] == "busy_wait"
    assert not analyse_semaphore(prob, {"S": 1}, ["P3"])["correct"]


def test_class_notes_are_retrieved_first():
    from rag.store import KnowledgeBase
    kb = KnowledgeBase()
    kb.build()
    for q, section in [("What is the Bakery algorithm?", "Bakery"), ("Explain Peterson's solution", "Peterson"),
                       ("explain multilevel feedback queue", "MLFQ")]:
        top = kb.search(q, k=1)[0]
        assert top["meta"].get("type") == "Teacher's notes" and section in top["meta"].get("section", ""), (q, top["meta"])
