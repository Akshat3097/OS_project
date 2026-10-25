"""The chat-first tutor: parsing, routing, the problem → answer → hint flow, quiz, teach-back and the guards."""
import json

import pytest

from engine.generator import problem_from_dict
from rag.store import KnowledgeBase
from tutor import chat_parse as cp
from tutor.chat_agent import ChatAgent, new_state
from tutor.student_model import StudentModel


class FakeClient:
    """Stands in for Ollama: JSON for the router, canned text for replies."""
    model = "fake-llm"

    def __init__(self, route=None, text="Here is my explanation. What do you think happens next?"):
        self.route_json = route
        self.text = text
        self.calls = []

    def available(self):
        return True

    def chat(self, messages, options=None, fmt=None):
        self.calls.append(("chat", fmt, messages))
        if fmt == "json":
            return self.route_json if isinstance(self.route_json, str) else json.dumps(self.route_json or {})
        return self.text

    def chat_stream(self, messages, options=None):
        self.calls.append(("stream", None, messages))
        for w in self.text.split(" "):
            yield w + " "

    def embed(self, texts, model=None):
        raise RuntimeError("no embeddings in tests")


@pytest.fixture(scope="module")
def kb():
    k = KnowledgeBase()
    k.load_or_build()
    return k


def make(tmp_path, kb, client=None):
    agent = ChatAgent(StudentModel(tmp_path / "t.db"), kb, client)
    agent.raise_errors = True
    return agent, new_state("tester")


def say(agent, state, text, **kw):
    r = agent.respond(state, text, **kw)
    r.final()
    agent.commit(state, r)
    return r


# --------------------------------------------------------------------------- parsing
def test_parse_problems_in_common_layouts():
    p = cp.parse_scheduling_problem("Solve using SRTF: P1 AT=0 BT=8, P2 AT=1 BT=4, P3 AT=2 BT=9")
    assert [(x.pid, x.arrival, x.burst) for x in p["processes"]] == [("P1", 0, 8), ("P2", 1, 4), ("P3", 2, 9)]
    assert p["algorithms"] == ["SRTF"]
    p = cp.parse_scheduling_problem("Round robin with time quantum 2: P1(0,5), P2(1,3), P3(2,1).")
    assert p["quantum"] == 2 and p["algorithms"] == ["RR"] and p["processes"][2].burst == 1
    p = cp.parse_scheduling_problem("Process Burst Time Priority\nP1 10 3\nP2 1 1\nP3 2 4\nall arrive at time 0. "
                                    "Draw Gantt charts using SJF and non-preemptive priority")
    assert [(x.arrival, x.burst, x.priority) for x in p["processes"]] == [(0, 10, 3), (0, 1, 1), (0, 2, 4)]
    assert p["algorithms"] == ["SJF", "PRIORITY_NP"]
    p = cp.parse_scheduling_problem("Arrival times: 0, 2, 4 and burst times: 3, 6, 4. Use FCFS")
    assert [(x.pid, x.arrival, x.burst) for x in p["processes"]] == [("P1", 0, 3), ("P2", 2, 6), ("P3", 4, 4)]
    assert cp.detect_algorithms("non-preemptive SJF") == ["SJF"]
    assert cp.detect_algorithms("preemptive SJF") == ["SRTF"]


def test_answers_are_not_read_as_problems():
    assert cp.parse_scheduling_problem("P1: CT 5, TAT 5, WT 0; P2: CT 8, TAT 7, WT 4") is None
    assert cp.parse_scheduling_problem("Process CT TAT WT\nP1 5 5 0\nP2 8 7 4") is None


def test_parse_answers():
    pids = ["P1", "P2", "P3"]
    for text in ["P1 0-5, P2 5-8, P3 8-10", "| P1 | P2 | P3 |\n0 5 8 10", "0-5 P1, 5-8 P2, 8-10 P3"]:
        assert cp.parse_scheduling_answer(text, pids)["gantt"] == [("P1", 0, 5), ("P2", 5, 8), ("P3", 8, 10)]
    want = {"P1": {"CT": 5, "TAT": 5, "WT": 0}, "P2": {"CT": 8, "TAT": 7, "WT": 4}, "P3": {"CT": 10, "TAT": 8, "WT": 6}}
    for text in ["P1: CT 5, TAT 5, WT 0; P2: CT 8, TAT 7, WT 4; P3: CT 10, TAT 8, WT 6",
                 "Process CT TAT WT\nP1 5 5 0\nP2 8 7 4\nP3 10 8 6", "CT: 5, 8, 10\nTAT: 5 7 8\nWT = 0 4 6"]:
        assert cp.parse_scheduling_answer(text, pids)["metrics"] == want
    assert cp.parse_bankers_answer("safe: <P1, P3, P4, P0, P2>", 5) == {"safe": True, "sequence": ["P1", "P3", "P4", "P0", "P2"]}
    assert cp.parse_bankers_answer("it is unsafe", 5)["safe"] is False
    assert cp.parse_semaphore_answer("S = -1, blocked: P3", ["S"]) == {"final": {"S": -1}, "blocked": ["P3"]}
    assert cp.parse_semaphore_answer("mutex is 0 and no process is blocked", ["mutex"])["blocked"] == []


