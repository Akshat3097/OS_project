"""Engine checks against hand-verified textbook examples (Silberschatz, Operating System Concepts)."""
import pytest

from engine import bankers, generator, scheduling, semaphore
from engine.scheduling import Process as P


def chart(res):
    return [(s.pid, s.start, s.end) for s in res.gantt]


def test_fcfs_convoy_example():
    r = scheduling.fcfs([P("P1", 0, 24), P("P2", 0, 3), P("P3", 0, 3)])
    assert chart(r) == [("P1", 0, 24), ("P2", 24, 27), ("P3", 27, 30)]
    assert r.avg_wt == 17


def test_sjf_example():
    r = scheduling.sjf([P("P1", 0, 6), P("P2", 0, 8), P("P3", 0, 7), P("P4", 0, 3)])
    assert [s.pid for s in r.gantt] == ["P4", "P1", "P3", "P2"]
    assert r.avg_wt == 7


def test_srtf_example():
    r = scheduling.srtf([P("P1", 0, 8), P("P2", 1, 4), P("P3", 2, 9), P("P4", 3, 5)])
    assert chart(r) == [("P1", 0, 1), ("P2", 1, 5), ("P4", 5, 10), ("P1", 10, 17), ("P3", 17, 26)]
    assert r.avg_wt == 6.5
    assert any(d.kind == "preempt" and d.preempted == "P1" for d in r.decisions)


def test_rr_example():
    r = scheduling.round_robin([P("P1", 0, 24), P("P2", 0, 3), P("P3", 0, 3)], 4)
    assert chart(r) == [("P1", 0, 4), ("P2", 4, 7), ("P3", 7, 10), ("P1", 10, 30)]
    assert round(r.avg_wt, 2) == 5.67


def test_rr_arrival_convention():
    procs = [P("P1", 0, 5), P("P2", 1, 3), P("P3", 2, 1), P("P4", 3, 2), P("P5", 4, 3)]
    r = scheduling.round_robin(procs, 2)
    assert {k: v.completion for k, v in r.results.items()} == {"P1": 13, "P2": 12, "P3": 5, "P4": 9, "P5": 14}
    other = scheduling.round_robin(procs, 2, new_arrivals_first=False)
    assert other.timeline() != r.timeline()


def test_priority_np_example():
    r = scheduling.priority_np([P("P1", 0, 10, 3), P("P2", 0, 1, 1), P("P3", 0, 2, 4),
                                P("P4", 0, 1, 5), P("P5", 0, 5, 2)])
    assert [s.pid for s in r.gantt] == ["P2", "P5", "P1", "P3", "P4"]
    assert r.avg_wt == 8.2


def test_priority_preemptive():
    r = scheduling.priority_p([P("P1", 0, 5, 3), P("P2", 2, 2, 1)])
    assert chart(r) == [("P1", 0, 2), ("P2", 2, 4), ("P1", 4, 7)]


def test_idle_gap():
    r = scheduling.fcfs([P("P1", 3, 4), P("P2", 10, 2)])
    assert chart(r) == [("IDLE", 0, 3), ("P1", 3, 7), ("IDLE", 7, 10), ("P2", 10, 12)]
    assert r.results["P1"].waiting == 0


def test_metric_identities():
    for algo in scheduling.ALGORITHMS:
        for d in (1, 2, 3):
            prob = generator.generate_scheduling(algo, d, seed=d * 31)
            r = prob.solve()
            for p in prob.processes:
                res = r.results[p.pid]
                assert res.turnaround == res.completion - p.arrival
                assert res.waiting == res.turnaround - p.burst
                assert res.waiting >= 0 and res.response >= 0
            busy = sum(s.length for s in r.gantt if s.pid != "IDLE")
            assert busy == sum(p.burst for p in prob.processes)


def test_validation():
    with pytest.raises(ValueError):
        scheduling.fcfs([P("P1", 0, 0)])
    with pytest.raises(ValueError):
        scheduling.round_robin([P("P1", 0, 2)], 0)


AV = [3, 3, 2]
MX = [[7, 5, 3], [3, 2, 2], [9, 0, 2], [2, 2, 2], [4, 3, 3]]
AL = [[0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1], [0, 0, 2]]


def test_bankers_textbook_sequence():
    res = bankers.safety(AV, MX, AL)
    assert res["safe"]
    assert res["sequence"] == ["P1", "P3", "P4", "P0", "P2"]
    assert res["need"][0] == [7, 4, 3]


def test_bankers_accepts_any_valid_sequence():
    assert bankers.verify_sequence(AV, MX, AL, ["P1", "P3", "P0", "P2", "P4"])["valid"]
    bad = bankers.verify_sequence(AV, MX, AL, ["P0", "P1", "P2", "P3", "P4"])
    assert not bad["valid"] and bad["fail_step"] == 1


def test_bankers_request_textbook():
    r1 = bankers.request(AV, MX, AL, 1, [1, 0, 2])
    assert r1["granted"]
    av2, al2 = r1["new_available"], r1["new_allocation"]
    assert av2 == [2, 3, 0]
    assert bankers.request(av2, MX, al2, 4, [3, 3, 0])["reason"] == "must_wait"
    assert bankers.request(av2, MX, al2, 0, [0, 2, 0])["reason"] == "unsafe"


def test_semaphore_blocking():
    ops = [{"pid": "P1", "op": "wait", "sem": "S"}, {"pid": "P2", "op": "wait", "sem": "S"},
           {"pid": "P3", "op": "signal", "sem": "S"}]
    res = semaphore.trace({"S": 0}, ops)
    assert res["final_values"]["S"] == -1
    assert res["blocked"] == ["P2"]
    assert res["steps"][2]["woken"] == "P1"


def test_generators_produce_valid_problems():
    for d in (1, 2, 3):
        b = generator.generate_bankers(d, seed=d)
        b.solve()
        s = generator.generate_semaphore(d, seed=d)
        s.solve()
