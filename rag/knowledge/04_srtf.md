---
topic: CPU Scheduling
subtopic: SRTF
source: Seed course notes
difficulty: Intermediate
---
# Shortest Remaining Time First (SRTF, preemptive SJF)

## Rule
SRTF always runs the arrived process with the shortest REMAINING burst time. Decisions happen when a process finishes and whenever a new process arrives. At each arrival, compare the new process's burst with the running process's remaining time; preempt only if the new one is strictly shorter. If they are equal, the running process continues.

## Worked idea
Processes P1(AT 0, BT 8), P2(AT 1, BT 4), P3(AT 2, BT 9), P4(AT 3, BT 5). At t=1, P2 (4) is shorter than P1's remaining 7, so P1 is preempted. P2 runs to t=5. Then P4 (5) beats P1 (7) and P3 (9). P1 runs from 10 to 17 and P3 from 17 to 26. Average waiting time is 6.5.

## Waiting time in preemptive schedules
Because a process can run in several pieces, waiting time is not just the time before its first run. Use WT = CT − AT − BT, which counts every wait. Response time is the wait before the first run only.

## Common student mistakes
Not re-checking when a process arrives (missed preemption); using the original burst instead of the remaining time; reading completion time from the end of the first piece instead of the last.
