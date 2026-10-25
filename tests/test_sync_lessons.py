"""The classical synchronization lessons (Module 4, slides 64–78): their worked traces match the notes, every
teach-back question can be generated and checked, and the chat routes to them."""
import random

from tutor import lessons as L
from tutor import teachback as TB


def _outcomes(lid):
    w = L.LESSON_BY_ID[lid]["watch"]
    return [(s["pid"], s["outcome"]) for s in L.semaphore_steps(w["initial"], w["ops"])]


def test_bounded_buffer_producer_blocks_when_full_and_is_woken():
    out = _outcomes("bounded_buffer")
    assert out[8] == ("P", "blocks") and out[-1] == ("C", "wakes P")
    assert sum(o == "blocks" for _, o in out) == 1


def test_readers_share_writer_waits_for_last_reader():
    out = _outcomes("readers_writers")
    assert ("R2", "blocks") not in out                       # the second reader is not blocked by the first
    assert out[5] == ("W", "blocks") and out[9] == ("R2", "wakes W")


def test_dining_philosophers_all_left_first_deadlocks():
    w = L.LESSON_BY_ID["dining"]["watch"]
    from engine import semaphore
    tr = semaphore.trace(w["initial"], w["ops"])
    assert tr["blocked"] == ["P0", "P1", "P2", "P3", "P4"]   # everyone waits: circular wait


def test_every_idea_has_a_working_question():
    for lid in ("bounded_buffer", "readers_writers", "dining"):
        lesson = L.LESSON_BY_ID[lid]
        assert len(lesson["watch"]["notes"]) == len(lesson["watch"]["ops"])
        for idea in lesson["ideas"]:
            q = TB.make_question(lesson, idea, seed=1)
            right = next(o[0] for o in q["options"] if o[1])
            assert TB.check_answer(q, right)["ok"]


def test_keyword_rubric_hears_a_good_explanation():
    a = TB.keyword_assess(L.LESSON_BY_ID["dining"],
                          "Five philosophers share five chopsticks and each needs both the left and right one. If everyone "
                          "picks up the left chopstick at the same time they wait forever, a deadlock with circular wait. "
                          "The fix is to pick up both only if both are free, like the monitor solution.")
    assert all(v == "clear" for v in a["ideas"].values())


def test_chat_routes_to_the_new_lessons(tmp_path):
    from rag.store import KnowledgeBase
    from tutor.chat_agent import ChatAgent, new_state
    from tutor.student_model import StudentModel
    agent = ChatAgent(StudentModel(tmp_path / "t.db"), KnowledgeBase(), None, use_llm=False)
    for text, lid in (("explain the producer consumer problem", "bounded_buffer"),
                      ("explain readers-writers", "readers_writers"), ("explain dining philosophers", "dining")):
        route = agent.route(new_state("s"), text)
        assert route.action == "explain" and route.topic == lid, (text, route)
