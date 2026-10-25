---
topic: CPU Scheduling
subtopic: SJF
source: Seed course notes
difficulty: Intermediate
---
# Shortest Job First (SJF, non-preemptive)

## Rule
Whenever the CPU becomes free, SJF picks the process with the shortest burst time among the processes that have already ARRIVED. A process that has not arrived yet cannot be chosen, even if its burst is shorter. Once a process starts, it runs to completion. Ties are broken by arrival order (FCFS).

## Why it is useful
When all processes are available at the same time, SJF gives the minimum possible average waiting time among non-preemptive schedules, because moving a short job ahead of a long one reduces the waiting time of the short job more than it increases the waiting time of the long one.

## Problems with SJF
The real length of the next CPU burst is not known in advance. Systems estimate it with exponential averaging: τ(n+1) = α·t(n) + (1 − α)·τ(n), where t(n) is the last actual burst and α (often 0.5) controls how much recent history counts. Long processes can also starve if short ones keep arriving.

## Common student mistakes
Choosing the globally shortest job even though it has not arrived yet; preempting a running process (that would be SRTF, not SJF); forgetting to use arrival order to break ties.
