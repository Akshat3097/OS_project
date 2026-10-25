"""
OS Tutor web server: a small FastAPI app around the chat agent, serving the React page from web/dist.

    python -m server                 # opens http://127.0.0.1:8000 in your browser

Endpoints (all JSON; the message endpoint streams one JSON object per line):
  GET  /api/status                  Ollama online?, models, notes index
  GET  /api/chats?sid=              saved conversations of a student
  GET  /api/chat?sid=&id=           one conversation (the most recent when id is omitted)
  POST /api/chat/new                start a new conversation
  DELETE /api/chat?sid=&id=         delete a conversation
  POST /api/message                 send a message; streams {"type": "delta"} pieces, then {"type": "done"}

Learn mode (server/learn.py builds the JSON):
  GET  /api/learn/lessons?sid=      the lessons with the student's progress and the suggested one
  GET  /api/learn/lesson?sid=&id=   one lesson: text, worked example step by step, quiz
  POST /api/learn/stage             remember the furthest stage reached
  GET  /api/learn/notes?id=         what the class notes say about the lesson topic
  POST /api/learn/explain           "explain it differently" or a question about the lesson (streams like /api/message)
  GET  /api/learn/try?id=           a new guided-practice problem;  POST /api/learn/try/check marks a CT/TAT/WT table
  POST /api/learn/teachback         assess the student's own explanation
  POST /api/learn/question          the next question on the weakest idea;  POST /api/learn/answer checks it
  POST /api/learn/pointers          what went well, what to add, what next (marks the lesson done)
  POST /api/labs/{scheduler,bankers,semaphores,deadlocks,parse}, GET /api/labs/presets, /api/labs/random?kind=   Labs
  POST /api/exam/start, GET /api/exam?id=, POST /api/exam/submit   a timed mock CAT paper, auto-marked
  GET  /api/progress?sid=           the progress dashboard (mastery, recent attempts, mistakes, what next)
  GET  /api/speech                  is offline speech-to-text installed?;  POST /api/transcribe (audio body) → text
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from rag.store import KnowledgeBase
from server import exam, labs, learn, progress
from server.cards import form_spec, hydrate
from tutor import lessons as L
from tutor import speech
from tutor import teachback as TB
from tutor import videos
from tutor.chat_agent import ChatAgent
from tutor import note_store
from tutor.chat_store import delete_chat, list_chats, load_chat, new_chat, save_chat
from tutor.llm import OllamaClient
from tutor.student_model import StudentModel
from tutor.tutor import Tutor

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"
PREFERRED_MODELS = ("os-tutor", "os-tutor-prompt", config.DEFAULT_MODEL)

app = FastAPI(title="OS Tutor", version="1.0")


def _warm_speech() -> None:
    """Load the speech model in the background at start-up, so the first recording doesn't wait for it."""
    if speech.available():
        try:
            speech._load()
        except Exception:
            pass                     # not downloaded or broken: /api/transcribe reports it when it is used


threading.Thread(target=_warm_speech, daemon=True).start()
students = StudentModel()
kb = KnowledgeBase()
kb.load_or_build()
teachbacks = learn.TeachbackSessions()
exams = exam.Exams()
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_speech_lock = threading.Lock()


