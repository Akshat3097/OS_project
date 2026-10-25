---
topic: CPU Scheduling
subtopic: Round Robin
source: Seed course notes
difficulty: Intermediate
---
# Round Robin (RR)

## Rule
Round Robin is FCFS with preemption by a timer. Each process gets at most one time quantum q at a time. The scheduler takes the process at the front of the FIFO ready queue. If the process finishes within q, it leaves; otherwise the timer interrupt preempts it and it goes to the back of the ready queue.

## Queue order convention
When a time slice ends at the same instant a new process arrives, this course adds the newly arrived process to the queue first and then the preempted process. Always state the convention you use, because some books use the opposite order and get a different Gantt chart.

## Choosing the quantum
With a very large quantum RR behaves like FCFS. With a very small quantum there are many context switches and the overhead dominates. A rule of thumb is that most CPU bursts (about 80%) should be shorter than the quantum. RR usually gives higher average turnaround than SJF but much better response time, which suits interactive systems.

## Example
P1(24), P2(3), P3(3), all at time 0, q = 4: P1 0–4, P2 4–7, P3 7–10, then P1 10–30. Waiting times are 6, 4 and 7, average 5.67.

## Common student mistakes
Running a process for longer than one quantum while others are waiting; putting the preempted process ahead of a process that arrived at the same time; forgetting that a process that finishes early gives up the rest of its quantum.