def test_parse_bankers_problem_both_layouts():
    sep = ("Allocation:\nP0 0 1 0\nP1 2 0 0\nP2 3 0 2\nMax:\nP0 7 5 3\nP1 3 2 2\nP2 9 0 2\nAvailable: 3 3 2")
    side = ("Process Allocation Max Available\nP0 0 1 0 7 5 3 3 3 2\nP1 2 0 0 3 2 2\nP2 3 0 2 9 0 2")
    for text in (sep, side):
        b = cp.parse_bankers_problem(text)
        assert b["allocation"] == [[0, 1, 0], [2, 0, 0], [3, 0, 2]]
        assert b["maximum"] == [[7, 5, 3], [3, 2, 2], [9, 0, 2]]
        assert b["available"] == [3, 3, 2]


# --------------------------------------------------------------------------- flows (LLM offline)
def _engine_answer(problem, wt_offset=0):
    res = problem.solve()
    chart = ", ".join(f"{s.pid} {s.start}-{s.end}" for s in res.gantt)
    vals = "; ".join(f"{p.pid}: CT {res.results[p.pid].completion}, TAT {res.results[p.pid].turnaround}, "
                     f"WT {res.results[p.pid].waiting + (wt_offset if i == 0 else 0)}"
                     for i, p in enumerate(problem.processes))
    return chart, vals


def test_practice_answer_in_two_parts_and_mastery(tmp_path, kb):
    agent, st = make(tmp_path, kb)
    r = say(agent, st, "give me a round robin problem")
    assert r.meta["action"] == "practice" and r.cards[0]["type"] == "problem"
    problem = problem_from_dict(st["problem"]["problem"])
    assert problem.algorithm == "RR"
    chart, vals = _engine_answer(problem)
    r = say(agent, st, chart)                                 # Gantt chart first
    assert r.meta["action"] == "check" and not st["problem"]["solved"]
    r = say(agent, st, vals)                                  # then the times: merged with the chart
    assert r.meta["action"] == "check" and st["problem"]["solved"]
    assert r.text.startswith("Correct")
    assert agent.students.history("tester")                    # the attempts were logged
    assert "Another one" in r.suggestions


def test_wrong_answer_gets_a_hint_and_hints_escalate(tmp_path, kb):
    agent, st = make(tmp_path, kb)
    say(agent, st, "give me an easy FCFS problem")
    problem = problem_from_dict(st["problem"]["problem"])
    chart, vals = _engine_answer(problem, wt_offset=problem.processes[0].burst)   # WT = TAT mistake for P1
    r = say(agent, st, chart + "\n" + vals)
    assert r.meta["action"] == "check" and not st["problem"]["solved"]
    assert r.cards[0]["analysis"]["errors"]
    for _ in range(3):
        r = say(agent, st, "give me a hint")
        assert r.meta["action"] == "hint"
    assert st["problem"]["hints"] == 3


def test_pasted_problem_offer_then_solution(tmp_path, kb):
    agent, st = make(tmp_path, kb)
    r = say(agent, st, "Process Arrival Burst\nP1 0 5\nP2 1 3\nP3 2 8")
    assert r.meta["action"] == "need_algorithm"
    r = say(agent, st, "SJF")
    assert r.meta["action"] == "offer" and st["problem"]["problem"]["algorithm"] == "SJF"
    r = say(agent, st, "Show me the full solution")
    assert r.meta["action"] == "reveal" and r.cards[0]["type"] == "solution"
    r = say(agent, st, "now solve it with round robin q=2")
    assert r.meta["action"] == "solve" and st["problem"]["problem"]["algorithm"] == "RR"
    assert st["problem"]["problem"]["quantum"] == 2


def test_pasted_problem_with_own_answer_is_checked(tmp_path, kb):
    agent, st = make(tmp_path, kb)
    r = say(agent, st, "FCFS: P1 AT=0 BT=5, P2 AT=1 BT=3. My answer: P1 0-5, P2 5-8, "
                       "P1: CT 5, TAT 5, WT 0; P2: CT 8, TAT 7, WT 4")
    assert r.meta["action"] == "pasted_check" and st["problem"]["solved"]


