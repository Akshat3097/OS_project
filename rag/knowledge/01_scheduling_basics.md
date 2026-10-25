---
topic: CPU Scheduling
subtopic: Scheduling basics
source: Seed course notes
difficulty: Beginner
---
# CPU scheduling basics

## Why scheduling is needed
A process alternates between CPU bursts (computing) and I/O bursts (waiting for a device). When several processes are ready to run, the short-term scheduler (CPU scheduler) chooses which one gets the CPU next. The dispatcher then gives that process the CPU by switching context, switching to user mode and jumping to the right instruction. The time this takes is the dispatch latency; textbook problems usually ignore it.

## Terms used in numerical problems
Arrival time (AT) is when the process enters the ready queue. Burst time (BT) is how much CPU time it needs. Completion time (CT) is when it finishes its last piece of execution. Turnaround time (TAT) is the total time from arrival to completion: TAT = CT − AT. Waiting time (WT) is the total time spent in the ready queue without running: WT = TAT − BT. Response time (RT) is the time from arrival until the process runs for the first time: RT = first start − AT. For non-preemptive algorithms WT equals RT; for preemptive algorithms WT can be larger because a process may wait several times.

## Gantt charts
A Gantt chart is a timeline showing which process holds the CPU in each interval. Read completion time from the end of the LAST block of a process, not the first one. If no process has arrived, the CPU is idle and the chart shows an idle gap. Total busy time in the chart must equal the sum of all burst times.

## Preemptive vs non-preemptive
In non-preemptive scheduling a process keeps the CPU until it finishes its burst (or blocks). In preemptive scheduling the OS may take the CPU away, for example when a time slice ends (Round Robin) or a better process arrives (SRTF, preemptive priority).

## Scheduling criteria
CPU utilisation (keep the CPU busy), throughput (processes completed per unit time), turnaround time, waiting time and response time. Batch systems care most about throughput and turnaround; interactive systems care most about response time. No single algorithm is best for every criterion.
