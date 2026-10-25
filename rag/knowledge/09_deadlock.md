---
topic: Process Synchronization
subtopic: Deadlocks
source: Seed course notes
difficulty: Intermediate
---
# Deadlocks

## Necessary conditions
A deadlock can occur only if all four conditions hold at once: mutual exclusion (a resource is used by one process at a time), hold and wait (a process holds resources while waiting for more), no preemption (resources are released only voluntarily) and circular wait (a cycle of processes, each waiting for a resource held by the next).

## Resource-allocation graph
Draw request edges from processes to resource types and assignment edges from resource instances to processes. If the graph has no cycle there is no deadlock. If every resource type has a single instance, a cycle means deadlock. With multiple instances, a cycle means deadlock is possible but not certain.

## Handling deadlocks
Prevention breaks one of the four conditions (for example, impose a global order on resource requests to prevent circular wait). Avoidance uses extra information about future requests to stay in a safe state (Banker's algorithm). Detection and recovery lets deadlocks happen, detects them, then aborts processes or preempts resources. Many general-purpose systems simply ignore the problem.
