---
topic: CPU Scheduling
subtopic: Priority scheduling
source: Seed course notes
difficulty: Intermediate
---
# Priority scheduling

## Rule
Each process has a priority number and the CPU goes to the arrived process with the highest priority. In this course a LOWER number means a HIGHER priority (priority 1 beats priority 3). Some books use the opposite convention, so always check the question. Equal priorities are broken by arrival order.

## Preemptive and non-preemptive
In non-preemptive priority scheduling, a newly arrived high-priority process waits until the running process finishes. In preemptive priority scheduling it preempts the running process if its priority is strictly higher.

## Starvation and aging
Low-priority processes may wait indefinitely if higher-priority work keeps arriving (starvation, also called indefinite blocking). Aging fixes this by gradually increasing the priority of processes that have waited a long time.

## Relation to other algorithms
SJF is a special case of priority scheduling where the priority is the (predicted) burst length. FCFS is priority scheduling where priority is arrival time.
