"""Lecture clips from YouTube transcripts: parsing both formats, finding the part about each topic, pinned clips,
and the clip appearing in the API and next to a chat explanation."""
import json

import pytest

from tutor import videos

# pasted from YouTube's "Show transcript" panel: a time, then the words
YOUTUBE = """0:00
hello everyone welcome to today's class
0:20
we will look at scheduling in general first
1:05
first come first serve FCFS runs processes in arrival order
1:30
the convoy effect happens with FCFS when a long job is first
2:10
now shortest remaining time first SRTF is the preemptive SJF
2:40
SRTF compares the remaining time of the running process with the new arrival
3:05
it will preempt only if the remaining time of the new one is strictly shorter
3:50
that is all about preemption with shortest remaining time
4:30
thank you see you next class"""

SRT = """1
00:00:01,000 --> 00:00:05,000
today deadlocks

2
00:00:05,000 --> 00:00:40,000
a deadlock needs mutual exclusion hold and wait no preemption and circular wait

3
00:00:40,000 --> 00:01:20,000
in a resource allocation graph a cycle with single instances means deadlock
"""


@pytest.fixture()
def folder(tmp_path):
    (tmp_path / "lecture1.txt").write_text(YOUTUBE, encoding="utf-8")
    (tmp_path / "lecture2.srt").write_text(SRT, encoding="utf-8")
    (tmp_path / "videos.json").write_text(json.dumps([
        {"url": "https://www.youtube.com/watch?v=abcdefghijk", "title": "Scheduling lecture", "transcript": "lecture1.txt"},
        {"url": "https://youtu.be/ABCDEFGHIJK", "title": "Deadlocks lecture", "transcript": "lecture2.srt",
         "clips": [{"lesson": "bankers", "start": "0:40", "end": "1:20"}]}]), encoding="utf-8")
    return tmp_path


def test_parsing_and_helpers():
    rows = videos.parse_transcript(YOUTUBE)
    assert rows[0] == (0, "hello everyone welcome to today's class") and rows[4][0] == 130
    srt = videos.parse_transcript(SRT)
    assert srt[1] == (5, "a deadlock needs mutual exclusion hold and wait no preemption and circular wait")
    assert videos.video_id("https://www.youtube.com/watch?v=abcdefghijk&t=30") == "abcdefghijk"
    assert videos.video_id("https://youtu.be/ABCDEFGHIJK") == "ABCDEFGHIJK"
    assert videos.seconds("1:02:03") == 3723 and videos.clock(190) == "3:10"


def test_each_lesson_gets_the_right_part(folder):
    srtf = videos.clips_for("srtf", folder)
    assert srtf and srtf[0]["video"] == "abcdefghijk" and 120 <= srtf[0]["start"] <= 130
    assert srtf[0]["end"] - srtf[0]["start"] <= videos.MAX_CLIP and "preempt" in srtf[0]["excerpt"]
    fcfs = videos.clips_for("fcfs", folder)
    assert fcfs and fcfs[0]["start"] < 120
    assert videos.clips_for("deadlock", folder)[0]["video"] == "ABCDEFGHIJK"
    pinned = videos.clips_for("bankers", folder)[0]                       # hand-pinned, even with no Banker's words
    assert (pinned["start"], pinned["end"], pinned["how"]) == (40, 80, "pinned")
    assert videos.clips_for("dining", folder) == []                       # nothing about it: no clip


def test_api_and_chat_card(folder, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import config
    import tutor.chat_store as store
    monkeypatch.setattr(config, "VIDEO_DIR", folder)
    monkeypatch.setattr(store, "CHAT_DIR", tmp_path / "chats")
    from server import api
    monkeypatch.setattr(api, "students", api.StudentModel(tmp_path / "t.db"))
    monkeypatch.setattr(api, "chat_models", lambda: [])
    c = TestClient(api.app)
    clip = c.get("/api/videos", params={"lesson": "srtf"}).json()["clips"][0]
    assert clip["video"] == "abcdefghijk" and clip["when"].startswith("2:")
    assert c.get("/api/videos", params={"lesson": "dining"}).json()["clips"] == []
    cid = c.post("/api/chat/new", json={"sid": "v"}).json()["id"]
    r = c.post("/api/message", json={"sid": "v", "id": cid, "text": "explain SRTF", "model": None})
    done = [json.loads(line) for line in r.text.splitlines() if line.strip()][-1]
    cards = [k for k in done["message"]["cards"] if k["type"] == "video"]
    assert cards and cards[0]["clips"][0]["video"] == "abcdefghijk"


def test_no_videos_folder_means_no_clips(tmp_path):
    assert videos.clips_for("srtf", tmp_path / "missing") == []
