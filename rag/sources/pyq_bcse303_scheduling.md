---
topic: CPU Scheduling
source: BCSE303L past papers (CAT-1, VIT)
type: Previous-year question paper
difficulty: Advanced
---
# CPU scheduling in past BCSE303L papers

## What CAT-1 scheduling questions look like
Every CAT-1 paper from 2024-25 to 2026-27 has two 10-mark scheduling numericals. Common patterns: (1) one process table solved with two or three algorithms (pre-emptive SJF, pre-emptive priority, Round Robin); (2) multilevel queue scheduling with different algorithms per queue; (3) processes with I/O, given either as CPU–I/O–CPU bursts or as a percentage of total time spent on I/O. Marks are split between the Gantt chart and the CT, TAT, WT (and sometimes RT) table with averages.

## Conventions the answer keys use
Pre-emptive SJF (SRTF) does not preempt on a tie: the running process continues. Among equal candidates the process that entered the ready queue earlier goes first; a process returning from I/O enters the ready queue when its I/O finishes. In Round Robin, a process arriving at the same instant a time slice ends joins the queue before the preempted process (the CAT-1 2025-26 C1 key confirms this). Priority questions usually say lower number = higher priority; one 2026-27 key also accepted the opposite convention when the student stated it.

## Processes with I/O bursts
For CPU 4, I/O 3, CPU 3: after the first CPU burst the process leaves the ready queue for 3 units (I/O runs in parallel with the CPU) and returns to the ready queue when the I/O ends. Completion time is the end of the last CPU burst. The 2026-27 key uses WT = TAT − (all CPU bursts) − (I/O burst). When a paper says "each process spends 25% of its time on I/O", the 2025-26 key treated the I/O as happening first and counted it as waiting (WT = TAT − CPU). State the convention you use in the exam.

## Percentage-based CPU bursts
CAT-1 2024-25 (B2) gave total execution times and said 60% is CPU. Compute CPU burst = 0.6 × total (for example 8 ms gives 4.8 ms), then schedule with FCFS and non-preemptive SJF using only the CPU bursts. Decimal times such as 6.8 and 12.8 appear in the Gantt chart.

## Multilevel queue scheduling
Each queue has its own algorithm (for example Q1 pre-emptive SJF, Q2 FCFS, Q3 Round Robin with time slice 2). A lower queue runs only when all higher queues are empty, and an arrival in a higher queue preempts a running lower-queue process. In the 2025-26 C2 key, P1 (Q2, FCFS) started at 0, was preempted at t=1 by P2 (Q1), and resumed at t=11 before the other Q2 processes. Draw the queues first, then the Gantt chart, then the table.

## Round Robin worked answer (CAT-1 2025-26 C1, q = 2)
Processes P1–P5 with arrival 0–4 and bursts 9, 5, 7, 4, 6 give completion times 31, 23, 30, 20, 29, average TAT 24.6 ms and average WT 18.4 ms. The theory part asked why context switches reduce efficiency: a very small quantum spends a large share of CPU time switching (about 10% overhead if the switch costs 10% of the quantum); a very large quantum turns RR into FCFS.

## Answer-key slips found by the OS Engine
In CAT-1 2025-26 C2 Q4 the Gantt charts are right but P1's waiting time is written as 0 instead of 1 and its SRTF turnaround as 3 instead of 4, so the averages are slightly off (FCFS WT 13.4 not 13.2; SJF 12.8 not 12.6; SRTF TAT 22.8 not 22.6). In CAT-1 2025-26 C1 Q5 the TAT sum shows P9 as 29, a typo for 2; the final average 12.89 is correct.
