# Teach-back judge: agreement with an examiner, 22 Oct 2026

37 labelled explanations (`eval/teachback_cases.py`) across 7 lessons: 7 full, 7 partial, 3 paraphrased, 9 with a
wrong belief, 7 keyword salad, 3 off-topic, 1 wrong rule. For every case and key idea the label says whether a fair
examiner would credit it; 164 decisions are scored. Run with `python -m eval.teachback_eval` on the laptop
(RTX 5070 Laptop, 8 GB; Ollama 0.40.6; temperature 0, fixed seed).

## Before and after

| Judge | Agrees with the examiner | Credits what was NOT said | Misses what WAS said | Wrong beliefs caught | Wrong beliefs invented | s / explanation |
|---|---|---|---|---|---|---|
| Keyword rubric (offline fallback) | 65% (106/164) | 49% (53/109) | 9% (5/55) | 20% (2/10) | 3 | 0.0 |
| os-tutor, ratings only (the judge until 22 Oct) | 47% (77/164) | 77% (84/109) | 5% (3/55) | 80% (8/10) | 16 | 2.2 |
| os-tutor, ratings only + keyword cap (22 Oct morning fix) | 73% (120/164) | 37% (40/109) | 7% (4/55) | 80% (8/10) | 16 | 2.2 |
| **llama3.1:8b, evidence quotes checked + keyword cap (now)** | **96% (157/164)** | **6% (6/109)** | **2% (1/55)** | 60% (6/10) | **0** | 4.3 |

## What changed

1. **Evidence quotes.** For every idea it credits, and every wrong belief it reports, the judge must quote the
   student's exact words. The code checks that the quote is really in the explanation (80% of its words) and is a
   statement rather than a list of terms (it contains a function word). No valid quote, no credit.
2. **Wrong beliefs must be on topic and consistent.** A reported wrong belief is dropped when its quote shares no
   keyword with the idea it contradicts ("the top two teams go to the final" is not a Round Robin misconception) or
   when the judge credited that same idea (it quoted one correct sentence as both).
3. **Keyword cap.** An idea none of whose keyword groups appear in the explanation is never credited.
4. **Nonsense gate.** Fewer than 15 real words (8 different) is not assessed at all.
5. **Judge model.** The plain instruct model judges better than the fine-tuned tutor once evidence is required
   (an intermediate run with the same prompt: llama3.1:8b 95% agreement, 7% misses; os-tutor 88%, 27% misses), so
   the teach-back judge is llama3.1:8b (`TUTOR_JUDGE_MODEL`) while the chat keeps os-tutor.

## Intermediate runs (same cases)

Evidence quotes for ideas only, before rule 2 (wrong beliefs needed no quote):

| Judge | Agrees | Credits NOT said | Misses | Wrong beliefs caught | Invented |
|---|---|---|---|---|---|
| os-tutor, evidence + cap | 95% (155/164) | 2% (2/109) | 13% (7/55) | 100% (10/10) | 26 |
| llama3.1:8b, evidence + cap | 96% (157/164) | 4% (4/109) | 5% (3/55) | 100% (10/10) | 16 |

Trade-off of rule 2: invented wrong beliefs fall from 16 to 0, and caught ones from 10 to 6. A missed wrong belief
is simply not mentioned (the idea is still not credited); an invented one tells a student who was right that they
are wrong, so the stricter rule is the better choice for a tutor.
