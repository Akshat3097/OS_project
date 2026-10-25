---
topic: Process Synchronization
subtopic: Semaphores
source: Seed course notes
difficulty: Intermediate
---
# Semaphores

## Definition
A semaphore S is an integer accessed only through two atomic operations: wait(S) (also called P or down) and signal(S) (also called V or up). A binary semaphore takes values 0 and 1 and works like a mutex lock. A counting semaphore can take any value and is used to control access to a pool of identical resources.

## Blocking implementation
To avoid busy waiting, each semaphore has a queue of waiting processes. wait(S): decrement S; if S becomes negative, add the calling process to the queue and block it. signal(S): increment S; if S is still zero or negative, remove one process from the queue (FIFO) and wake it up. In this implementation a negative value −k means k processes are waiting. A quick check: the final value always equals the initial value minus the number of waits plus the number of signals.

## Producer–consumer with a bounded buffer
Use three semaphores: mutex = 1 (protects the buffer), empty = n (free slots) and full = 0 (filled slots). Producer: wait(empty); wait(mutex); add item; signal(mutex); signal(full). Consumer: wait(full); wait(mutex); remove item; signal(mutex); signal(empty). Swapping the order of wait(empty) and wait(mutex) in the producer can deadlock: the producer holds mutex while sleeping on empty, so the consumer can never enter to free a slot.

## Common student mistakes
Mixing the two definitions in one answer (the busy-waiting P/V in the Module 4 notes keeps S ≥ 0; the blocking version lets S go negative); forgetting that signal wakes a blocked process; letting a blocked process perform further operations.
