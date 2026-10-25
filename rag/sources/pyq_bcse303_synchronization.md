---
topic: Process Synchronization
source: BCSE303L past papers (CAT-2, VIT)
type: Previous-year question paper
difficulty: Advanced
---
# Synchronization and deadlocks in past BCSE303L papers

## What CAT-2 synchronization questions look like
Every CAT-2 paper has a Banker's algorithm question (safe state, safe sequence, a resource request) and one or two semaphore design or tracing questions. Frequent themes: Peterson's solution, the Bakery algorithm, Test-and-Set with bounded waiting, dining philosophers, counting semaphores for limited resources, and scenario problems (study room capacity, airport runway, speaker sessions). Memory-management questions in the same paper are outside this tutor's scope.

## Banker's algorithm in the answer keys
The keys compute Need = Max − Allocation, then scan P0, P1, P2 … repeatedly, continuing from where the last process was found (cyclic scan). Example (CAT-2 2024-25 B1): Available (3, 3, 2, 1) gives the safe sequence P0, P3, P4, P1, P2, and P1's request (1, 1, 0, 0) is granted because the state stays safe. Other valid sequences are accepted (the 2025-26 C1 key notes P0, P2, P1, P3, P4 as also correct). In 2025-26 C2, P2's request (0, 3, 0, 0) is refused because it exceeds P2's need (1, 0, 1, 2): always check Request ≤ Need first, then Request ≤ Available, then safety.

## Deadlock detection from a resource-allocation graph
CAT-2 2023-24 gave a resource-allocation graph with resources P, Q, R. Read Allocation and outstanding Request from the edges, then run the safety algorithm with Need = Request. With Available (1, 0, 1) only P3 can finish, so the state is unsafe; adding one instance of Q makes it safe with order P1, P2, P3, P4, P5. A related CAT-2 2025-26 C1 question asked whether 2 processes needing at most 2 of 3 identical resources can deadlock: no, because resources > processes × (max need − 1), that is 3 > 2 × 1.

## Peterson's solution
Shared variables: interested[2] and turn. Entry: interested[i] = true; turn = i (or the other process, depending on the textbook version); wait while the other is interested and the turn condition holds. A trace table question (CAT-2 2023-24) asks which process enters for given values of interested[] and turn; the answer depends on whether the other process is interested and whose turn it is. It guarantees mutual exclusion and progress for two processes.

## Bakery algorithm and token passing
For n processes, each takes a ticket one larger than the maximum, waits while anyone is choosing, then waits for every process with a smaller ticket (or an equal ticket and a smaller id). A 2025-26 question asked for a solution without tickets: a turn variable passed around the processes in a circle, skipping processes that do not want the critical section, which also prevents starvation.

## Test-and-Set with bounded waiting
Shared waiting[n] and lock. Entry: waiting[i] = true; key = true; while (waiting[i] && key) key = TestAndSet(&lock); waiting[i] = false. Exit: look for the next waiting process j in circular order; if none, set lock = false, otherwise set waiting[j] = false. In the 2025-26 C2 trace, the first process whose TestAndSet sees lock = false enters; on exit it hands the critical section directly to the next waiting process in order, which gives bounded waiting.

## Semaphore scenario problems
Counting semaphore initialised to the capacity (10 database connections, 20 study-room seats) limits entry; a binary semaphore (mutex) protects a shared item (one whiteboard, one runway). The 2025-26 runway question adds landing priority: count waiting landing planes under a mutex and let take-offs proceed only when that count is zero. A 2023-24 trace: with a = 1, b = 0, P0 does down(a), print 3, up(b) and P1 does down(b), print 2, up(a), so the output strictly alternates 3232…

## Fixing a race condition with a mutex
Two threads each run counter++ 10000 times; without a lock the final value is often less than 20000 because load, add and store interleave. Wrapping counter++ in pthread_mutex_lock / pthread_mutex_unlock (and initialising the mutex) makes the result always 20000.

## Dining philosophers
Each philosopher picks up the left chopstick, then the right. If all five pick up their left chopstick at once, everyone waits forever (deadlock). Remedies: allow at most four philosophers to sit, pick up both chopsticks only if both are free (monitor with test()), or make one philosopher pick up the right chopstick first. In the 2025-26 C2 trace, philosopher 0 holds both chopsticks and eats first; the others hold one chopstick and wait.

## A key that needs checking
CAT-2 2024-25 B2 printed Allocation larger than Max; the key swaps the two tables, gets the safe sequence P0, P2, P3, P4, P1, and then says P3's request (2, 1, 0, 0) can be granted. After the swap P3's need is (1, 0, 2, 0), so asking for 2 instances of A exceeds its maximum claim and should be refused.
