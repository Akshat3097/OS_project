---
source: OS Tutor check of the class-notes worked examples against the OS Engine
type: Notes
difficulty: Intermediate
---
# Conventions in the class notes, and what the engine check found

## Conventions the Module 3 worked examples follow
Ties: equal bursts (SJF) or equal priorities are broken FCFS, by arrival time. Priority: the worked examples use smallest integer = highest priority unless the question says "higher number represents higher priority" (Priority Example 3). Round Robin: a new process joins the tail of the ready queue; when a process arrives at the same moment a time slice ends, the new arrival goes into the queue before the preempted process. SRTF and preemptive priority preempt the running process only when the newcomer is strictly better. Response time = first time on the CPU − arrival time. With I/O bursts the tables compute WT = TAT − total CPU burst, so time spent doing I/O is counted as waiting (slide 19 also writes TAT = WT + CPU + I/O, which would exclude it); the tutor accepts both and says which one you used. CPU utilisation and throughput use the total time from 0 to the last completion. Context switches = number of changes from one process to a different one in the Gantt chart (an idle gap between two runs of the same process is not a switch). Multilevel feedback queue: every new process enters the top queue; a process that uses its whole quantum moves down one level; one that finishes or leaves for I/O early keeps its level.

## Semaphore definitions in the course
The Module 4 notes define P(S) { while (S <= 0); S--; } and V(S) { S++; }: a busy-waiting semaphore whose value never goes below 0. OSTEP (threads-sema) and the Theory "Semaphore" slides define the blocking version: wait decrements and blocks if the value becomes negative, so −k means k waiting threads. For the same sequence of operations both block the same processes; only the value differs (busy-waiting value = blocking value, but never below 0). The tutor accepts either and tells you which definition your answer follows.

## Banker's algorithm: more than one safe sequence
The notes list several valid safe sequences for the same state (Example 2: <P0, P3, P1, P2, P4>, <P0, P3, P4, P1, P2>, <P0, P3, P2, P1, P4>, …). Any order that passes the safety check is correct; the tutor checks your sequence step by step instead of comparing it with one fixed answer. The engine itself scans cyclically (after a process finishes it continues from the next process), which is what the past CAT answer keys do.

## Worked examples reproduced exactly by the engine
All of these match the notes' Gantt charts and numbers: FCFS Examples 1, 2, 3, 4 and 6; SJF Examples 1, 5, 6 and 7; SRTF Examples 2, 3 and 4; Priority Examples 1, 2 (GATE MCQ, average WT 29), 3 (higher number = higher priority) and 4; Round Robin Examples 1 and 2; Round Robin with priority (Example 4, a higher priority waits for the running time slice to end); FCFS, SRTF, Round Robin and preemptive priority with I/O bursts (Gantt charts, completion times, CPU utilisation and context switches); the multilevel queue example; the MLFQ example; Banker's Examples 1 and 2 (including both requests); and the deadlock detection example.

## Slips found in the notes
FCFS Example 5 (slide 31): the turnaround times use CT − 0 for every process, copied from Example 4; with arrivals 0, 4, 6 they are 6, 5, 11 (average 7.33) and the waiting times 0, 2, 3 (average 1.67). Round Robin Example 3 (slide 85, q = 3): the chart takes processes in index order; with a real ready queue P1 (requeued at 3) runs before P5 (arrives at 4): P1 12–15, P5 15–17, so P5 completes at 17 and the averages are TAT 20.2 and WT 14.6 instead of 19.6 and 14. Round Robin with I/O (slide 125): the waiting times 3, 5, 2, 2 add up to 12, not 11, so the average WT is 3.0 (2.5 if I/O is not counted). Preemptive priority with I/O (slide 146): P4's WT is 8 − 2 = 6, not 4, and the TAT column adds up to 35, not 25, so the averages are TAT 8.75 and WT 4.5. In SRTF Examples 2–4 the handwritten numbers next to a burst (e.g. 12 → 10) are the remaining times after the first preemption, not new burst times.
