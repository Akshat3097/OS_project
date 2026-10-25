---
topic: CPU Scheduling
subtopic: Common mistakes
source: Seed course notes
difficulty: Beginner
---
# Checking your scheduling answers

## Quick self-checks
Every process must appear in the Gantt chart for exactly its burst time in total. No process may start before its arrival time. Turnaround time is never smaller than burst time, and waiting time is never negative. The sum of waiting times plus the sum of burst times equals the sum of turnaround times.

## Formula mix-ups
TAT = CT − AT, not CT alone; using CT only works when every process arrives at time 0. WT = TAT − BT, so forgetting to subtract the burst gives WT = TAT. In preemptive scheduling, waiting time includes every period spent in the ready queue, so it is generally not equal to the response time.

## Throughput and utilisation
Throughput is the number of completed processes divided by the total time. CPU utilisation is busy time divided by total time; idle gaps lower it.
