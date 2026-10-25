---
topic: Process Synchronization
subtopic: Critical section
source: Seed course notes
difficulty: Intermediate
---
# Race conditions and the critical-section problem

## Race condition
A race condition happens when several processes access and change shared data at the same time and the result depends on the exact order of execution. Example: two threads both execute count++ which is really load, add, store; if they interleave, one update can be lost.

## Critical section requirements
The critical section is the code that accesses shared data. A correct solution must provide: (1) mutual exclusion, at most one process in its critical section at a time; (2) progress, if nobody is in the critical section, the choice of who enters next cannot be postponed forever and only processes wanting to enter take part in the decision; (3) bounded waiting, there is a limit on how many times others can enter before a waiting process gets its turn.

## Peterson's solution
For two processes, Peterson's algorithm uses flag[i] (I want to enter) and turn (whose turn it is to yield). Process i sets flag[i] = true and turn = j, then waits while flag[j] && turn == j. It satisfies all three requirements, but on modern hardware it needs memory barriers because instructions can be reordered.

## Hardware support
Atomic instructions such as test_and_set and compare_and_swap let a lock be acquired in one indivisible step. Mutex locks built on them use busy waiting (spinlocks), which is fine for very short critical sections on multiprocessors.
