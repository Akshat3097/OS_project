"""
Orchestrator: ties the OS Engine, error analysis, student model, teaching strategy,
RAG and the LLM together. This is the loop from the architecture diagram:

  student answer -> OS Engine verifies -> error analysis -> update student model
  -> teaching strategy -> (RAG notes + LLM phrasing, checked by the guard) -> feedback
"""
from __future__ import annotations

import re
import time
from collections.abc import Iterator

from rag.store import ALGO_TO_SUBTOPIC, KnowledgeBase
from tutor import prompts, strategy as strategy_mod
from tutor.error_analysis import analyse_bankers, analyse_scheduling, analyse_semaphore
from tutor.llm import OllamaClient
from tutor.student_model import StudentModel


class Tutor:
    def __init__(self, students: StudentModel, kb: KnowledgeBase, client: OllamaClient | None = None):
        self.students = students
        self.kb = kb
        self.client = client

    @property
    def llm_online(self) -> bool:
        return self.client is not None and self.client.available()

    # ------------------------------------------------------------------ checking
    def check(self, problem, answer: dict) -> dict:
        kind = getattr(problem, "kind", "scheduling")
        if kind == "scheduling":
            return analyse_scheduling(problem, answer.get("gantt"), answer.get("metrics"))
        if kind == "bankers":
            return analyse_bankers(problem, answer.get("need"), answer.get("safe"), answer.get("sequence"))
        if kind == "advanced":
            from tutor.error_analysis import analyse_advanced
            return analyse_advanced(problem, answer.get("metrics"))
        return analyse_semaphore(problem, answer.get("final", {}), answer.get("blocked", []))

    def submit(self, student_id: str, problem, problem_id: str, answer: dict, attempt_no: int, hints_used: int,
               revealed: bool, started_at: float) -> dict:
        analysis = self.check(problem, answer)
        changes = self.students.record_attempt(student_id, problem.to_dict(), problem_id, analysis, attempt_no,
                                               hints_used, revealed, time.time() - started_at)
        topic = problem.algorithm if getattr(problem, "kind", "scheduling") == "scheduling" else problem.kind.upper()
        strat = strategy_mod.decide(problem, analysis, self.students.level(student_id, topic),
                                    self.students.recurring_errors(student_id), attempt_no, hints_used)
        return {"analysis": analysis, "mastery_changes": changes, "strategy": strat}

    def hint(self, student_id: str, problem, analysis: dict | None, attempt_no: int, hints_used: int):
        topic = problem.algorithm if getattr(problem, "kind", "scheduling") == "scheduling" else problem.kind.upper()
        # attempt_no here = number of submissions so far; +1 because the hint itself is one more escalation step
        return strategy_mod.decide(problem, analysis, self.students.level(student_id, topic),
                                   self.students.recurring_errors(student_id), max(1, attempt_no), hints_used)

    # ------------------------------------------------------------------ feedback text
    # what to look up in the class notes for each Learn-mode lesson
    CLASS_NOTES_QUERY = {"basics": "scheduling criteria formulas turnaround waiting response time CPU utilisation",
                         "fcfs": "FCFS First Come First Serve FIFO convoy effect worked examples", "sjf": "SJF Shortest Job First worked examples",
                         "srtf": "SRTF preemptive SJF worked examples waiting time formula", "rr": "Round Robin time quantum ready queue",
                         "priority": "Priority scheduling smallest integer highest priority aging",
                         "critical_section": "critical-section problem mutual exclusion progress bounded waiting Peterson",
                         "semaphores": "Semaphores as defined in the Module 4 notes P V wait signal",
                         "bounded_buffer": "Classical problems bounded buffer semaphores mutex empty full producer consumer",
                         "readers_writers": "Readers-writers problem readcount mutex wrt",
                         "dining": "Dining philosophers chopstick semaphore monitor deadlock",
                         "deadlock": "four necessary conditions deadlock resource-allocation graph",
                         "bankers": "Banker's safety algorithm resource-request algorithm example"}

    def class_notes_for(self, lesson: dict, k: int = 2) -> list[dict]:
        """The teacher's own notes on a lesson topic (shown in Learn mode next to the lesson)."""
        q = self.CLASS_NOTES_QUERY.get(lesson["id"], f"{lesson['title']} {lesson['goal']}")
        return self.kb.search(q, k=k, client=self.client, types={"Teacher's notes"})

    def notes_for(self, strat) -> list[dict]:
        query = " ".join(f for f in strat.facts if f.startswith(("Likely misconception", "Detected error", "Rule")))
        return self.kb.search(query or strat.topic, k=2, client=self.client,
                              subtopic=ALGO_TO_SUBTOPIC.get(strat.topic))

    def feedback(self, strat, use_llm: bool = True) -> dict:
        notes = self.notes_for(strat)
        messages = prompts.feedback_messages(strat, notes)
        out = {"messages": messages, "notes": notes, "issues": [], "source": "template"}
        if use_llm and self.llm_online:
            try:
                t0 = time.time()
                text = self.client.chat(messages).strip()
                out["latency"] = time.time() - t0
                issues = prompts.check_response(text, strat)
                out["issues"] = issues
                out["llm_text"] = text
                if any(i["type"] == "revealed_answer" for i in issues):
                    out["text"] = prompts.template_response(strat)
                    out["source"] = "template (LLM reply blocked: it revealed the answer)"
                elif len(re.findall(r"[A-Za-z]{2,}", text)) < 18:
                    out["text"] = prompts.template_response(strat)
                    out["source"] = "template (LLM reply too short)"
                else:
                    out["text"] = text
                    out["source"] = f"LLM ({self.client.model})"
                return out
            except Exception as e:  # network / model errors -> still give feedback
                out["error"] = str(e)
        out["text"] = prompts.template_response(strat)
        return out

    # ------------------------------------------------------------------ free questions (RAG)
    def ask(self, question: str, level: str, history: list[dict] | None = None) -> tuple[Iterator[str] | str, list[dict]]:
        chunks = self.kb.search(question, k=3, client=self.client)
        if self.llm_online:
            msgs = prompts.qa_messages(question, chunks, level, history)
            return self.client.chat_stream(msgs), chunks
        if not chunks:
            return "I couldn't find this in the course notes, and the language model is offline.", chunks
        text = "The language model is offline, so here are the most relevant parts of the course notes:\n\n" + \
               "\n\n".join(f"**[{i}] {c['meta'].get('subtopic', '')} — {c['meta'].get('section', c['meta'].get('source', ''))}**\n{c['text'].split(': ', 1)[-1]}"
                           for i, c in enumerate(chunks, start=1))
        return text, chunks

    # ------------------------------------------------------------------ Learn mode
    def _lesson_answer(self, lesson: dict, level: str, notes: list[dict], question: str,
                       history: list[dict] | None) -> tuple[str, str]:
        """A student's own question on the Learn page. Answered by the plain instruct model (the teach-back judge, also
        on this page): on 24 Oct the fine-tuned model answered "why does anything matter?" with the summary line, "why
        can't I use a normal variable?" with the whole lesson, and made up an FCFS example with wrong sums. Checked
        before it is shown: no leaked prompt, and no number that is not in the lesson, the notes or the question."""
        import re
        from tutor import teachback
        from tutor.chat_agent import clean_reply, substantial
        fallback = "Here is the part of the lesson that answers this best:\n\n" + lesson["concept"].strip()
        client = teachback.judge_client(self.client)
        try:
            text = clean_reply(client.chat(prompts.lesson_messages(lesson, level, notes, question, history)))
        except Exception:
            return fallback, "lesson notes (LLM failed)"
        known = " ".join([lesson["concept"], lesson.get("alt", ""), " ".join(lesson["summary"]), question] +
                         [n["text"] for n in notes])
        allowed = set(re.findall(r"\d+(?:\.\d+)?", known))
        if not substantial(text) or any(n not in allowed for n in re.findall(r"\d+(?:\.\d+)?", text)):
            return fallback, f"lesson notes (the {client.model} reply was too short or used numbers not in the lesson)"
        return text, f"LLM ({client.model})"

    def lesson_reply(self, lesson: dict, level: str, question: str | None = None,
                     history: list[dict] | None = None) -> tuple[Iterator[str] | str, str]:
        """Re-explain a lesson (question=None) or answer a question about it. Returns (text or stream, source)."""
        from rag.store import ALGO_TO_SUBTOPIC
        from tutor import faq
        from tutor.chat_agent import clean_stream
        known = faq.lookup(question) if question else None
        if question and not known:
            near = faq.lookup(f"{question} ({lesson['title']})")
            known = near if near and near["lesson"] == lesson["id"] else None
        if known:
            return known["text"], "checked answer (tutor/faq.py)"
        sub = ALGO_TO_SUBTOPIC.get(lesson.get("practice_topic") or "")
        notes = self.kb.search(question or lesson["title"], k=2, client=self.client, subtopic=sub)
        if self.llm_online and question is None:
            return clean_stream(self.client.chat_stream(prompts.lesson_messages(lesson, level, notes, None, history)),
                                lesson["alt"]), f"LLM ({self.client.model})"
        if self.llm_online:
            return self._lesson_answer(lesson, level, notes, question, history)
        if question is None:
            return lesson["alt"], "prepared explanation (LLM offline)"
        if not notes:
            return "The language model is offline and the notes don't cover this. Try the Ask the tutor tab.", "offline"
        return ("The language model is offline, so here is the most relevant part of the course notes:\n\n"
                + notes[0]["text"].split(": ", 1)[-1]), "course notes (LLM offline)"

