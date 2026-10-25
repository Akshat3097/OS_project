# Chat model comparison, 22 Oct 2026 (laptop: RTX 5070 8 GB, Ollama 0.40.6)

Run with `python -m eval.chat_eval` (10 scheduling problems, 5 Banker's states, 10 course facts, 5 wrong answers to hint on).
The models answer on their own, without the OS Engine; in the app every number comes from the engine and the guard
checks the reply. Reply times include a ~2 s per-request delay from calling Ollama at "localhost" on Windows (fixed the
same morning; this run started before the fix).

| Metric | llama3.1:8b | os-tutor-prompt | os-tutor |
|---|---|---|---|
| Numerical: correct average WT | 0% (0/10) | 0% (0/10) | 40% (4/10) |
| Banker's: safe/unsafe correct | 60% (3/5) | 60% (3/5) | 60% (3/5) |
| Course facts (yes/no) correct | 60% (6/10) | 70% (7/10) | 90% (9/10) |
| Hint-first on a wrong answer | 0% (0/5) | 20% (1/5) | 20% (1/5) |
| Replies ending in a question | 0% | 53% | 57% |
| Average reply length (words) | 303 | 1078 | 154 |
| Average time per reply (s) | 11.8 | 30.1 | 32.5 |
