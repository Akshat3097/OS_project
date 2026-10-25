"""Labs: all six algorithms on one problem, Banker's safety and requests, semaphore timelines, pasted questions."""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client():
    from server import api
    return TestClient(api.app)


def test_scheduler_lab_textbook(client):
    p = client.get("/api/labs/presets").json()["scheduler"][0]
    r = client.post("/api/labs/scheduler", json={"processes": p["processes"], "quantum": p["quantum"]}).json()
    wt = {x["algorithm"]: x["avg_wt"] for x in r["runs"]}
    assert len(wt) == 6 and wt["SRTF"] == 6.5                    # Silberschatz: SRTF average WT 6.5
    assert "SRTF" in r["best"] and r["span"] == 26
    assert all(x["gantt"]["segments"][-1][2] <= r["span"] for x in r["runs"])


@pytest.mark.parametrize("rows, msg", [([["P1", 0, 0]], "burst"), ([["P1", "x", 3]], "whole numbers"),
                                        ([["P1", 0, 3], ["P1", 1, 2]], "Duplicate")])
def test_scheduler_lab_rejects_bad_input(client, rows, msg):
    r = client.post("/api/labs/scheduler", json={"processes": rows, "quantum": 2})
    assert r.status_code == 400 and msg in r.json()["detail"]


def test_bankers_lab_safe_unsafe_and_request(client):
    safe, unsafe = client.get("/api/labs/presets").json()["bankers"]
    keys = ("available", "maximum", "allocation", "resources")
    r = client.post("/api/labs/bankers", json={**{k: safe[k] for k in keys}, "request": {"pid": 1, "vector": [1, 0, 2]}}).json()
    assert r["walk"]["sequence"] == ["P1", "P3", "P4", "P0", "P2"] and r["request"]["granted"]
    u = client.post("/api/labs/bankers", json={k: unsafe[k] for k in keys}).json()["walk"]
    assert not u["safe"] and [s["chosen"] for s in u["steps"]] == ["P1", "P3"] and u["stuck"] == ["P0", "P2", "P4"]
    bad = client.post("/api/labs/bankers", json={**{k: safe[k] for k in keys}, "request": {"pid": 0, "vector": [9, 9, 9]}}).json()
    assert not bad["request"]["granted"] and bad["request"]["reason"] == "exceeds_need"


def test_semaphore_lab_producer_consumer(client):
    pc = client.get("/api/labs/presets").json()["semaphores"][2]
    r = client.post("/api/labs/semaphores", json={"initial": pc["initial"], "ops": pc["ops"]}).json()
    b = r["blocking"]
    assert b["steps"][0]["effect"] == "C blocks (full < 0)" and b["lanes"]["C"][1] == "blocked"
    assert b["final"] == {"mutex": 1, "empty": -1, "full": 2} and b["blocked"] == ["P"]
    assert r["busy_wait"]["final"]["empty"] == 0 and r["busy_wait"]["lanes"]["C"][1] == "spinning"
    assert client.post("/api/labs/semaphores", json={"initial": {"S": 1}, "ops": [["P1", "wait", "T"]]}).status_code == 400


def test_parse_and_random(client):
    p = client.post("/api/labs/parse", json={"text": "Round robin with q = 2: P1(0,5), P2(1,3), P3(2,1)"}).json()
    assert p["kind"] == "scheduler" and p["quantum"] == 2 and p["processes"][1] == ["P2", 1, 3, 0]
    assert client.post("/api/labs/parse", json={"text": "hello"}).status_code == 400
    for kind in ("scheduler", "bankers", "semaphores"):
        assert client.get("/api/labs/random", params={"kind": kind}).status_code == 200
