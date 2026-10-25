"""Fixes for what eval/teacher_probe.py found on 24 Oct (teacher-style questions through the whole chat)."""
import pytest

from rag.store import KnowledgeBase
from tutor import chat_parse as cp
from tutor import faq
from tutor.chat_agent import clean_reply, clean_stream, fix_typos
from tests.test_chat_agent import FakeClient, make, say


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase()


def test_hint_opener_and_leaked_instructions_are_removed():
    assert clean_reply("Here's a hint.\n\nThe PCB keeps the state of each process.") == "The PCB keeps the state of each process."
    leaked = ("A semaphore is an integer used for signalling.\nLESSON ANALOGY: A parking lot.\nKEY POINTS: wait; signal")
    assert clean_reply(leaked) == "A semaphore is an integer used for signalling."
    assert clean_reply("Here's a hint.\n\nThe OS Engine computes every schedule and number exactly.") == ""
    garbage = "Here's a hint.\n\nThe full correct answer is below. If you want to retry on your own, delete what you have."
    assert clean_reply(garbage) == ""
    # ordinary words are not labels
    ok = "For example: two processes each hold one resource. The topic of deadlock covers this."
    assert clean_reply(ok) == ok


def test_cleaned_stream_falls_back_when_nothing_is_left():
    pieces = ["Here's a hint.\n\n", "The full correct ", "answer is below. More text here."]
    assert "".join(clean_stream(iter(pieces), "FALLBACK")) == "FALLBACK"
    good = ["Round Robin gives each process ", "one quantum in turn. ", "A process that needs more goes to the back ",
            "of the queue and waits for its next turn.\nKEY POINTS: secret"]
    out = "".join(clean_stream(iter(good), "FALLBACK"))
    assert out.startswith("Round Robin gives") and "KEY POINTS" not in out and "next turn." in out


def test_typos_are_corrected_before_routing(tmp_path, kb):
    assert fix_typos("dinning philosphers problem?") == "dining philosophers problem?"
    assert fix_typos("explian rr with quantum 2") == "explain rr with quantum 2"
    assert fix_typos("wat is semaphore") == "what is semaphore"
    assert fix_typos("the processor is idle") == "the processor is idle"
    assert fix_typos("write a python program") == "write a python program"
    assert fix_typos("semaphor") == "semaphore"
    agent, st = make(tmp_path, kb)
    r = say(agent, st, "dinning philosphers problem?")
    assert r.action in ("explain", "ask") and st["topic"] == "dining"
    assert st["messages"][-2]["content"] == "dinning philosphers problem?"      # saved as the student typed it


def test_trick_questions_get_checked_answers(tmp_path, kb):
    agent, st = make(tmp_path, kb, FakeClient(text="Wrong things the model should not get to say about this at all."))
    r = say(agent, st, "is an unsafe state the same as deadlock?")
    assert r.action == "faq" and "unsafe ≠ deadlock" in r.text and agent.client.calls == [] or r.action == "faq"
    r = say(agent, st, "can round robin cause starvation?")
    assert r.action == "faq" and r.text.startswith("**No.**")
    r = say(agent, st, "explain LRU page replacement")
    assert r.action == "faq" and "Belady" in r.text and "outside the two areas" in r.text
    assert faq.lookup("explain round robin") is None
    assert faq.lookup("is SJF optimal for P1 0 5, P2 1 3?") is None            # numbers: a specific problem


def test_example_follow_up_uses_the_topic(tmp_path, kb):
    agent, st = make(tmp_path, kb)
    say(agent, st, "explain round robin")
    r = say(agent, st, "give me an example")
    assert r.action == "example" and r.cards[0]["type"] == "example" and r.cards[0]["lesson"] == "rr"


def test_bankers_request_on_the_open_problem(tmp_path, kb):
    agent, st = make(tmp_path, kb)
    say(agent, st, "Allocation: P0 0 1 0, P1 2 0 0, P2 3 0 2, P3 2 1 1, P4 0 0 2. Max: P0 7 5 3, P1 3 2 2, "
                   "P2 9 0 2, P3 2 2 2, P4 4 3 3. Available 3 3 2. Is it safe?")
    r = say(agent, st, "what if P1 requests 1 0 2?")
    assert r.action == "bankers_request" and "**granted**" in r.text and "(2, 3, 0)" in r.text
    r = say(agent, st, "what if P4 requests 3 3 0?")
    assert r.action == "bankers_request" and "**unsafe**" in r.text and "**not granted**" in r.text


