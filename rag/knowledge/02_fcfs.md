---
topic: CPU Scheduling
subtopic: FCFS
source: Seed course notes
difficulty: Beginner
---
# First Come First Serve (FCFS)

## Rule
FCFS runs processes in the order they arrive, using a FIFO ready queue. It is non-preemptive: once a process starts it runs until its burst finishes. If two processes arrive at the same time, the one listed first usually goes first.

## Convoy effect
If a long process arrives first, every short process behind it waits for the whole long burst. This is the convoy effect. Example: bursts 24, 3, 3 arriving together in that order give waiting times 0, 24 and 27, an average of 17. If the two short jobs go first, the average waiting time drops to 3. So FCFS is simple and fair in arrival order but can give poor average waiting time.

## Solving an FCFS problem
Sort by arrival time. Start each process at the later of (its arrival time, the time the previous process finished). If the CPU becomes free before the next arrival, there is an idle gap. Then CT is the end of each block, TAT = CT − AT and WT = TAT − BT.