def _lock(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def chat_models() -> list[str]:
    return [m for m in OllamaClient().list_models() if "embed" not in m]


def default_model(models: list[str]) -> str | None:
    for pref in PREFERRED_MODELS:
        for m in models:
            if m.split(":")[0] == pref.split(":")[0]:
                return m
    return models[0] if models else None


def view(state: dict) -> dict:
    """The conversation as the page needs it: messages with cards drawn as data, plus the answer form."""
    msgs = state["messages"]
    out = []
    for i, m in enumerate(msgs):
        last = i == len(msgs) - 1
        item = {"role": m["role"], "content": m.get("content", "")}
        if m["role"] == "assistant":
            item["cards"] = [c for c in (hydrate(card, active=last and bool(state.get("quiz"))) for card in m.get("cards") or []) if c]
            item["suggestions"] = m.get("suggestions") or []
            item["meta"] = m.get("meta") or {}
        out.append(item)
    return {"id": state["id"], "title": state.get("title", "New chat"), "messages": out, "form": form_spec(state)}


def _with_welcome(state: dict) -> dict:
    if not state["messages"]:
        state["messages"].append(ChatAgent(students, kb, None, use_llm=False).welcome(state))
    return state


# ============================================================================ API
@app.get("/api/status")
def status():
    models = chat_models()
    return {"online": bool(models), "models": models, "default_model": default_model(models),
            "notes": {"chunks": len(kb.chunks), "mode": kb.mode}}


@app.get("/api/chats")
def chats(sid: str):
    return list_chats(sid)


@app.get("/api/chat")
def get_chat(sid: str, id: str | None = None):
    return view(_with_welcome(load_chat(sid, id)))


class NewChat(BaseModel):
    sid: str


@app.post("/api/chat/new")
def create_chat(body: NewChat):
    return view(_with_welcome(new_chat(body.sid)))


@app.delete("/api/chat")
def remove_chat(sid: str, id: str):
    delete_chat(sid, id)
    return {"ok": True}


class Message(BaseModel):
    sid: str
    id: str | None = None
    text: str = ""
    structured: dict | None = None
    model: str | None = None
    use_llm: bool = True


@app.post("/api/message")
def message(body: Message):
    if not body.text.strip() and body.structured is None:
        raise HTTPException(400, "empty message")

    def run():
        with _lock(f"{body.sid}/{body.id}"):
            state = _with_welcome(load_chat(body.sid, body.id))
            if body.id and state["id"] != body.id:
                state["id"] = body.id
            client = OllamaClient(model=body.model) if body.model else None
            agent = ChatAgent(students, kb, client, use_llm=body.use_llm and client is not None)
            yield json.dumps({"type": "start", "chat": {"id": state["id"]}}) + "\n"
            try:
                reply = agent.respond(state, body.text, body.structured)
                yield json.dumps({"type": "meta", "meta": reply.meta}) + "\n"
                for piece in reply.chunks():
                    yield json.dumps({"type": "delta", "text": piece}) + "\n"
                agent.commit(state, reply)
            except Exception as e:  # report instead of cutting the stream
                yield json.dumps({"type": "error", "text": f"{type(e).__name__}: {e}"}) + "\n"
                return
            save_chat(state)
            v = view(state)
            yield json.dumps({"type": "done", "message": v["messages"][-1], "form": v["form"],
                              "chat": {"id": state["id"], "title": state["title"]}}) + "\n"

    return StreamingResponse(run(), media_type="application/x-ndjson")


# ============================================================================ Learn mode
def _lesson(lid: str) -> dict:
    lesson = L.LESSON_BY_ID.get(lid)
    if not lesson:
        raise HTTPException(404, f"no lesson called {lid!r}")
    return lesson


def _client(model: str | None, use_llm: bool = True) -> OllamaClient | None:
    return OllamaClient(model=model) if model and use_llm else None


@app.get("/api/learn/lessons")
def learn_lessons(sid: str):
    return learn.lesson_list(students.lesson_progress(sid), students.recurring_errors(sid))


@app.get("/api/learn/lesson")
def learn_lesson(sid: str, id: str):
    return learn.lesson_view(_lesson(id), students.lesson_progress(sid).get(id))


class LessonRef(BaseModel):
    sid: str
    lesson: str


class Stage(LessonRef):
    stage: int


@app.post("/api/learn/stage")
def learn_stage(body: Stage):
    _lesson(body.lesson)
    students.update_lesson(body.sid, body.lesson, stage=max(0, min(body.stage, len(L.STAGES) - 1)))
    return {"ok": True}


@app.get("/api/learn/notes")
def learn_notes(id: str, model: str | None = None):
    return learn.notes_view(Tutor(students, kb, _client(model)).class_notes_for(_lesson(id)))


class Explain(LessonRef):
    question: str | None = None
    history: list[dict] = []
    model: str | None = None
    use_llm: bool = True


@app.post("/api/learn/explain")
def learn_explain(body: Explain):
    lesson = _lesson(body.lesson)
    tutor = Tutor(students, kb, _client(body.model, body.use_llm))

    def run():
        try:
            reply, source = tutor.lesson_reply(lesson, students.overall_level(body.sid), body.question,
                                               body.history[-6:] or None)
            for piece in ([reply] if isinstance(reply, str) else reply):
                yield json.dumps({"type": "delta", "text": piece}) + "\n"
            yield json.dumps({"type": "done", "source": source}) + "\n"
        except Exception as e:  # Ollama stopped half-way: send the prepared explanation instead
            yield json.dumps({"type": "error", "text": f"{type(e).__name__}: {e}", "fallback": lesson["alt"]}) + "\n"

    return StreamingResponse(run(), media_type="application/x-ndjson")


@app.get("/api/learn/try")
def learn_try(id: str, seed: int | None = None):
    out = learn.try_view(_lesson(id), seed)
    if out is None:
        raise HTTPException(404, "this lesson has no guided practice")
    return out


class MetricsCheck(BaseModel):
    problem: dict
    metrics: dict


@app.post("/api/learn/try/check")
def learn_try_check(body: MetricsCheck):
    return learn.check_metrics(body.problem, body.metrics)


class Teachback(LessonRef):
    text: str
    model: str | None = None
    use_llm: bool = True


@app.post("/api/learn/teachback")
def learn_teachback(body: Teachback):
    lesson = _lesson(body.lesson)
    text = body.text.strip()
    if not TB.enough_to_assess(text):
        raise HTTPException(400, "That doesn't look like an explanation yet. Say a little more in your own words "
                                 "(at least 15 real words).")
    a = TB.assess(lesson, text, _client(body.model, body.use_llm))
    row = students.record_teachback(body.sid, lesson["id"], text, a)
    teachbacks.start(body.sid, lesson["id"], text, a, row)
    students.update_lesson(body.sid, lesson["id"], check_score=a["score"])
    return learn.assessment_view(lesson, a)


@app.post("/api/learn/question")
def learn_question(body: LessonRef):
    return teachbacks.next_question(body.sid, _lesson(body.lesson))


class Answer(LessonRef):
    answer: str | int | float | list | None = None


@app.post("/api/learn/answer")
def learn_answer(body: Answer):
    if body.answer is None or body.answer == "":
        raise HTTPException(400, "choose an answer first")
    try:
        return teachbacks.answer(body.sid, _lesson(body.lesson), body.answer)
    except LookupError:
        raise HTTPException(409, "there is no open question; ask for one first")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/learn/pointers")
def learn_pointers(body: LessonRef):
    lesson = _lesson(body.lesson)
    tb = teachbacks.get(body.sid, lesson["id"]) or teachbacks.skip(body.sid, lesson)
    results = teachbacks.results(tb)
    if tb.get("row"):
        students.update_teachback_questions(tb["row"], results)
    if results:
        students.update_lesson(body.sid, lesson["id"], try_score=sum(r["ok"] for r in results) / len(results))
    students.update_lesson(body.sid, lesson["id"], completed=1, stage=len(L.STAGES) - 1)
    return learn.pointers_view(lesson, tb, results)


# ============================================================================ Labs
def _lab(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except labs.LabError as e:
        raise HTTPException(400, str(e))


@app.get("/api/labs/presets")
def labs_presets():
    return labs.PRESETS


@app.get("/api/labs/random")
def labs_random(kind: str):
    makers = {"scheduler": labs.random_scheduler, "bankers": labs.random_bankers, "semaphores": labs.random_semaphores}
    if kind not in makers:
        raise HTTPException(404, "unknown lab")
    return makers[kind]()


class SchedulerLab(BaseModel):
    processes: list[list]
    quantum: int | None = 2
    lower_is_higher: bool = True


@app.post("/api/labs/scheduler")
def labs_scheduler(body: SchedulerLab):
    return _lab(labs.scheduler, body.processes, body.quantum, body.lower_is_higher)


class BankersLab(BaseModel):
    available: list
    maximum: list[list]
    allocation: list[list]
    resources: list[str] | None = None
    request: dict | None = None


@app.post("/api/labs/bankers")
def labs_bankers(body: BankersLab):
    return _lab(labs.bankers_lab, body.available, body.maximum, body.allocation, body.resources, body.request)


class SemaphoresLab(BaseModel):
    initial: dict
    ops: list[list]


@app.post("/api/labs/semaphores")
def labs_semaphores(body: SemaphoresLab):
    return _lab(labs.semaphores_lab, body.initial, body.ops)


class DeadlocksLab(BaseModel):
    processes: list[str]
    resources: list[list]
    edges: list[list]


@app.post("/api/labs/deadlocks")
def labs_deadlocks(body: DeadlocksLab):
    return _lab(labs.deadlocks_lab, body.processes, body.resources, body.edges)


class PastedProblem(BaseModel):
    text: str


@app.post("/api/labs/parse")
def labs_parse(body: PastedProblem):
    return _lab(labs.parse, body.text)


# ============================================================================ Exam mode
class ExamStart(BaseModel):
    sid: str


@app.post("/api/exam/start")
def exam_start(body: ExamStart):
    return exams.start(body.sid)


@app.get("/api/exam")
def exam_get(id: str):
    try:
        e = exams.get(id)
    except exam.ExamError as err:
        raise HTTPException(404, str(err))
    return {**exam.public_view(e), "result": e["result"]}


class ExamSubmit(BaseModel):
    id: str
    answers: dict


@app.post("/api/exam/submit")
def exam_submit(body: ExamSubmit):
    try:
        return exams.submit(body.id, body.answers, students)
    except exam.ExamError as err:
        raise HTTPException(404, str(err))


@app.get("/api/videos")
def lecture_clips(lesson: str):
    """The lecture clips for a lesson (YouTube, cued to the right seconds); empty when videos/ has none."""
    return {"clips": videos.clips_for(lesson)}


@app.get("/api/progress")
def progress_view(sid: str):
    return progress.dashboard(students, sid)


# ============================================================================ Notes (the student's own)
class NoteIn(BaseModel):
    sid: str
    text: str
    title: str = ""
    color: str | None = None
    source: str = ""


class NoteChange(BaseModel):
    sid: str
    text: str | None = None
    title: str | None = None
    color: str | None = None
    pinned: bool | None = None


@app.get("/api/notes")
def notes_list(sid: str):
    return {"notes": note_store.list_notes(sid), "colors": list(note_store.COLORS)}


@app.post("/api/notes")
def notes_add(body: NoteIn):
    try:
        return note_store.add_note(body.sid, body.text, body.title, body.color, body.source)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.put("/api/notes/{note_id}")
def notes_change(note_id: str, body: NoteChange):
    try:
        return note_store.update_note(body.sid, note_id, text=body.text, title=body.title, color=body.color,
                                      pinned=body.pinned)
    except KeyError:
        raise HTTPException(404, "no such note")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/notes/{note_id}")
def notes_delete(note_id: str, sid: str):
    try:
        note_store.delete_note(sid, note_id)
    except KeyError:
        raise HTTPException(404, "no such note")
    return {"ok": True}


@app.get("/api/speech")
def speech_status():
    return {"available": speech.available(), "model": config.WHISPER_MODEL}


@app.post("/api/transcribe")
async def transcribe(request: Request, lesson: str | None = None):
    if not speech.available():
        raise HTTPException(503, "Speech-to-text isn't installed. Run: .venv\\Scripts\\python -m pip install faster-whisper")
    audio = await request.body()
    if len(audio) < 1000:
        raise HTTPException(400, "The recording is empty. Check that the browser may use the microphone.")
    kind = request.headers.get("content-type", "audio/webm")
    suffix = next((s for t, s in (("webm", ".webm"), ("ogg", ".ogg"), ("mp4", ".mp4"), ("wav", ".wav")) if t in kind), ".webm")

    lesson_info = L.LESSON_BY_ID.get(lesson or "")
    hint = lesson_info["title"] + "." if lesson_info else ""      # sentences here get "continued" on unclear audio

    def run() -> dict:
        with _speech_lock:                      # one Whisper model, one transcription at a time
            return speech.transcribe_checked(audio, suffix=suffix, hint=hint)

    from starlette.concurrency import run_in_threadpool
    try:
        return await run_in_threadpool(run)    # {text, unsure, reason, seconds, rms_db, peak_db}
    except Exception as e:  # model download failed, unreadable audio, ...
        raise HTTPException(500, f"Speech-to-text failed ({type(e).__name__}: {e}). You can type instead.")


# ============================================================================ the React page
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def page(path: str):
        f = DIST / path
        if path and f.is_file() and DIST in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
