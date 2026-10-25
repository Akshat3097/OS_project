# Chat model comparison, 23 Oct 2026: first vs second fine-tuning round

Run with `python -m eval.chat_eval` on the laptop (RTX 5070 Laptop 8 GB, Ollama 0.40.6): 10 scheduling problems
(average WT), 5 Banker's states (safe or not), 10 course facts (yes/no), 5 wrong answers to hint on. The models answer
on their own, without the OS Engine; in the app every number comes from the engine and replies are checked.

All models now run with the app's settings (output cap 600 tokens, repeat penalty 1.1), temperature 0, one model on
the GPU at a time. The 22 Oct run (`results_chat_2026-10-22.md`) had no output cap, so some replies looped (that is why
os-tutor-prompt averaged 1,078 words then).

| Metric | llama3.1:8b | os-tutor-prompt | os-tutor (round 1) | os-tutor-v2 (round 2) |
|---|---|---|---|---|
| Numerical: correct average WT | 0% (0/10) | 0% (0/10) | **50% (5/10)** | 20% (2/10) |
| Banker's: safe/unsafe correct | 100% (5/5) | 40% (2/5) | 80% (4/5) | 60% (3/5) |
| Course facts (yes/no) correct | 60% (6/10) | 80% (8/10) | **90% (9/10)** | **90% (9/10)** |
| Hint-first on a wrong answer | 0% (0/5) | 20% (1/5) | 20% (1/5) | 0% (0/5) |
| Replies ending in a question | 0% | 63% | 67% | 57% |
| Average reply length (words) | 283 | 96 | 147 | 148 |
| Average time per reply (s) | 11.8 | 5.3 | 9.2 | 4.6 |

## The same questions in student-style phrasing

Round 2 was trained to cope with informal, short, misspelt questions, so the numerical, Banker's and fact questions
were rewritten with the same rewriter as its training data (`qlora/student_style.py`, e.g. "quick doubt: solve using
FCFS: P1 AT=0 BT=1 … draw the gantt chart n give the avera…").

| Student-style | os-tutor (round 1) | os-tutor-v2 (round 2) |
|---|---|---|
| Numerical: correct average WT | 5/10 | 3/10 |
| Banker's: safe/unsafe correct | 3/5 | 3/5 |
| Course facts correct | 9/10 | 8/10 |

## Decision

The second round (1,580 examples, about a fifth of them student-style copies, 2 epochs instead of 1) did not improve
on the first, with clean or with student-style questions, so the app keeps **os-tutor** (round 1) as the default
model; os-tutor-v2 stays installed for comparison. A likely reason: the student-style copies repeat existing answers,
so a second epoch over them shifts weight toward phrasing rather than the worked solutions. With 5 to 10 questions per
row the differences are indicative, not conclusive.
