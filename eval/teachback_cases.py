"""
Labelled explanations for checking the teach-back judge (python -m eval.teachback_eval).

Each case: the lesson, what the student said, the ideas a fair examiner would credit ("yes", clear or partial),
ideas that are borderline ("either", not scored) and the misconceptions it states ("mis"). Every other idea of the
lesson must NOT be credited. The kinds cover what students (and examiners testing the app) actually do: full and
partial explanations, paraphrases without the textbook words, wrong beliefs, off-topic talk, and keyword salad
(technical words with no explanation).
"""

CASES = [
    # ------------------------------------------------------------------ scheduling basics
    {"lesson": "basics", "kind": "full", "yes": {"one_cpu", "tat", "wt", "ct_last", "preemption"},
     "text": "Only one process can run on a CPU core at any moment, so the scheduler chooses which ready process gets it "
             "next. Turnaround time is completion time minus arrival time. Waiting time is turnaround time minus burst "
             "time, the time it sat ready without running. The completion time is the end of the process's last block in "
             "the Gantt chart, not the first. In non-preemptive scheduling a process keeps the CPU till it finishes, but "
             "in preemptive scheduling the OS can take the CPU away."},
    {"lesson": "basics", "kind": "partial", "yes": {"tat", "wt"},
     "text": "Turnaround time is how long the process stays in the system, from when it arrives until it completes. "
             "Waiting time is the turnaround time minus the time it actually runs on the CPU."},
    {"lesson": "basics", "kind": "paraphrase", "yes": {"tat", "wt"},
     "text": "You take the moment the job shows up and the moment it is fully done; the gap between them is its total "
             "time in the system. Subtract the time it was actually being served and what remains is how long it sat in "
             "the queue doing nothing."},
    {"lesson": "basics", "kind": "misconception", "yes": {"one_cpu"}, "either": {"tat"}, "mis": {"wt_equals_tat"},
     "text": "The CPU runs one process at a time and the scheduler decides which one goes next. Waiting time is the "
             "same as turnaround time, it is just completion time minus arrival time."},
    {"lesson": "basics", "kind": "salad", "yes": set(),
     "text": "TAT CT AT WT BT Gantt chart scheduler preemptive non-preemptive CPU last block arrival completion burst "
             "waiting turnaround"},
    {"lesson": "basics", "kind": "off-topic", "yes": set(),
     "text": "My favourite subject is operating systems because the professor explains things well and the labs are "
             "fun, and I want to learn more about computers in general."},
    # ------------------------------------------------------------------ SRTF
    {"lesson": "srtf", "kind": "full", "yes": {"preemptive", "remaining", "strictly", "wt_pieces"},
     "text": "SRTF is the preemptive version of shortest job first. Whenever a new process arrives, the scheduler "
             "compares its burst with the remaining time of the running process, and if the newcomer is strictly shorter "
             "it interrupts the running one; on a tie the running one continues. Because a process can be stopped and "
             "resumed it runs in pieces, so waiting time is completion minus arrival minus burst."},
    {"lesson": "srtf", "kind": "partial", "yes": {"preemptive", "remaining"},
     "text": "In SRTF the process with the least remaining time runs. If a shorter job comes in, the current one gets "
             "kicked off the CPU."},
    {"lesson": "srtf", "kind": "misconception", "yes": set(), "mis": {"same_as_sjf"},
     "text": "SRTF picks the shortest job when the CPU becomes free, and once a process starts it runs until it "
             "finishes, nobody can interrupt it."},
    {"lesson": "srtf", "kind": "wrong rule", "yes": {"preemptive", "remaining"},
     "text": "SRTF is preemptive and looks at the remaining time. If the new process has the same remaining time as the "
             "running one, the new one takes over the CPU."},
    {"lesson": "srtf", "kind": "salad", "yes": set(),
     "text": "SRTF preemptive remaining time strictly shorter tie burst arrival completion pieces interrupt newcomer running"},
    {"lesson": "srtf", "kind": "paraphrase", "yes": {"preemptive", "remaining"}, "either": {"strictly"},
     "text": "Think of it as always serving whoever is closest to being done. Each time someone new shows up you check: "
             "if they need less time than what the current one still has left, the current one is paused and resumed later."},
    # ------------------------------------------------------------------ Round Robin
    {"lesson": "rr", "kind": "full", "yes": {"quantum", "back_of_queue", "arrival_convention", "early_finish", "q_size"},
     "text": "Round robin gives each process a fixed time slice called the quantum. If it is not finished when the slice "
             "ends it goes to the back of the ready queue and the process at the front runs next. If a new process "
             "arrives exactly when a slice ends, the new one joins the queue before the preempted one. A process that "
             "finishes early releases the CPU straight away. A very large quantum makes it behave like FCFS, and a very "
             "small one causes too many context switches."},
    {"lesson": "rr", "kind": "partial", "yes": {"quantum", "back_of_queue"},
     "text": "Every process gets a small time quantum on the CPU, and when its time is up it goes to the back of the line."},
    {"lesson": "rr", "kind": "misconception", "yes": set(), "mis": {"runs_to_end"},
     "text": "In round robin the processes take turns in arrival order and each one runs until it finishes before the "
             "next one starts."},
    {"lesson": "rr", "kind": "misconception", "yes": {"quantum"}, "mis": {"preempted_first"},
     "text": "Round robin uses a time quantum. When the quantum ends and a new process arrives at the same time, the "
             "preempted process goes into the queue first, ahead of the new arrival."},
    {"lesson": "rr", "kind": "salad", "yes": set(),
     "text": "quantum queue FIFO front back preempted arrival context switch FCFS round robin slice finish early"},
    {"lesson": "rr", "kind": "off-topic", "yes": set(),
     "text": "Round robin is also how cricket tournaments are played: every team plays every other team once and the "
             "top two teams go to the final."},
    # ------------------------------------------------------------------ semaphores
    {"lesson": "semaphores", "kind": "full", "yes": {"wait_block", "signal_wake", "negative", "mutex", "order"},
     "text": "wait, also called P, decreases the semaphore, and if the value goes negative the process blocks. signal, "
             "or V, increases it, and if processes are waiting one of them is woken. In the blocking version a value of "
             "minus two means two processes are waiting. A binary semaphore starting at one works as a mutex: call wait "
             "before the critical section and signal after it. The order of waits matters, because waiting on another "
             "semaphore while holding the mutex can deadlock."},
    {"lesson": "semaphores", "kind": "partial", "yes": {"mutex"}, "either": {"wait_block", "signal_wake"},
     "text": "A semaphore is an integer. wait decrements it and signal increments it, and with the value one it acts "
             "like a lock around the critical section."},
    {"lesson": "semaphores", "kind": "misconception", "yes": set(), "either": {"wait_block"}, "mis": {"signal_always_wakes"},
     "text": "signal always wakes up a waiting process every single time it is called, and wait makes the process sleep."},
    {"lesson": "semaphores", "kind": "salad", "yes": set(),
     "text": "semaphore wait signal P V mutex binary counting negative block wake critical section deadlock order"},
    {"lesson": "semaphores", "kind": "off-topic", "yes": set(),
     "text": "Semaphores are the flags that railway signalmen used in the old days to tell the train driver whether "
             "the track ahead was clear."},
    # ------------------------------------------------------------------ deadlocks
    {"lesson": "deadlock", "kind": "full", "yes": {"definition", "four_conditions", "rag", "handling"},
     "text": "A deadlock is when a set of processes each wait for a resource held by another process in the set, so none "
             "of them can continue. It needs all four conditions together: mutual exclusion, hold and wait, no "
             "preemption and circular wait. In a resource allocation graph where each resource has one instance, a "
             "cycle means deadlock. We can prevent it by breaking a condition, avoid it with the banker's algorithm, or "
             "detect it and recover."},
    {"lesson": "deadlock", "kind": "misconception", "yes": {"definition"}, "mis": {"starvation_condition"},
     "text": "Deadlock happens when processes wait for each other forever and none can go on. The conditions are "
             "mutual exclusion, hold and wait, starvation and circular wait."},
    {"lesson": "deadlock", "kind": "misconception", "yes": set(), "mis": {"any_cycle"},
     "text": "If the resource allocation graph has any cycle at all then the system is definitely deadlocked, even if "
             "the resources have many instances."},
    {"lesson": "deadlock", "kind": "partial", "yes": {"definition"},
     "text": "Two processes each hold one resource and wait for the one the other has, so both are stuck forever. "
             "That is a deadlock."},
    {"lesson": "deadlock", "kind": "salad", "yes": set(),
     "text": "deadlock mutual exclusion hold wait preemption circular graph cycle instance prevention avoidance "
             "detection recovery bankers"},
    # ------------------------------------------------------------------ Banker's algorithm
    {"lesson": "bankers", "kind": "full", "yes": {"need", "need_le_work", "release", "safe", "unsafe"},
     "text": "First compute need as max minus allocation. A process can finish if its need is less than or equal to "
             "work, which starts as available, for every resource. When it finishes it releases its allocation, so work "
             "increases by that allocation. If every process can finish in some order the state is safe, and there can "
             "be more than one safe sequence. An unsafe state does not mean there is a deadlock, only that one is possible."},
    {"lesson": "bankers", "kind": "misconception", "yes": {"need"}, "mis": {"release_need", "unsafe_is_deadlock"},
     "text": "Need is max minus allocation. When a process finishes we add its need to work. If the state is unsafe "
             "the system is already in deadlock."},
    {"lesson": "bankers", "kind": "partial", "yes": {"safe"},
     "text": "The banker's algorithm checks whether the system is in a safe state by finding an order in which all of "
             "the processes can finish."},
    {"lesson": "bankers", "kind": "salad", "yes": set(),
     "text": "need max allocation work available finish release safe sequence unsafe deadlock banker algorithm"},
    {"lesson": "bankers", "kind": "paraphrase", "yes": {"need", "need_le_work", "release"},
     "text": "For each customer the bank works out how much more they could still ask for, which is their limit minus "
             "what they already have. It only serves a customer if the cash in hand covers that remaining amount, and "
             "once they are done they return everything they had borrowed."},
    # ------------------------------------------------------------------ dining philosophers
    {"lesson": "dining", "kind": "full", "yes": {"setup", "deadlock", "circular", "fix"},
     "text": "Five philosophers sit at a round table with five chopsticks, and each needs both the left and the right "
             "chopstick to eat. If all of them pick up their left chopstick at the same time, each waits forever for the "
             "right one, which is a deadlock. It is a circular wait, each holding one chopstick and waiting for the next "
             "philosopher's. To fix it a philosopher should pick up the chopsticks only when both are free, or allow "
             "only four at the table."},
    {"lesson": "dining", "kind": "misconception", "yes": set(), "either": {"setup"}, "mis": {"semaphores_prevent"},
     "text": "Each chopstick is a semaphore, and because we use semaphores for the chopsticks the philosophers can "
             "never deadlock."},
    {"lesson": "dining", "kind": "partial", "yes": {"setup"},
     "text": "There are five philosophers and five forks around the table, and you need two forks to eat, so "
             "neighbours cannot eat at the same time."},
    {"lesson": "dining", "kind": "salad", "yes": set(),
     "text": "philosopher chopstick fork left right both deadlock circular wait monitor four odd even fix"},
]
