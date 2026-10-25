| Check | Result |
|---|---|
| Messages routed to the expected action (rules + keyword fallback, LLM off) | 100% (70/70) |
| Pasted problems read exactly (120 problems × 6 layouts) | 100% (720/720) |
| Correct typed answers marked correct (120 problems × 4 formats) | 100% (480/480) |
| Injected mistake (WT = TAT) found | 100% (240/240) |
| Leaking hints blocked by the guard, before / after the fix | 60% / 100% (495 replies) |
| Safe hints wrongly blocked, before / after the fix | 0% / 0% (198 replies) |
| Hidden value also in the problem data: leaking hints blocked | 80% (84/105) |
| Hidden value also in the problem data: safe hints wrongly blocked | 0% (0/84) |

Guard cases where the hidden value also appears in the problem data: 21. They are judged by context (the number next to the hidden quantity, e.g. "P2's waiting time is 4"); a leak that names no quantity, like "It should come out to 4.", cannot be told apart from the data.
