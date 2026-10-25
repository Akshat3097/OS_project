"""Error analysis, student model, strategy and guard."""
import time

import pytest

from engine.generator import BankersProblem, SchedulingProblem, SemaphoreProblem
from engine.scheduling import Process as P, round_robin, sjf
from tutor import prompts, strategy
from tutor.error_analysis import analyse_bankers, analyse_scheduling, analyse_semaphore
from tutor.student_model import StudentModel, bkt_update

SRTF = SchedulingProblem("SRTF", 2, [P("P1", 0, 8), P("P2", 1, 4), P("P3", 2, 9), P("P4", 3, 5)])


def chart(res):
    return [(s.pid, s.start, s.end) for s in res.gantt]


def test_algorithm_confusion_detected():
    a = analyse_scheduling(SRTF, chart(sjf(SRTF.processes)), None)
    assert a["root_cause"]["type"] == "algorithm_confusion"
    assert a["errors"][0]["details"][0]["applied"] == "SJF"


def test_local_wrong_selection_and_divergence_time():
    a = analyse_scheduling(SRTF, [("P1", 0, 1), ("P2", 1, 5), ("P3", 5, 14), ("P4", 14, 19), ("P1", 19, 26)], None)
    assert a["root_cause"]["type"] == "wrong_selection"
    assert a["divergence"]["time"] == 5 and a["divergence"]["correct_pid"] == "P4"


def test_propagated_errors_not_blamed_on_formulas():
    wrong = sjf(SRTF.processes)
    metrics = {p: {"CT": r.completion, "TAT": r.turnaround, "WT": r.waiting} for p, r in wrong.results.items()}
    a = analyse_scheduling(SRTF, chart(wrong), metrics)
    assert a["observations"]["WT_FORMULA"] and a["observations"]["TAT_FORMULA"]
    assert not a["observations"]["SRTF"]
    assert "consistent" in {v for row in a["cells"].values() for v in row.values()}


@pytest.mark.parametrize("field,etype", [("WT", "wt_forgot_burst"), ("TAT", "tat_forgot_arrival")])
def test_formula_misconceptions(field, etype):
    r = SRTF.solve()
    m = {}
    for pid, x in r.results.items():
        m[pid] = {"CT": x.completion, "TAT": x.turnaround, "WT": x.waiting}
        if field == "WT":
            m[pid]["WT"] = x.turnaround
        else:
            m[pid]["TAT"] = x.completion
            m[pid]["WT"] = x.completion - x.burst
    a = analyse_scheduling(SRTF, chart(r), m)
    assert etype in a["error_types"]


def test_rr_requeue_convention_detected():
    pr = SchedulingProblem("RR", 3, [P("P1", 0, 5), P("P2", 1, 3), P("P3", 2, 1), P("P4", 3, 2), P("P5", 4, 3)], 2)
    a = analyse_scheduling(pr, chart(round_robin(pr.processes, 2, new_arrivals_first=False)), None)
    assert a["root_cause"]["type"] == "rr_requeue_order"


def test_bankers_alternative_sequence_accepted_and_need_sign_error():
    bp = BankersProblem(2, [3, 3, 2], [[7, 5, 3], [3, 2, 2], [9, 0, 2], [2, 2, 2], [4, 3, 3]],
                        [[0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1], [0, 0, 2]])
    need = bp.solve()["need"]
    assert analyse_bankers(bp, need, True, ["P1", "P3", "P0", "P2", "P4"])["correct"]
    bad = analyse_bankers(bp, [[-v for v in r] for r in need], True, ["P1", "P3", "P0", "P2", "P4"])
    assert bad["root_cause"]["type"] == "need_sign_error"


def test_semaphore_forgot_wakeup():
    sp = SemaphoreProblem(1, {"S": 0}, [{"pid": "P1", "op": "wait", "sem": "S"},
                                        {"pid": "P2", "op": "signal", "sem": "S"}])
    a = analyse_semaphore(sp, {"S": 0}, ["P1"])
    assert "forgot_wakeup" in a["error_types"]


def test_bkt_moves_in_right_direction():
    assert bkt_update(0.3, True) > 0.3
    assert bkt_update(0.6, False) < 0.6


def test_student_model_first_attempt_only_and_recurring(tmp_path):
    sm = StudentModel(tmp_path / "t.db")
    wrong = [("P1", 0, 1), ("P2", 1, 5), ("P3", 5, 14), ("P4", 14, 19), ("P1", 19, 26)]
    a = analyse_scheduling(SRTF, wrong, None)
    ch1 = sm.record_attempt("s", SRTF.to_dict(), "prob1", a, 1, 0, False, 10)
    ch2 = sm.record_attempt("s", SRTF.to_dict(), "prob1", a, 2, 0, False, 10)
    assert ch1 and not ch2                       # retries do not update mastery
    assert not sm.recurring_errors("s")          # same problem twice is not "recurring"
    sm.record_attempt("s", SRTF.to_dict(), "prob2", a, 1, 0, False, 10)
    assert sm.recurring_errors("s")[0]["type"] == "wrong_selection"
    assert sm.recommend_next("s")["topic"] == "SRTF"


def test_hint_ladder_escalates_and_hides_answer():
    a = analyse_scheduling(SRTF, [("P1", 0, 1), ("P2", 1, 5), ("P3", 5, 14), ("P4", 14, 19), ("P1", 19, 26)], None)
    actions = [strategy.decide(SRTF, a, "beginner", [], n, 0) for n in (1, 3, 4)]
    assert [s.action for s in actions] == ["SOCRATIC_HINT", "TARGETED_HINT", "REVEAL_STEP"]
    assert not any("Correct choice" in f for f in actions[0].facts + actions[1].facts)
    assert any("Correct choice" in f for f in actions[2].facts)


def test_guard_blocks_leak_but_allows_questions():
    a = analyse_scheduling(SRTF, [("P1", 0, 1), ("P2", 1, 5), ("P3", 5, 14), ("P4", 14, 19), ("P1", 19, 26)], None)
    s = strategy.decide(SRTF, a, "beginner", [], 1, 0)
    assert any(i["type"] == "revealed_answer" for i in prompts.check_response("P4 should run next.", s))
    assert not any(i["type"] == "revealed_answer"
                   for i in prompts.check_response("Should P4 or P3 run at t=5?", s))


def test_guard_judges_a_hidden_value_that_is_also_problem_data():
    """The hidden WT of P2 is 4, and 4 is also a burst time in the problem: block it only when tied to the WT."""
    from types import SimpleNamespace
    from tutor import prompts
    strat = SimpleNamespace(reveal=False, facts=["P1 arrives at 0 with burst 4", "P2 arrives at 1 with burst 3"],
                            secrets={"pids": [], "numbers": [4], "values": [{"pid": "P2", "field": "WT", "value": 4}]})
    blocked = lambda t: any(i["type"] == "revealed_answer" for i in prompts.check_response(t, strat))  # noqa: E731
    for leak in ("P2's waiting time should be 4.", "The correct WT for P2 is 4", "So P2 waits 4 units in total.",
                 "That gives 4 units of waiting for P2."):
        assert blocked(leak), leak
    for safe in ("P1 has a burst of 4, so it runs first.", "Waiting time = turnaround − burst; P1's burst is 4.",
                 "Is P2's waiting time really 4?",
                 "-   B: CT=7, TAT=7−1=6, WT=6−4=2",                    # a worked example about another process
                 "P1 waits 4 units before it runs again."):
        assert not blocked(safe), safe
