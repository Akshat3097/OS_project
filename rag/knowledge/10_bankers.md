---
topic: Process Synchronization
subtopic: Banker's algorithm
source: Seed course notes
difficulty: Advanced
---
# Banker's algorithm

## Data structures
For n processes and m resource types: Available[m] (free instances), Max[n][m] (maximum each process may claim), Allocation[n][m] (currently held) and Need[n][m] = Max − Allocation (what each process may still request).

## Safety algorithm
Set Work = Available and Finish[i] = false for all i. Repeatedly find a process i with Finish[i] = false and Need[i] ≤ Work (every component). Pretend it runs to completion: Work = Work + Allocation[i] and Finish[i] = true. If every process can finish this way, the state is safe and the order found is a safe sequence. If at some point no unfinished process has Need ≤ Work, the state is unsafe.

## Several safe sequences
A safe state usually has more than one safe sequence. Any order is correct as long as each chosen process satisfies Need ≤ Work at its turn. A common textbook answer is P1, P3, P4, P0, P2, but P1, P3, P0, P2, P4 is also safe for the same data.

## Resource-request algorithm
When process i requests Request[i]: if Request > Need[i], it is an error (it exceeds its maximum claim). If Request > Available, the process must wait. Otherwise pretend to allocate (Available −= Request, Allocation[i] += Request, Need[i] −= Request) and run the safety algorithm. Grant the request only if the new state is safe; otherwise roll back and make the process wait.

## Common student mistakes
Computing Need as Allocation − Max; comparing Max instead of Need with Work; adding Need instead of Allocation to Work when a process finishes; thinking an unsafe state is already a deadlock (it only means deadlock is possible).