def test_bankers_and_semaphore_answers(tmp_path, kb):
    agent, st = make(tmp_path, kb)
    say(agent, st, "give me a banker's problem")
    eng = problem_from_dict(st["problem"]["problem"]).solve()
    r = say(agent, st, "what does safe state mean?")             # a question, not an answer
    assert r.meta["action"] == "ask"
    r = say(agent, st, ("safe: " + ", ".join(eng["sequence"])) if eng["safe"] else "unsafe")
    assert r.meta["action"] == "check" and st["problem"]["solved"]
    say(agent, st, "give me a semaphore problem")
    eng = problem_from_dict(st["problem"]["problem"]).solve()
    r = say(agent, st, ", ".join(f"{k} = {v}" for k, v in eng["final_values"].items()) + "; blocked: " +
            (", ".join(eng["blocked"]) or "none"))
    assert r.meta["action"] == "check" and st["problem"]["solved"]


def test_quiz_flow(tmp_path, kb):
    agent, st = make(tmp_path, kb)
    r = say(agent, st, "quiz me on deadlocks")
    assert r.meta["action"] == "quiz" and st["quiz"]["lesson"] == "deadlock"
    for _ in range(len(st["quiz"]["order"])):
        r = say(agent, st, "a")
        assert r.meta["action"] == "quiz_answer"
    assert st["quiz"] is None and "out of" in r.text
    assert agent.students.lesson_progress("tester")["deadlock"]["check_score"] is not None


def test_teachback_flow(tmp_path, kb):
    agent, st = make(tmp_path, kb)
    r = say(agent, st, "let me explain SRTF")
    assert r.meta["action"] == "teachback"
    r = say(agent, st, "SRTF always picks the process with the shortest remaining time and it is preemptive, "
                       "so a newly arrived shorter process takes the CPU")
    assert r.meta["action"] == "teachback_assess" and "✅" in r.text
    r = say(agent, st, "Explain the parts I missed")
    assert r.meta["action"] == "explain" and r.meta["style"] == "gaps"


def test_every_suggestion_is_understood_by_the_rules(tmp_path, kb):
    """Suggestion buttons must route without the LLM (fast and predictable)."""
    agent, st = make(tmp_path, kb)
    seen = set()
    for msg in ["hi", "explain round robin", "give me a problem", "Give me a hint", "Show me the solution",
                "quiz me on semaphores", "how am i doing?", "let me explain deadlocks",
                "A deadlock happens when processes wait for each other forever because of hold and wait"]:
        r = say(agent, st, msg)
        seen.update(r.suggestions)
    for s in seen:
        st2 = {**new_state("tester"), "problem": st["problem"], "topic": "rr", "last_gaps": ["an idea"]}
        route = agent._rules(st2, s)
        assert route is not None, s


def test_cards_are_json(tmp_path, kb):
    agent, st = make(tmp_path, kb)
    for msg in ["explain SRTF", "give me a problem", "Show me the solution", "how am i doing?", "quiz me on FCFS"]:
        say(agent, st, msg)
    json.dumps([{k: m.get(k) for k in ("content", "cards", "suggestions")} for m in st["messages"]])


# --------------------------------------------------------------------------- with an LLM
def test_llm_router_handles_free_phrasing(tmp_path, kb):
    agent, st = make(tmp_path, kb, FakeClient(route={"action": "practice", "topic": "rr", "difficulty": "hard"}))
    r = say(agent, st, "throw a tricky one at me on that time slice thing")
    assert r.meta["routed_by"] == "LLM" and r.meta["action"] == "practice"
    p = problem_from_dict(st["problem"]["problem"])
    assert p.algorithm == "RR" and p.difficulty == 3


def test_invalid_router_json_falls_back_to_keywords(tmp_path, kb):
    agent, st = make(tmp_path, kb, FakeClient(route="not json at all"))
    r = say(agent, st, "hmm the ready queue thing confuses me in srtf honestly")
    assert r.meta["routed_by"] in ("keywords", "rules")


def test_explain_streams_from_the_llm(tmp_path, kb):
    client = FakeClient(text="Think of a canteen queue: whoever comes first is served first. What happens when the counter is free?")
    agent, st = make(tmp_path, kb, client)
    r = agent.respond(st, "explain FCFS")
    assert r.stream is not None
    assert "".join(r.chunks()).strip() == client.text
    agent.commit(st, r)
    assert st["messages"][-1]["content"] == client.text


def test_hint_that_leaks_the_answer_is_blocked(tmp_path, kb):
    # FCFS: WT is P1 0, P2 4, P3 6. The student writes WT = TAT (14) for P3; the hidden correct value is 6.
    leak = "Your P3 waiting time should be 6."
    agent, st = make(tmp_path, kb, FakeClient(text=leak))
    say(agent, st, "FCFS: P1 AT=0 BT=5, P2 AT=1 BT=3, P3 AT=2 BT=8")
    r = say(agent, st, "P1 0-5, P2 5-8, P3 8-16. P1: CT 5, TAT 5, WT 0; P2: CT 8, TAT 7, WT 4; P3: CT 16, TAT 14, WT 14")
    assert r.meta["action"] == "check" and not st["problem"]["solved"]
    assert leak not in r.text and "blocked" in r.meta["source"]


