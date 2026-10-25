"""Deadlock detection, checked against the worked examples in the Module 3 notes (slides 258–262) and the
Theory-folder deadlock problem (rag/sources/notes_module3_deadlocks.md)."""
from engine import deadlock

# Silberschatz / Module 3 slides: A has 7 instances, B 2, C 6
ALLOC = [[0, 1, 0], [2, 0, 0], [3, 0, 3], [2, 1, 1], [0, 0, 2]]
REQ = [[0, 0, 0], [2, 0, 2], [0, 0, 0], [1, 0, 0], [0, 0, 2]]


def test_notes_example_no_deadlock():
    r = deadlock.detect([0, 0, 0], ALLOC, REQ)
    assert not r["deadlock"] and len(r["sequence"]) == 5
    # the notes give <P0, P2, P3, P1, P4>; any valid order is accepted, and the notes' one must be valid
    assert deadlock.verify_order([0, 0, 0], ALLOC, REQ, ["P0", "P2", "P3", "P1", "P4"])
    assert deadlock.verify_order([0, 0, 0], ALLOC, REQ, r["sequence"])
    assert not deadlock.verify_order([0, 0, 0], ALLOC, REQ, ["P1", "P0", "P2", "P3", "P4"])


def test_notes_example_p2_asks_for_one_more_c():
    req = [row[:] for row in REQ]
    req[2] = [0, 0, 1]
    r = deadlock.detect([0, 0, 0], ALLOC, req)
    assert r["sequence"] == ["P0"] and r["deadlocked"] == ["P1", "P2", "P3", "P4"]   # "stops after P0"


THEORY = dict(processes=["P0", "P1", "P2", "P3"], resources={"R1": 2, "R2": 3, "R3": 3, "R4": 2},
              holds=[("P0", "R1", 1), ("P1", "R1", 1), ("P1", "R2", 1), ("P2", "R2", 1), ("P3", "R2", 1),
                     ("P0", "R3", 2), ("P3", "R4", 1), ("P2", "R4", 1)],
              wants=[("P1", "R1", 1), ("P0", "R2", 1), ("P3", "R1", 1), ("P3", "R2", 2), ("P0", "R3", 1), ("P2", "R3", 1)])


def test_theory_folder_problem():
    g = deadlock.analyse_graph(**THEORY)
    assert g["allocation"] == [[1, 0, 2, 0], [1, 1, 0, 0], [0, 1, 0, 1], [0, 1, 0, 1]]
    assert g["request"] == [[0, 1, 1, 0], [1, 0, 0, 0], [0, 0, 1, 0], [1, 2, 0, 0]]
    assert g["available"] == [0, 0, 1, 0]
    assert g["detection"]["sequence"] == ["P2", "P0", "P1", "P3"] and not g["deadlock"]
    assert ["P0", "R2", "P3", "R1"] in g["cycles"]                       # "e.g. P0 → R2 → P3 → R1 → P0"
    assert not g["single_instance"] and "does not mean deadlock" in g["why"]


def test_single_instance_cycle_is_a_deadlock():
    g = deadlock.analyse_graph(["P1", "P2"], {"R1": 1, "R2": 1}, holds=[("P1", "R1", 1), ("P2", "R2", 1)],
                               wants=[("P1", "R2", 1), ("P2", "R1", 1)])
    assert g["deadlock"] and g["detection"]["deadlocked"] == ["P1", "P2"]
    assert g["wait_for"] == [("P1", "P2"), ("P2", "P1")] and g["wait_for_cycles"] == [["P1", "P2"]]
    assert "one instance" in g["why"]


def test_no_cycle_no_deadlock_and_bad_input():
    g = deadlock.analyse_graph(["P1", "P2"], {"R1": 1}, holds=[("P1", "R1", 1)], wants=[("P2", "R1", 1)])
    assert g["cycles"] == [] and not g["deadlock"]
    assert g["detection"]["sequence"] == ["P1"] and g["detection"]["skipped"] == ["P2"]   # holds nothing: Finish starts true
    for holds in ([("P1", "R1", 2)], [("P9", "R1", 1)]):
        try:
            deadlock.analyse_graph(["P1", "P2"], {"R1": 1}, holds=holds, wants=[])
            assert False, "should have been rejected"
        except ValueError:
            pass


# ---------------------------------------------------------------------------- reading and answering it in the chat
DETECTION_TEXT = ("Is the system deadlocked?\nAllocation\nP0 0 1 0\nP1 2 0 0\nP2 3 0 3\nP3 2 1 1\nP4 0 0 2\n"
                  "Request\nP0 0 0 0\nP1 2 0 2\nP2 0 0 0\nP3 1 0 0\nP4 0 0 2\nAvailable 0 0 0")


def test_parse_detection_problem_both_layouts():
    from tutor.chat_parse import parse_bankers_problem, parse_detection_problem
    d = parse_detection_problem(DETECTION_TEXT)
    assert d["allocation"] == ALLOC and d["request"] == REQ and d["available"] == [0, 0, 0]
    side = ("Process Allocation Request\n" + "\n".join(f"P{k} {' '.join(map(str, a))} {' '.join(map(str, r))}"
                                                       for k, (a, r) in enumerate(zip(ALLOC, REQ))) + "\nAvailable = (0, 0, 0)")
    assert parse_detection_problem(side)["request"] == REQ
    assert parse_bankers_problem(DETECTION_TEXT) is None                 # not mistaken for Banker's
    assert parse_detection_problem("Allocation Max\nP0 0 1 0 7 5 3\nP1 2 0 0 3 2 2\nAvailable 3 3 2") is None


def test_chat_solves_a_pasted_detection_question(tmp_path, monkeypatch):
    import json
    from fastapi.testclient import TestClient
    import tutor.chat_store as store
    monkeypatch.setattr(store, "CHAT_DIR", tmp_path / "chats")
    from server import api
    monkeypatch.setattr(api, "students", api.StudentModel(tmp_path / "t.db"))
    monkeypatch.setattr(api, "chat_models", lambda: [])
    c = TestClient(api.app)
    cid = c.post("/api/chat/new", json={"sid": "d"}).json()["id"]
    r = c.post("/api/message", json={"sid": "d", "id": cid, "text": DETECTION_TEXT, "model": None})
    done = [json.loads(line) for line in r.text.splitlines() if line.strip()][-1]
    card = done["message"]["cards"][0]
    assert done["message"]["meta"]["action"] == "detect"
    assert card["kind"] == "detection" and card["verdict"].startswith("✅") and len(card["details"]["rows"]) == 5
    assert "No deadlock" in done["message"]["content"]
