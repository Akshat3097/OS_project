"""Learn mode: lessons, teach-back assessment and targeted questions."""
from tutor import lessons as L
from tutor import teachback as T


def test_every_idea_has_a_working_question():
    for lesson in L.LESSONS:
        assert lesson["real_life"] and lesson["ideas"]
        for idea in lesson["ideas"]:
            q = T.make_question(lesson, idea, seed=3)
            assert q["idea"] == idea["id"]


def test_keyword_rubric_and_target():
    lesson = L.LESSON_BY_ID["srtf"]
    a = T.assess(lesson, "SRTF is preemptive. When a new process arrives compare the remaining time and preempt "
                         "only if strictly shorter; if equal it continues.")
    assert a["ideas"]["preemptive"] == "clear" and a["ideas"]["strictly"] == "clear"
    assert a["target"] == "wt_pieces"


def test_misconception_detected():
    a = T.assess(L.LESSON_BY_ID["priority"], "In priority scheduling a higher number means higher priority.")
    assert "higher_number" in a["misconceptions"]


def test_question_answers_are_checked_by_engine():
    lesson = L.LESSON_BY_ID["srtf"]
    idea = next(i for i in lesson["ideas"] if i["id"] == "wt_pieces")
    q = T.make_question(lesson, idea, seed=11)
    from engine.generator import problem_from_dict
    r = problem_from_dict(q["problem"]).solve().results[q["pid"]]
    assert T.check_answer(q, r.waiting)["ok"]
    assert not T.check_answer(q, r.waiting + 1)["ok"]


def test_speech_mishearings_of_preempt_still_count():
    from tutor import teachback
    assert teachback.normalise("it preamps only if shorter") == "it preempts only if shorter"
    assert teachback.normalise("Pre-empt the running one") == "preempt the running one"


def test_nonsense_is_not_assessed_and_llm_cannot_credit_unmentioned_ideas(monkeypatch):
    """Found in a click-through: "f f f f …" (16 'words') was rated 4 of 5 ideas clear by the LLM judge."""
    from tutor import lessons as L
    from tutor import teachback
    assert not teachback.enough_to_assess(". f f f f f f f f f f  f f f f ff")
    assert not teachback.enough_to_assess("blah " * 20)
    assert teachback.enough_to_assess("Turnaround time is completion time minus arrival time and waiting time is "
                                      "turnaround minus the burst, read from the Gantt chart.")
    lesson = L.LESSON_BY_ID["basics"]
    generous = {"ideas": {i["id"]: "clear" for i in lesson["ideas"]}, "misconceptions": [], "did_well": "Great!",
                "gap": "", "source": "LLM judge (fake)"}
    monkeypatch.setattr(teachback, "llm_assess", lambda *a: {k: (dict(v) if isinstance(v, dict) else v) for k, v in generous.items()})
    client = type("C", (), {"available": lambda self: True})()
    junk = teachback.assess(lesson, "the weather is nice today and I like cricket and tea very much indeed my friend", client)
    assert all(v == "missing" for v in junk["ideas"].values()) and not junk["did_well"]
    real = teachback.assess(lesson, "Turnaround time is completion minus arrival, TAT = CT - AT, and waiting is TAT minus burst.", client)
    assert real["ideas"]["tat"] == "clear" and real["ideas"]["wt"] == "clear"