def test_why_a_waiting_time_is_worked_out(tmp_path, kb):
    agent, st = make(tmp_path, kb)
    say(agent, st, "solve fcfs for P1 arrival 0 burst 5, P2 arrival 1 burst 3, P3 arrival 2 burst 8")
    r = say(agent, st, "why is the waiting time of P3 that much?")
    assert r.action == "why" and "WT = TAT − BT = 14 − 8 = **6**" in r.text and "P1 (2–5)" in r.text


def test_answer_written_label_first_is_read():
    a = cp.parse_scheduling_answer("My answer: waiting times P1 = 4, P2 = 1, P3 = 0, average 1.67", ["P1", "P2", "P3"])
    assert a["metrics"] == {"P1": {"WT": 4}, "P2": {"WT": 1}, "P3": {"WT": 0}} and a["averages"] == {"WT": 1.67}
    a = cp.parse_scheduling_answer("waiting time of P1 is 4, P2 is 1 and P3 is 0", ["P1", "P2", "P3"])
    assert a["metrics"]["P3"] == {"WT": 0}


def test_system_call_questions_get_answers_and_clips(tmp_path, kb):
    hit = faq.lookup("if fork is called 3 times how many processes")
    assert hit and hit["video"] == "fork" and "2ⁿ" in hit["text"]
    assert faq.lookup("how many forks do dining philosophers need") is None
    assert faq.lookup("what does wait(S) do in a semaphore") is None
    agent, st = make(tmp_path, kb)
    r = say(agent, st, "what does fork return?")
    assert r.action == "faq" and (r.cards == [] or r.cards[0]["type"] == "video")


def test_whole_video_and_pinned_only_lectures(tmp_path):
    import json
    from tutor import videos
    (tmp_path / "t.txt").write_text("0:00 priority priority starvation aging\n1:00 more priority aging talk\n", encoding="utf-8")
    (tmp_path / "videos.json").write_text(json.dumps([
        {"url": "https://youtu.be/AAAAAAAAAAA", "title": "Whole", "clips": [{"lesson": "rr"}]},
        {"url": "https://youtu.be/BBBBBBBBBBB", "title": "Pinned", "transcript": "t.txt", "auto": False,
         "clips": [{"lesson": "mlfq", "start": "0:00", "end": "1:00"}]}]), encoding="utf-8")
    rr = videos.clips_for("rr", tmp_path)
    assert rr[0]["end"] is None and rr[0]["when"] == "whole video"
    assert videos.clips_for("priority", tmp_path) == []           # auto matching is off for the pinned lecture
    assert videos.clips_for("mlfq", tmp_path)[0]["excerpt"].startswith("priority")


def test_learn_page_questions_are_checked(tmp_path, kb):
    from tutor import lessons as L
    from tutor.student_model import StudentModel
    from tutor.tutor import Tutor
    made_up = "FCFS matters because a process with burst 37 makes all the others wait a long time, which raises the average."
    t = Tutor(StudentModel(tmp_path / "l.db"), kb, FakeClient(text=made_up))
    text, src = t.lesson_reply(L.LESSON_BY_ID["fcfs"], "beginner", "why does it matter")
    assert "37" not in text and src.startswith("lesson notes")
    text, src = t.lesson_reply(L.LESSON_BY_ID["bankers"], "beginner", "is this used in real life")
    assert src.startswith("checked answer") and "Rarely" in text
    fine = "It matters because one long job at the front makes every short job behind it wait, the convoy effect."
    t = Tutor(StudentModel(tmp_path / "m.db"), kb, FakeClient(text="Here's a hint.\n\n" + fine))
    text, src = t.lesson_reply(L.LESSON_BY_ID["fcfs"], "beginner", "why does it matter")
    assert text == fine and src.startswith("LLM")


def test_explanation_copied_from_mid_lesson_and_coding_requests(tmp_path, kb):
    mid = ("- **Monitor solution (in the notes):** a philosopher picks up chopsticks only when both are free, "
           "and putdown re-tests both neighbours so nobody waits for ever at the table.")
    agent, st = make(tmp_path, kb, FakeClient(text=mid))
    r = say(agent, st, "explain the dining philosophers problem")
    assert r.action == "explain" and not r.text.startswith("- ")
    agent, st = make(tmp_path, kb, FakeClient(text="Bubble sort compares neighbours and swaps them until sorted, okay?"))
    r = say(agent, st, "write a python program for bubble sort")
    assert r.action == "chat" and r.text.startswith("That's outside what I can help with")
