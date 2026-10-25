"""
Past-paper theory questions through the whole chat, once with each model, written side by side for a person to read.
The questions follow the themes of the BCSE303 CAT papers (rag/sources/pyq_bcse303_*.md) and the class notes.

    python -m eval.pyq_compare                                   # os-tutor and llama3.1:8b
    python -m eval.pyq_compare --models os-tutor

Writes eval/logs/pyq_compare.md. Each question is a fresh chat, so the answers don't depend on each other.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

from rag.store import KnowledgeBase
from tutor.chat_agent import ChatAgent, new_state
from tutor.llm import OllamaClient
from tutor.student_model import StudentModel

OUT = Path(__file__).resolve().parent / "logs" / "pyq_compare.md"

QUESTIONS = [
    # CPU scheduling
    "Why do context switches reduce efficiency in Round Robin?",
    "What happens if the time quantum is very small?",
    "Why is SJF difficult to implement in a real operating system?",
    "How is the length of the next CPU burst predicted?",
    "When does the CPU scheduler have to make a decision?",
    "What is the difference between turnaround time and response time?",
    "What is a dispatcher and what is dispatch latency?",
    "Why does SRTF give a lower average waiting time than SJF?",
    "How is waiting time calculated when a process also does I/O?",
    "Compare FCFS, SJF and Round Robin for an interactive system.",
    "How does multilevel queue scheduling work?",
    "What is the difference between CPU-bound and I/O-bound processes?",
    # synchronization
    "Explain Peterson's solution. Does it work for more than two processes?",
    "How does the Bakery algorithm work?",
    "Why does counter++ give wrong results when two threads run it without a lock?",
    "What is the difference between a binary semaphore and a counting semaphore?",
    "How can semaphores make process P2 run statement S2 only after P1 has run S1?",
    "In producer-consumer, why must the producer call wait(empty) before wait(mutex)?",
    "In the first readers-writers problem, which processes can starve and why?",
    "How can deadlock be avoided in the dining philosophers problem?",
    "What is a monitor and how is it different from a semaphore?",
    "What is busy waiting, and when is a spinlock acceptable?",
    "How would you use a semaphore to allow at most 10 users into a database at once?",
    # deadlocks
    "What are the four necessary conditions for deadlock?",
    "What is the difference between deadlock prevention and deadlock avoidance?",
    "Can two processes that each need at most 2 of 3 identical resources deadlock?",
    "How can a system recover from a deadlock?",
    "In the resource-request algorithm, why is Request compared with Need first?",
    "What is a wait-for graph and when can it be used?",
    "How can the circular wait condition be prevented?",
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", default=["os-tutor", "llama3.1:8b"])
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="pyq_"))
    kb = KnowledgeBase()
    answers: dict[str, list[tuple[str, str, float, str]]] = {}
    for model in a.models:                      # one model at a time: no swapping between questions
        client = OllamaClient(model=model)
        if not client.available():
            sys.exit("Ollama is not running: start it with start.bat")
        students = StudentModel(tmp / f"{model.replace(':', '_')}.db")
        rows = []
        for q in QUESTIONS:
            agent = ChatAgent(students, kb, client, use_llm=True)
            state = new_state("Teacher")
            t0 = time.time()
            reply = agent.respond(state, q)
            text = "".join(reply.chunks()).strip()
            rows.append((reply.action, reply.meta.get("source", "?"), time.time() - t0, text))
            print(f"[{model}] {q[:60]!r} -> {reply.action} ({rows[-1][2]:.1f}s)", flush=True)
        answers[model] = rows
    lines = [f"# Past-paper theory questions · {time.strftime('%Y-%m-%d %H:%M')}\n"]
    for i, q in enumerate(QUESTIONS):
        lines.append(f"\n## {i + 1}. {q}\n")
        for model in a.models:
            action, source, took, text = answers[model][i]
            lines.append(f"**{model}** · `{action}` · {source} · {took:.1f}s\n\n{text}\n")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