def test_solution_narration_with_made_up_numbers_falls_back(tmp_path, kb):
    agent, st = make(tmp_path, kb, FakeClient(text="The average waiting time is 987.5, which you can read straight off the chart, easy!"))
    r = say(agent, st, "Solve using FCFS: P1 AT=0 BT=5, P2 AT=1 BT=3")
    assert "987" not in r.text and r.meta.get("blocked_text")


def test_parser_fixes_found_by_the_chat_checks():
    # priority given as the third value of a tuple, with "priority" only in the algorithm's name
    p = cp.parse_scheduling_problem("non-preemptive priority: P1(0,6,2), P2(2,2,5), P3(3,2,3)")
    assert [(x.arrival, x.burst, x.priority) for x in p["processes"]] == [(0, 6, 2), (2, 2, 5), (3, 2, 3)]
    # a bar-chart answer with an idle gap
    assert cp.parse_gantt_text("| P1 | idle | P2 |\n0 3 5 8") == [("P1", 0, 3), ("IDLE", 3, 5), ("P2", 5, 8)]


def test_chat_checks_run(tmp_path):
    from eval import chat_checks
    kb = KnowledgeBase()
    kb.load_or_build()
    agent = chat_checks._agent(tmp_path, kb)
    ok, n, misses = chat_checks.check_routing(agent)
    assert n == 70 and ok >= 68, misses


def test_small_talk_never_invents_a_past_or_a_topic():
    """Found in a click-through: the model answered "ni" with "Let's get back to Round Robin. You had a question…"."""
    from tutor.chat_agent import ASKS, _invents_context, resolve_topic
    st = {"topic": "basics"}
    assert _invents_context("Back to Round Robin: what happens when a slice ends?", "hola amigo", st)
    assert _invents_context("You were working on waiting time, remember?", "ni", st)
    assert not _invents_context("Hi! Want an explanation or a quick quiz?", "hola amigo", st)
    assert not _invents_context("Round robin gives each process a quantum.", "what is round robin", st)
    for unclear in ("ni", "ok", "hola amigo", "i see p1 p2 p3"):
        assert not resolve_topic(unclear)[0] and not ASKS.search(unclear), unclear


def test_general_chat_is_routed_as_chat_and_checked():
    """From a run of general messages: "solve 2x + 3 = 11" went to practice, "explain recursion" to the notes, and
    the model invented working ("WT = TAT − BT = 5 − 5 = 0") and a "mock CAT 2 paper on the course website"."""
    from tutor.chat_agent import Route, _in_scope, _invents_context
    assert _in_scope(Route("practice", by="LLM"), "can you help me with my maths homework? solve 2x + 3 = 11").action == "chat"
    assert _in_scope(Route("progress", by="LLM"), "I am really stressed about my exams").action == "chat"
    assert _in_scope(Route("ask"), "explain recursion").action == "chat"
    assert _in_scope(Route("ask"), "what is the convoy effect?").action == "ask"
    assert _in_scope(Route("ask"), "explain it again").action == "ask"                  # refers to the conversation
    st = {"topic": "fcfs"}
    assert _invents_context("You subtracted BT from TAT: WT = 5 - 5 = 0.", "no i am not", st)
    assert _invents_context("Look at the mock CAT 2 paper on the course website.", "I am stressed", st)
    assert not _invents_context("I run on Llama 3.1 8B, fine-tuned with QLoRA.", "what model are you?", st)
    assert not _invents_context("Paris. Can I help with CPU scheduling or process synchronization?", "capital of France?", st)


def test_what_else_can_you_teach_lists_the_topics(tmp_path):
    """From a click-through: "no not this one, what else can you teach me" got a long SJF explanation."""
    from rag.store import KnowledgeBase
    from tutor.chat_agent import ChatAgent, new_state
    from tutor.student_model import StudentModel
    agent = ChatAgent(StudentModel(tmp_path / "t.db"), KnowledgeBase(), None, use_llm=False)
    st = new_state("s")
    st["topic"] = "fcfs"
    for text in ("no not this one, what else can you teach me", "what topics do you cover", "something else"):
        assert agent.route(st, text).action == "menu", text
    assert agent.route(st, "what is SJF").action == "explain"
    reply = agent.respond(st, "what else can you teach me?")
    assert "Dining philosophers" in reply.text and "(where we are now)" in reply.text
    assert [agent.route(new_state("x"), s).action for s in reply.suggestions[:3]] == ["explain"] * 3
