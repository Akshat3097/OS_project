"""What teachers actually typed (eval/teacher_questions.txt, 24 Oct): problem formats, answers to check, conventions."""
import pytest

from rag.store import KnowledgeBase
from tutor import chat_parse as cp
from tutor import faq
from tests.test_chat_agent import make, say


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase()


def procs(text):
    p = cp.parse_scheduling_problem(text)
    return p and [(x.pid, x.arrival, x.burst, x.priority) for x in p["processes"]], p and p["algorithms"]


def test_scheduling_formats_teachers_typed():
    assert procs("P1(0,5) P2(1,3) P3(2,8) P4(3,6) solve using SJF non preemptive find avg wt and tat") == \
        ([("P1", 0, 5, 0), ("P2", 1, 3, 0), ("P3", 2, 8, 0), ("P4", 3, 6, 0)], ["SJF"])
    assert procs("AT: 0 1 2 4\nBT: 8 4 9 5\nsrtf gantt chart and avg TAT pls")[0] == \
        [("P1", 0, 8, 0), ("P2", 1, 4, 0), ("P3", 2, 9, 0), ("P4", 4, 5, 0)]
    assert procs("sjf p1 at0 bt6 p2 at1 bt2 p3 at2 bt4")[0] == [("P1", 0, 6, 0), ("P2", 1, 2, 0), ("P3", 2, 4, 0)]
    got = procs("P1 0 10 prio 3, P2 1 1 prio 1, P3 2 2 prio 4, P4 3 1 prio 5, P5 4 5 prio 2. preemptive")
    assert got[0][-1] == ("P5", 4, 5, 2) and got[1] == ["PRIORITY_P"]
    assert procs("priority lower no higher p1 b5 pr3 p2 b3 pr1 p3 b8 pr2 arr0")[0] == \
        [("P1", 0, 5, 3), ("P2", 0, 3, 1), ("P3", 0, 8, 2)]


def test_bankers_formats_teachers_typed():
    tb = {"allocation": [[0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1], [0, 0, 2]], "available": [3, 3, 2]}
    for text in ["alloc: P0 010 P1 200 P2 302 P3 211 P4 002 max: P0 753 P1 322 P2 902 P3 222 P4 433 avail: 332",
                 "5 processes 3 resource types A B C total 10 5 7. alloc P0 010 P1 200 P2 302 P3 211 P4 002, "
                 "max P0 753 P1 322 P2 902 P3 222 P4 433"]:
        b = cp.parse_bankers_problem(text)
        assert b and b["allocation"] == tb["allocation"] and b["available"] == tb["available"], text
    b = cp.parse_bankers_problem("Banker claim matrix\n7 5 3\n3 2 2\n9 0 2\n2 2 2\nAllocation\n0 1 0\n2 0 0\n3 0 2\n"
                                 "2 1 1\nAvailable 3 3 2")
    assert b["maximum"][2] == [9, 0, 2] and b["allocation"][3] == [2, 1, 1]
    b = cp.parse_bankers_problem("Allocation: P0(0,1,0) P1(2,0,0) P2(3,0,2). Max: P0(7,5,3) P1(3,2,2) P2(9,0,2). "
                                 "Available: (3,3,2)")
    assert b["maximum"] == [[7, 5, 3], [3, 2, 2], [9, 0, 2]]
    b = cp.parse_bankers_problem("3 processes, max need 10, 4, 9. currently allocated 5, 2, 4. total resources 12")
    assert b["available"] == [1] and b["maximum"] == [[10], [4], [9]]
    b = cp.parse_bankers_problem("bankers avail 2 1 0 alloc p0 1 0 0 max 3 2 2 p1 0 1 0 max 2 2 2 safe?")
    assert b["allocation"] == [[1, 0, 0], [0, 1, 0]]


def test_answers_written_the_way_teachers_did(tmp_path, kb):
    agent, st = make(tmp_path, kb)
    r = say(agent, st, "P1 0 5, P2 1 3 FCFS, my avg WT is 6, right?")
    assert r.action == "check" and "does not match" in r.text
    r = say(agent, st, "RR q=2 for P1(0,4) P2(1,5) P3(2,2). i got gantt chart P1 P2 P1 P3 P2 P2. check this")
    assert r.action == "check" and "P1 → P2 → P3 → P1 → P2" in r.text and "joins the queue before" in r.text
    r = say(agent, st, "for P1(0,6) P2(2,4) SJF non preemptive, TAT for P2 is 6?")
    assert r.action == "check" and "TAT of P2 = 6: ✗" in r.text
    r = say(agent, st, "SJF non preemptive P1(0,7) P2(2,4) P3(4,1) P4(5,4) order P1 P3 P2 P4 and avg wt = "
                       "(0+7+8+12)/4 = 6.75 is this right")
    assert r.action == "check" and "6.75" in r.text and "does not match" in r.text


def test_worked_out_instead_of_guessed(tmp_path, kb):
    agent, st = make(tmp_path, kb)
    r = say(agent, st, "if turnaround time is 8 and burst time is 5 then waiting time is 13 right")
    assert r.action == "formula" and "WT is 3, not 13" in r.text
    r = say(agent, st, "semaphore S=1, P1 calls wait then P2 calls wait, S becomes -1 so both P1 and P2 are blocked now correct?")
    assert r.action == "sem_trace" and "**Blocked at the end:** P2." in r.text
    r = say(agent, st, "5 processes 3 resource types A B C total 10 5 7. P1 requests (1,0,2) alloc P0 010 P1 200 P2 302 "
                       "P3 211 P4 002, max P0 753 P1 322 P2 902 P3 222 P4 433. can request be granted immediately")
    assert r.action == "bankers_request" and "**granted**" in r.text


def test_conventions_get_checked_answers():
    for q, start in [("in srtf if a new process arrives with burst equal to remaining time of current process, who runs",
                      "**The running process continues.**"),
                     ("in RR if a new process arrives at same time a process gets preempted, which goes first",
                      "In this course the **newly arrived process joins the ready queue first**"),
                     ("what if time quantum is 0", "**A quantum of 0 isn't valid**"),
                     ("is fcfs preemptive or not", "**FCFS is non-preemptive**"),
                     ("can sjf starve a process", "**Yes, both versions can.**"),
                     ("in priority scheduling is 1 highest priority or lowest?", "In this course (and Silberschatz)"),
                     ("why is SRTF not used much in practice if its optimal", "Three reasons"),
                     ("difference between preemptive n nonpreemptive scheduling", "**Non-preemptive:**")]:
        from tutor.chat_agent import fix_typos
        hit = faq.lookup(fix_typos(q))
        assert hit and hit["text"].startswith(start), q


def test_in_practice_is_not_a_practice_request(tmp_path, kb):
    agent, st = make(tmp_path, kb)
    r = say(agent, st, "why is SRTF not used much in practice if its optimal")
    assert r.action == "faq"
    r = say(agent, st, "solve this knapsack problem for me")
    assert r.action == "chat" and r.text.startswith("That's outside")


def test_follow_ups_use_the_current_topic(tmp_path, kb):
    agent, st = make(tmp_path, kb)
    say(agent, st, "explain bankers algo")
    r = say(agent, st, "ok give me one example to solve")
    assert r.action == "practice" and st["problem"]["problem"]["kind"] == "bankers"
    say(agent, st, "what is critical section problem")
    r = say(agent, st, "what are the 3 requirements")
    assert r.action == "faq" and "Mutual exclusion" in r.text
