"""
Checked answers to the questions a teacher is likely to ask to test the tutor: classic trick questions, short
definitions next to the course, and topics from other modules (memory, disks).

Found on 24 Oct with eval/teacher_probe.py: the fine-tuned model answered "Can Round Robin cause starvation?",
"Is an unsafe state a deadlock?", "explain paging" and "explain LRU" with confident mistakes (an unsafe state "where
every process could finish", "a 4 KB page fits into a 64 KB frame"). These answers are written and checked by hand
against Silberschatz and the class notes, so they are shown as they are, without the language model.
"""
from __future__ import annotations

import re

# Topics the tutor was not built for get a short, correct summary and say so.
OUTSIDE = ("\n\n_That topic is outside the two areas I was built for (CPU scheduling and process synchronization), so "
           "this is only a short summary: check the details in your notes._")

# (pattern, lesson id or None, answer, inside the course?)
ENTRIES: list[tuple] = [   # optional fifth item: the video key, when it is not the lesson id
    (r"^\W*(who (made|built|created|developed) (you|this)|who are you|what are you|are you (chat\s*gpt|gpt|gemini|claude|an? ai|human|real))\b", None,
     "I'm **OS Tutor**, a final-year project by **Akshat** and **Mohammed Falah Ur Rahman Danish** for the BCSE303 "
     "Operating Systems course at VIT. I'm not ChatGPT: I run on **Llama 3.1 8B fine-tuned with QLoRA** on the course "
     "material, entirely on this laptop with Ollama, and every number I give comes from a deterministic **OS Engine**, "
     "not from the language model.\n\nAsk me to explain a topic, paste a question from a paper, or try **Learn**, "
     "**Labs** or the mock **Exam**.", True),
    (r"\b(which|what) (llm|model|language model|ai)\b|\b(running|run|based) on\b.*\b(model|llm|llama)|how (were|are) you (trained|built|made)|fine[- ]?tun", None,
     "**Llama 3.1 8B**, fine-tuned with **QLoRA** on examples built from the course: worked solutions from the OS Engine, "
     "explanations from the lessons and the class notes, and hints for common mistakes. It runs locally on this "
     "laptop with **Ollama**, so nothing leaves the machine.\n\nThe language model only words the replies: every "
     "schedule, table and number comes from the deterministic OS Engine, and a guard blocks any reply that uses a "
     "number the engine didn't give.", True),
    # ---- conventions and follow-ups teachers asked about (24 Oct, eval/teacher_questions.txt) ----
    (r"(fcfs|first[- ]come)\b.*\b(vs|versus|differ\w*|compar\w*|and)\b.*\b(sjf|shortest[- ]job)|(sjf|shortest[- ]job)\b.*\b(vs|versus|differ\w*|compar\w*)\b.*\b(fcfs|first[- ]come)", "sjf",
     "- **FCFS** runs processes in the order they **arrive**, each to completion.\n"
     "- **SJF** (non-preemptive) picks, among the processes that have **already arrived**, the one with the "
     "**shortest burst**, and runs it to completion; ties go to the earlier arrival.\n\n"
     "Both are non-preemptive. FCFS is simpler and fair by arrival order but suffers the convoy effect; SJF gives the "
     "minimum average waiting time but needs to know (predict) burst lengths and can starve long jobs.", True),
    (r"(fcfs|first[- ]come)\b.*\b(vs|versus|differ\w*|compar\w*)\b.*\b(round[- ]?robin|\brr\b)|(round[- ]?robin|\brr\b)\b.*\b(vs|versus|differ\w*|compar\w*)\b.*\b(fcfs|first[- ]come)", "rr",
     "- **FCFS** serves processes in arrival order and lets each run to completion (non-preemptive).\n"
     "- **Round Robin** also uses arrival order, but each process runs for at most one **time quantum**, then goes "
     "to the back of the queue (preemptive).\n\n"
     "RR gives much better response time for interactive users, at the cost of context switches; with a very large "
     "quantum it behaves exactly like FCFS.", True),
    (r"(fcfs|first[- ]come)\b.*\b(depend\w*|chang\w*|affect\w*|matter\w*)\b.*\b(order|arriv\w*)", "fcfs",
     "**Yes, strongly.** FCFS runs processes in arrival order, so the order decides who waits behind whom. If a long "
     "process arrives first, every short one waits for its whole burst (the convoy effect); with the short ones "
     "first, the average waiting time drops a lot. Example from the lesson: bursts 8, 2, 1 arriving in that order "
     "give an average waiting time of 5.", True),
    (r"\bsafe\b.*\b(sequence|order)\b.*\b(not |isn'?t |never )?(written|shown|stated|given)|\b(without|no) (a )?(written )?(safe )?sequence\b", "bankers",
     "**Yes: a state is safe exactly when such an order exists**, whether or not anyone writes it down. But in an "
     "exam the sequence is your evidence: show the order with Work after each step, or the marks for the safety check "
     "are lost. Any valid order is accepted.", True),
    (r"\b(just|simply|only)\b.*\b(increment\w*|decrement\w*|counter|variable)\b.*\bsemaphore|semaphore\w*\b.*\b(instead of|rather than)\b.*\b(variable|counter|increment\w*)|"
     r"why\b.*\bboth wait and signal|\bboth wait and signal\b.*\bwhy|why\b.*\bwait and signal\b.*\b(instead|rather|just)", "semaphores",
     "Because the two operations do different jobs, and a plain variable can do neither safely:\n\n"
     "- **wait()** takes a unit and **blocks** the caller if none is free.\n"
     "- **signal()** returns a unit and **wakes** a waiting process.\n\n"
     "A plain counter can't block or wake anyone, so a process would have to spin checking it. And `count++` / "
     "`count--` aren't atomic (load, add, store): two processes could both read 1 and both enter. Semaphore "
     "operations are atomic.", True),
    (r"(\bsrtf\b|shortest[- ]remaining)\b.*\b(tie|ties|tied|same|equal|equals|matches)\b|\b(tie|ties|same|equal)\b.*\bremaining\b|"
     r"\bsrtf\b.*\bremaining\b.*\barriv\w*\b.*\b(who|which)\b", "srtf",
     "**The running process continues.** SRTF preempts only when the newcomer's burst is **strictly shorter** than "
     "the running process's remaining time, so on a tie there is no context switch (the course answer keys follow "
     "this). Among *waiting* processes with equal remaining time, the one that arrived earlier goes first, then the "
     "lower process number.", True),
    (r"(all|every)\b.*\barriv\w*\b.*\bsame burst|\bsame burst\b.*\b(which|best)\b|(all|every)\b.*\bsame burst", "basics",
     "If every process arrives at 0 with the same burst b, **FCFS, SJF and SRTF give the same schedule** (ties go to "
     "list order) and the lowest average waiting time, (n − 1)·b / 2. **Round Robin** gives a worse average waiting "
     "and turnaround time (everyone finishes near the end) but a better response time.", True),
    (r"(\bsjf\b|shortest[- ]job)\b.*\b(tie|ties|tied|same|equal)\b|\b(tie|ties|same|equal) bursts?\b|"
     r"\bsjf\b.*\barriv\w* times?\b.*\bsame\b", "sjf",
     "Ties go to the process that **arrived earlier** (FCFS order), and if they also arrived together, to the one "
     "listed first (lower process number). A process that hasn't arrived yet can't be chosen, however short it is.", True),
    (r"(same|equal) priorit|priorit\w*\b.*\b(tie|ties|tied|same|equal)\b", "priority",
     "Equal priorities are served **FCFS**: the one that arrived earlier first, then the lower process number. In "
     "preemptive priority, a newcomer with the *same* priority does not preempt the running process; only a strictly "
     "higher priority does.", True),
    (r"\b(lower|higher|smaller|larger|bigger|low|high)\b[^.?]{0,25}\b(number|no\.?|value|integer)\b[^.?]{0,40}\bpriorit|"
     r"priorit\w*\b[^.?]{0,40}\b(lower|higher|smaller|larger|bigger)\b[^.?]{0,15}\b(number|no\.?|value)|"
     r"\b(is|does) (0|1|zero|one)\b[^.?]{0,30}\b(highest|lowest|high|low)\b|\bpriorit\w*\b.*\b(0|1|zero|one)\b.*\b(highest|lowest)\b", "priority",
     "In this course (and Silberschatz), a **lower number means higher priority**: 0 or 1 is the highest, unless the "
     "question says otherwise. Some books use the opposite, so **state the convention you use** in the exam; past "
     "answer keys accepted either when it was stated. In Labs, the box \"Higher number = higher priority\" switches it.", True),
    (r"(arriv\w*|new process|newcomer)\b.*\b(same time|same moment|same instant|exact\w*|simultaneous\w*|at the same|matches)\b.*\b(quantum|slice|preempt\w*|back)\b|"
     r"(quantum|slice)\b.*\b(ends?|expires?|over|finish\w*)\b.*\barriv|\b(enqueue|ready queue|queue)\b.*\b(first|before)\b.*\b(arriv\w*|preempt\w*|put\w*)|"
     r"\b(finish\w*|ends?|expires?)\b.*\b(quantum|slice)\b.*\barriv\w*|\barriv\w*\b.*\b(which|who)\b.*\b(first|queue)\b|"
     r"(round[- ]?robin|\brr\b)\b.*\bsimultaneous|\bsimultaneous\b.*(round[- ]?robin|\brr\b|preempt)|"
     r"\bput\w*\b.*\b(back|preempted)\b.*\bbefore\b", "rr",
     "In this course the **newly arrived process joins the ready queue first**, then the preempted one goes behind it "
     "(the CAT-1 2025-26 C1 key confirms this, and it is Silberschatz's convention).\n\n"
     "Example: q = 2, P1(0,5), P2(1,3), P3(2,2). At t = 2 P1's slice ends just as P3 arrives, so the queue becomes "
     "P2, P3, P1. Some books put the preempted process first; if a question says so, follow it and state it.", True),
    (r"quantum\b[^.?]{0,25}\b(is |=|of |to |approaches |tends to |becomes |set to )?\s*(0|zero)\b|\bq\s*(=|is|approaches|tends to|->)\s*(0|zero)\b|"
     r"(zero|0) (time )?quantum|\bq\s*approaches\b", "rr",
     "**A quantum of 0 isn't valid**: no process would ever run, the CPU would only switch. The quantum must be "
     "greater than 0.\n\nAs q gets very small, Round Robin approaches **processor sharing**: each of n processes seems "
     "to run on its own CPU at 1/n speed. In practice the context-switch overhead would then take most of the CPU "
     "time, so q must stay well above the switch time.", True),
    (r"waiting time\b.*\b(tat|turn\s*-?around)\b.*\b(start|first)|\b(start|first)\w*\b.*\b(minus|-)\s*(at|arrival)\b.*\bwait|"
     r"\bwt\s*=\s*(tat|start|ct)\b.*\bor\b", "basics",
     "**WT = TAT − BT is always right** (when there is no I/O). WT = start − AT gives the same value only when a "
     "process runs in one piece, as in the non-preemptive algorithms. With preemption a process waits several times, "
     "and adding up all its gaps gives TAT − BT again.\n\nstart − AT is the **response time** (RT = first start − AT).", True),
    (r"response time\b.*\b(first (run|output|response|cpu|allocation|time)|mean\w*|defin\w*|minus)|\b(first output|first run)\b.*\bresponse", "basics",
     "In scheduling numericals, **RT = (the first time the process gets the CPU) − (its arrival time)**. Silberschatz "
     "defines response time as the time from submission until the first response is produced; a process can only "
     "respond after it first runs, so problems use the first time it is scheduled. It is not the time to finish "
     "(that's turnaround).", True),
    (r"\bfcfs\b[^.?]{0,40}\bpre-?empt|first[- ]come\b[^.?]{0,40}\bpre-?empt|pre-?empt\w*\b[^.?]{0,20}\bfcfs", "fcfs",
     "**FCFS is non-preemptive**: once a process gets the CPU, it keeps it until its burst ends (or it blocks for "
     "I/O). The preemptive version of \"serve in arrival order\" is **Round Robin**: FCFS plus a time quantum.", True),
    (r"(\bsjf\b|shortest[- ]job|\bsrtf\b)\b.*\bstarv|\bstarv\w*\b.*(\bsjf\b|shortest[- ]job|long (jobs?|process\w*))", "sjf",
     "**Yes, both versions can.** In non-preemptive SJF, a long job in the ready queue is passed over every time a "
     "shorter one is there when the CPU becomes free; if short jobs keep arriving, it can wait indefinitely. SRTF is "
     "worse, because a running long job can also be preempted again and again.\n\nThe fix is **aging**: raise a job's "
     "priority the longer it waits. (Starvation needs a steady stream of short jobs; with a fixed set of processes "
     "every job finishes eventually.)", True),
    (r"priorit\w*\b.*\bstarv|\bstarv\w*\b.*\bpriorit", "priority",
     "**Not always.** Starvation happens only when higher-priority processes keep arriving, so a low-priority one is "
     "always passed over; with a fixed set of processes everything finishes. It is a risk in both versions, and "
     "preemptive priority is more exposed because a running low-priority process can also be interrupted. **Aging** "
     "(raising the priority of processes that wait long) fixes it.", True),
    (r"(all|every)\b.*\barriv\w*\b.*\b(same time|together|t\s*=\s*0|time 0|at 0|at time 0)\b.*\b(srtf|sjf|same as)\b|"
     r"(srtf|sjf)\b.*\b(all|every)\b.*\barriv\w*\b.*\b(same|together|0)\b", "srtf",
     "Then **SRTF behaves exactly like non-preemptive SJF**: nobody arrives later, so nothing can preempt, and the "
     "shortest job runs first, then the next shortest, each to completion. Same Gantt chart, same averages (ties by "
     "list order).", True),
    (r"gantt\b.*\bcontext switch|context switch\w*\b.*\bgantt", "rr",
     "**Ignore it (take it as 0) unless the question gives a switch time.** If it does, put a gap of that length "
     "between consecutive processes in the Gantt chart. That delays every later completion, and CPU utilisation = "
     "useful time / total time.", True),
    (r"priority inversion|priority inheritance", None,
     "**Priority inversion:** a high-priority process H waits for a lock held by a low-priority process L, and a "
     "medium-priority process M (which doesn't need the lock) preempts L, so H effectively waits for M.\n\n"
     "**Priority inheritance:** while L holds a resource that H wants, L temporarily runs at H's priority, so M can't "
     "preempt it. L finishes its critical section quickly, releases the lock, drops back to its own priority, and H "
     "runs. (The Mars Pathfinder rover is the classic real case.)", True),
    (r"readers?[- ]writers?\b.*\b(first|second)\b.*\b(default|textbook|mean\w*|which|vs|versus)|(first|second)\b.*\breaders?[- ]writers?\b.*\b(default|textbook|vs)", "readers_writers",
     "By default (Silberschatz's code) it is the **first readers–writers problem**: readers have priority, so no "
     "reader waits unless a writer already has the data, and writers can starve. The **second** problem gives "
     "writers priority: once a writer is waiting no new reader may start, and then readers can starve.", True),
    (r"readers?[- ]writers?\b.*\b(which|what) semaphore|semaphore\b.*\bwriters? only|\brw_?mutex\b|\bwrt\b", "readers_writers",
     "**rw_mutex** (called **wrt** in older editions), initialised to 1, gives writers mutual exclusion: a writer "
     "does `wait(rw_mutex)` … write … `signal(rw_mutex)`. The first reader also takes it and the last reader "
     "releases it, so readers as a group exclude writers. The other semaphore, **mutex** (also 1), only protects "
     "`read_count`.", True),
    (r"\bneed\b\s*(=|is)\s*max\b|\bwhy\b.*\bneed\b.*\bmax\b|\bmax\b\s*(\+|plus|minus|-)\s*alloc|need matrix\b.*\b(always|calculated|how|why)", "bankers",
     "**Need is what a process may still ask for**: its maximum claim minus what it already holds, "
     "**Need = Max − Allocation**, element by element, always.\n\nUsing Max instead would overstate it: part of Max is "
     "already allocated and comes back when the process finishes, so safe states would look unsafe. Max + Allocation "
     "would count the held resources twice. A request is valid only if Request ≤ Need.", True),
    (r"banker\w*\b.*\b(needs?|requires?|uses?)\b.*\bmax\b|\bwhy\b.*\bbanker\w*\b.*\bmax|\bmax (matrix|claim)\b.*\bwhy", "bankers",
     "Because **avoidance must know the worst case in advance**. Max is each process's declared maximum claim; from "
     "it the system computes Need and checks whether some order lets every process get everything it could still ask "
     "for. Without Max there's no way to tell a safe state from an unsafe one, which is also why the Banker's "
     "algorithm is rare in general-purpose systems.", True),
    (r"safe state\b.*\b(no deadlock|never|guarantee\w*|deadlock[- ]free|always)", "bankers",
     "A safe state is **not deadlocked**, and from it the system **can** avoid deadlock: there is an order in which "
     "every process can finish. It stays that way only if the OS keeps granting requests carefully, which is what the "
     "Banker's algorithm does. If requests are granted that lead to an unsafe state, deadlock becomes possible again.", True),
    (r"banker\w*\b.*\b(detection|avoidance|prevention)\b", "bankers",
     "**Avoidance.** The Banker's algorithm decides each request in advance and grants it only if the system stays "
     "safe. **Detection** is a different algorithm (similar matrices, with Request in place of Need) that runs after "
     "the fact to find processes that are already deadlocked.", True),
    (r"avail\w*\b[^.?]{0,15}\b0\s*,?\s*0\s*,?\s*0\b|avail\w* (is |=\s*)?(zero|0)\b|nothing (is )?available", "bankers",
     "**No.** With Available = 0 the state is still safe if some process already holds everything it needs "
     "(Need = 0): it can finish, release its resources, and let the others continue. It is unsafe only if every "
     "process still needs something, and even an unsafe state is not yet a deadlock.", True),
    (r"(resource[- ]allocation graph|\brag\b)\b.*\b(multiple|several|more than one|many) instances?", "deadlock",
     "Yes, but a cycle means less. With **one instance per resource type**, a cycle in the resource-allocation graph "
     "means deadlock. With **several instances** a cycle is necessary but not sufficient: a process outside the cycle "
     "can release an instance and break it (Silberschatz Fig. 7.3). So with multiple instances, use the detection "
     "algorithm (Banker's-style matrices) to decide.", True, "rag"),
    (r"throughput\b.*\butili[sz]ation|utili[sz]ation\b.*\bthroughput", "basics",
     "**No.** CPU **utilisation** is the fraction of time the CPU is busy (for example 90%). **Throughput** is the "
     "number of processes completed per unit time (for example 5 per second). A CPU can be 100% busy yet finish few "
     "processes if they are long, or if much of its time goes on context switches.", True),
    (r"bounded waiting\b.*\bprogress|progress\b.*\bbounded waiting", "critical_section",
     "- **Progress:** if nobody is in the critical section, a process that wants to enter can, without waiting for "
     "processes that aren't trying; the choice can't be postponed forever. The group never gets stuck.\n"
     "- **Bounded waiting:** once a process has asked to enter, there's a limit on how many times others can enter "
     "before it does. Each individual eventually gets its turn (no starvation).", True),
    (r"bounded waiting\b.*\b(violat\w*|not (satisfied|met|guaranteed|there)|broken|missing|fails?)", "critical_section",
     "**No.** A correct solution must satisfy all three requirements. Without bounded waiting you still have mutual "
     "exclusion and progress, but a process can be overtaken forever (starvation); plain test_and_set is the usual "
     "example.", True),
    (r"why\b.*\b(need|use|needed|required|important)\b.*\b(process )?synchroni[sz]ation|synchroni[sz]ation\b.*\bwhy\b", "critical_section",
     "Because processes that share data run concurrently and can be interrupted at any instruction. Without "
     "coordination the result depends on the timing (a **race condition**): two threads doing count++ can lose an "
     "update, and a consumer can read from an empty buffer. Synchronization makes critical sections mutually "
     "exclusive and orders the steps that depend on each other.", True),
    (r"disabl\w* (the )?interrupts?", "critical_section",
     "On a **single CPU**, disabling interrupts during the critical section gives mutual exclusion (nothing can "
     "preempt the process) and progress, but bounded waiting isn't guaranteed, and letting user processes do it is "
     "dangerous (one might never turn them back on).\n\nOn a **multiprocessor** it doesn't work: disabling interrupts "
     "on one CPU doesn't stop the others from entering, and broadcasting the disable to all CPUs is slow. That's why "
     "we use atomic instructions (test_and_set, compare_and_swap) and the locks built on them.", True),
    (r"(empty\b.*\bfull|full\b.*\bempty)\b.*\b(why|need|both|alone)\b|\bmutex alone\b|\bwhy\b.*\bcounting semaphores?\b.*\bproducer", "bounded_buffer",
     "`mutex` only makes the buffer updates happen one at a time; it can't make anyone **wait for a condition**. "
     "`empty` counts free slots, so a producer blocks when the buffer is full; `full` counts filled slots, so a "
     "consumer blocks when it is empty. With only mutex, a producer could write into a full buffer and a consumer "
     "could take from an empty one. They are **counting** semaphores because there are n slots to count.", True),
    (r"binary semaphore\b.*\bproducer|producer\b.*\bbinary semaphore", "bounded_buffer",
     "Only for a buffer of **size 1**: then empty and full can be binary (empty = 1, full = 0) and the producer and "
     "consumer strictly alternate. For n slots, empty and full must be counting semaphores (starting at n and 0); "
     "mutex is the binary one.", True),
    (r"buffer (of )?size (1|one)|size[- ](1|one) buffer|one[- ]slot buffer", "bounded_buffer",
     "**empty = 1, full = 0, mutex = 1.** The producer and consumer then strictly alternate: produce, consume, "
     "produce, …", True),
    (r"(wait|signal)\b.*\bnot atomic|non[- ]?atomic\b.*\b(wait|signal|semaphore)|(wait|signal)\b.*\b(weren'?t|isn'?t|aren'?t) atomic", "semaphores",
     "Then the semaphore itself has a race condition: two processes could both read S = 1, both decrement it and "
     "both enter the critical section, or a wake-up could be lost. That's why wait and signal must run atomically: on "
     "one CPU by briefly disabling interrupts, on a multiprocessor with an atomic instruction or a spinlock around "
     "their short bodies.", True),
    (r"semaphore\b.*\binitiali[sz]\w*\b.*-\s*1|initiali[sz]\w*\b.*\b(to )?-\s*1\b", "semaphores",
     "A semaphore is initialised to a **non-negative** value (the number of free resources), so -1 is not valid by "
     "definition. If you did it anyway in the blocking version, the first wait would make it -2 and block, and two "
     "signals would be needed before anyone could pass. A negative value is supposed to mean \"this many processes are "
     "waiting\", which only wait() can cause.", True),
    (r"\bsignal\b.*\b(zero|0)\b|\b(zero|0)\b.*\bsignal\b", "semaphores",
     "signal(S) **increments** S, so 0 becomes 1. In the blocking version it also wakes a waiting process if, after "
     "the increment, S ≤ 0; when S was 0 nobody was waiting, so nobody is woken. The signal is not lost: the next "
     "wait() finds S = 1 and passes.", True),
    (r"\b(p0|zero[- ]?indexed)\b.*\b(first|start\w*|index\w*|or p1)\b|\bprocess names\b.*\bp0", "bankers",
     "Process names are just labels. Silberschatz numbers the Banker's examples from **P0**, and the app keeps the "
     "names the question uses (P0…P4 or P1…P5). The safety algorithm scans them in the order they are listed.", True),
    (r"(\bsrtf\b|shortest[- ]remaining)\b.*\b(practice|practical|real|implement\w*|used|use)\b", "srtf",
     "Three reasons:\n\n1. It needs the length of every process's **next CPU burst**, which the OS can't know; it can "
     "only predict it from past bursts (exponential averaging).\n2. **Overhead:** every arrival means comparing "
     "remaining times, and every preemption costs a context switch.\n3. **Starvation:** long jobs can be passed over "
     "indefinitely.\n\nReal systems get a similar effect without knowing bursts, using multilevel feedback queues "
     "that favour short and I/O-bound jobs.", True),
    (r"\bsrtf\b.*\boverhead|overhead\b.*\bsrtf", "srtf",
     "On every arrival the scheduler must compare remaining times (and keep the ready queue ordered by remaining "
     "time), and every preemption costs a **context switch**. SRTF also needs a prediction of each burst. With many "
     "short arrivals this adds up, which is one reason real systems approximate it with multilevel feedback queues.", True),
    (r"(round[- ]?robin|\brr\b)\b.*\b(more|higher|worse|greater|larger)\b.*\b(sjf|shortest)|\bwhy\b.*\b(rr|round[- ]?robin)\b.*\bwait\w*\b.*\b(more|higher)", "rr",
     "Because Round Robin **interleaves everyone**: a short job that could have finished early waits in line behind "
     "slices of every other job, and long jobs keep going to the back too. SJF finishes the short jobs first, which "
     "is exactly what minimises the average. Round Robin's strength is response time: everyone starts quickly.", True),
    (r"(coffman|(four|4) (necessary )?conditions)\b.*\b(break|easiest|prevent\w*|which)\b", "deadlock",
     "**Mutual exclusion, hold and wait, no preemption, circular wait.** The one usually broken in practice is "
     "**circular wait**: number the resources and always request them in increasing order (lock ordering). Mutual "
     "exclusion can't be dropped for resources that can't be shared, preventing hold and wait wastes resources, and "
     "preemption only works for resources whose state can be saved (CPU, memory).", True),
    (r"(all|every) (five|5|the) (philosophers?|forks?|chopsticks?)\b.*\b(left|right)\b.*\b(coffman|condition)|which coffman", "dining",
     "**All four** hold at once: **mutual exclusion** (a chopstick is used by one philosopher at a time), **hold and "
     "wait** (each holds the left chopstick while waiting for the right), **no preemption** (nobody takes a chopstick "
     "from a neighbour), and **circular wait** (P0 waits for P1, P1 for P2, …, P4 for P0). Breaking any one prevents "
     "the deadlock; the usual fixes break circular wait or hold and wait.", True),
    (r"(starvation|deadlock)\b.*\b(one without|without the other|without each other)", "deadlock",
     "**Deadlock:** a set of processes each waiting for a resource held by another one in the set, so none of them "
     "can continue. **Starvation:** a process could run but keeps being passed over while others progress.\n\n"
     "**Yes, either can happen without the other.** Starvation without deadlock: a low-priority process under "
     "priority scheduling while high-priority jobs keep arriving. Deadlock means every process in the cycle waits "
     "forever, so those processes are starved too, but the cause is the circular wait, not unfair scheduling.", True),
    # ---- past-paper theory (24 Oct: eval/pyq_compare.py; both models got about half of these wrong) ----
    (r"context switch\w*.*\b(efficien\w*|overhead|round[- ]?robin|\brr\b|quantum|reduce\w*|cost\w*)\b|\b(overhead|efficien\w*)\b.*context switch", "rr",
     "Every context switch is **pure overhead**: the CPU saves the running process's registers and state into its PCB, "
     "loads the next one's, and the caches go cold. No useful work is done meanwhile.\n\n"
     "Round Robin switches at the end of **every** quantum, so the smaller the quantum, the larger the share of CPU "
     "time lost to switching: if a switch costs about a tenth of the quantum, roughly 10% of the CPU is wasted. So q "
     "should be much larger than the switch time (rule of thumb: about 80% of CPU bursts should finish within one "
     "quantum). But a very large q turns Round Robin into FCFS.", True),
    (r"(time )?quantum\b.*\b(very |too )?(small|short|tiny|low|large|big|huge|long|larger|bigger|greater|smaller|longer|shorter|exceed\w*|increas\w*|decreas\w*)\b|"
     r"\b(small|short|tiny|large|big|huge|increas\w*|decreas\w*)\b.*\b(time )?quantum\b|"
     r"\bchoos\w*\b.*\bquantum\b", "rr",
     "- **Too small:** the CPU spends a large share of its time on context switches instead of real work (in the "
     "limit every process seems to run on its own slow CPU). Throughput drops.\n"
     "- **Too large:** almost every process finishes within one quantum, so Round Robin becomes **FCFS**, and "
     "interactive users wait behind long jobs (poor response time).\n\n"
     "A good quantum is large compared with the context-switch time but small enough to keep response time low: the "
     "rule of thumb is that about 80% of CPU bursts should be shorter than the quantum (typically 10–100 ms).", True),
    (r"(\bsjf\b|shortest[- ]job).*\b(difficult|hard|impossibl\w*|practical|implement\w*|real|problem|disadvantages?|drawbacks?|limitations?)\b", "sjf",
     "Because the scheduler must know the length of each process's **next CPU burst**, and it can't know that in "
     "advance. It can only **predict** it from past bursts by exponential averaging: τ(n+1) = α·t(n) + (1 − α)·τ(n), "
     "usually with α = 1/2. A wrong prediction gives a schedule that is no longer optimal.\n\n"
     "SJF can also **starve** long jobs if short ones keep arriving (fixed with aging). It is used more in long-term "
     "(batch) scheduling, where users give a time limit for the job.", True),
    (r"(predict\w*|estimat\w*|guess\w*)\b.*\bburst|\bburst\b.*\b(predict\w*|estimat\w*)|exponential\w* averag", "sjf",
     "With **exponential averaging** of the measured bursts:\n\n"
     "τ(n+1) = α · t(n) + (1 − α) · τ(n)\n\n"
     "t(n) is the length of the n-th CPU burst that just happened, τ(n) the previous prediction, and 0 ≤ α ≤ 1 sets "
     "how much the latest burst counts (often α = 1/2). With α = 0 the prediction never changes; with α = 1 only the "
     "last burst counts. Older bursts count less and less, because each step multiplies their weight by (1 − α).", True),
    (r"when\b.*\b(scheduler|scheduling)\b.*\b(decisions?|decide|runs?|invoked|called)\b|scheduling decisions?\b.*\b(when|occur|happen|take place)\b", "basics",
     "In four situations:\n\n"
     "1. A process switches from **running to waiting** (an I/O request, or a wait() call).\n"
     "2. A process switches from **running to ready** (an interrupt, such as the timer at the end of a time slice).\n"
     "3. A process switches from **waiting to ready** (its I/O finishes).\n"
     "4. A process **terminates**.\n\n"
     "If scheduling happens only in 1 and 4, the scheduling is **non-preemptive**; if it also happens in 2 and 3, it "
     "is **preemptive**.", True),
    (r"turn\s*-?around\b.*\bresponse|response\b.*\bturn\s*-?around|waiting time\b.*\bresponse time|response time\b.*\bwaiting time", "basics",
     "- **Turnaround time:** the whole stay in the system, TAT = CT − AT (completion minus arrival).\n"
     "- **Waiting time:** the part of that stay spent in the ready queue, WT = TAT − BT.\n"
     "- **Response time:** how long until the process gets the CPU for the **first** time, RT = first start − AT.\n\n"
     "For non-preemptive algorithms (no I/O) a process waits only before it first runs, so RT = WT. In Round Robin "
     "the response time is short even when the turnaround time is long, which is why it suits interactive systems.", True),
    (r"\bdispatch(er|ing| latency)\b", "basics",
     "The **dispatcher** is the module that gives the CPU to the process the short-term (CPU) scheduler chose. It "
     "switches context, switches to user mode, and jumps to the right place in the program to resume it.\n\n"
     "**Dispatch latency** is the time it takes to stop one process and start another. The dispatcher runs on every "
     "switch, so this time should be as short as possible.", True),
    (r"(\bsrtf\b|shortest[- ]remaining).*(\bsjf\b|shortest[- ]job)|(\bsjf\b|shortest[- ]job).*(\bsrtf\b|shortest[- ]remaining)", "srtf",
     "**SRTF is the preemptive version of SJF.** When a new process arrives with a burst shorter than the running "
     "process's *remaining* time, SRTF switches to it; SJF always lets the running process finish.\n\n"
     "So under SRTF a short job never waits behind a long one that happened to start first, and the average waiting "
     "time is lower or equal: SRTF is optimal among all algorithms, SJF only among non-preemptive ones. The costs are "
     "more context switches and possible starvation of long jobs. On a tie the running process continues (course "
     "convention).", True),
    (r"(waiting time|\bwt\b|turn\s*-?around|\btat\b).*\b(i/?o|input|output)\b|\b(i/?o)\b.*\b(waiting time|\bwt\b|turn\s*-?around)", "basics",
     "For a process like CPU 4, I/O 3, CPU 3:\n\n"
     "- After its first CPU burst it **leaves** the ready queue for the I/O (which runs in parallel with the CPU) and "
     "**re-enters** the ready queue when the I/O finishes.\n"
     "- CT is the end of its **last** CPU burst; TAT = CT − AT as usual.\n"
     "- **WT = TAT − (all CPU bursts) − (I/O time)**: only the time spent in the ready queue.\n\n"
     "Some answer keys count the I/O as waiting and use WT = TAT − (CPU bursts). Write down which convention you use "
     "in the exam; the tutor accepts both.", True),
    (r"\bcompar\w*\b.*(fcfs|\bsjf\b|round[- ]?robin|\brr\b).*(fcfs|\bsjf\b|round[- ]?robin|\brr\b|priority)|"
     r"(fcfs|\bsjf\b|round[- ]?robin|\brr\b)\b.*\binteractive\b|which (algorithm|scheduling\w*)\b.*\b(interactive|time[- ]shar\w*|best)", "basics",
     "- **FCFS:** simplest and fair by arrival, non-preemptive; one long job makes everyone wait (convoy effect), so "
     "response time is poor.\n"
     "- **SJF / SRTF:** minimum average waiting time, but needs the next burst length (only predicted) and can starve "
     "long jobs.\n"
     "- **Round Robin:** each process gets a quantum in turn: the best **response time**, built for time-sharing, at "
     "the cost of more context switches and usually a higher average turnaround than SJF.\n\n"
     "For an **interactive** system Round Robin (or a multilevel feedback queue built on it) is the usual choice.", True),
    (r"cpu[- ]bound|i/?o[- ]bound|cpu[- ]i/?o burst|burst cycle", "basics",
     "Process execution alternates **CPU bursts** and **I/O waits** (the CPU–I/O burst cycle).\n\n"
     "- **CPU-bound:** a few long CPU bursts (heavy computation).\n"
     "- **I/O-bound:** many short CPU bursts between I/O waits (an editor, a browser).\n\n"
     "The mix matters: the long-term scheduler should admit a mix so both the CPU and the devices stay busy. "
     "Schedulers that favour short bursts (SJF, multilevel feedback queues) keep I/O-bound processes responsive; with "
     "FCFS one CPU-bound process holds everyone up (the convoy effect).", True, "burst_cycle"),
    (r"peterson", "critical_section",
     "**Peterson's solution** (two processes Pi and Pj) uses `flag[2]` (also called interested[]) and `turn`:\n\n"
     "```\nflag[i] = true;   turn = j;\nwhile (flag[j] && turn == j) ;   /* wait */\n    /* critical section */\n"
     "flag[i] = false;\n```\n\n"
     "Each process says it wants to enter and politely gives the turn to the other. If both want in, `turn` decides, "
     "and only one can pass. It satisfies **mutual exclusion, progress and bounded waiting**.\n\n"
     "It is written for **two** processes only; for n processes you need a generalisation such as the Bakery "
     "algorithm. On modern CPUs that reorder memory operations it also needs memory barriers.", True, "peterson"),
    (r"bakery", "critical_section",
     "**Lamport's Bakery algorithm** solves the critical section for **n** processes, like taking a token at a shop "
     "counter:\n\n"
     "1. Entry: `choosing[i] = true; number[i] = 1 + max(number[0..n−1]); choosing[i] = false;`\n"
     "2. For every other process j: wait while `choosing[j]`, then wait while `number[j] != 0` and "
     "`(number[j], j) < (number[i], i)`: a smaller token goes first, and on equal tokens the smaller id goes first.\n"
     "3. Exit: `number[i] = 0;`\n\n"
     "It gives mutual exclusion, progress and bounded waiting (processes enter in token order).", True),
    (r"counter\s*\+\+|count\s*\+\+|\bincrement\w*\b.*\b(race|wrong|lock|threads?|lost)\b|\b(race|lost update)\b.*\bincrement", "critical_section",
     "Because `counter++` is **three machine steps**: load counter into a register, add 1, store it back. If thread A "
     "loads 5 and thread B also loads 5 before A stores, both store 6: one increment is **lost**. That's a race "
     "condition, so two threads doing 10000 increments each often end below 20000.\n\n"
     "Fix: make the update a critical section, e.g. `pthread_mutex_lock(&m); counter++; pthread_mutex_unlock(&m);` "
     "(or use an atomic increment). Then the result is always 20000.", True),
    (r"\bs1\b.*\bs2\b|\bs2\b.*\bs1\b|semaphores?\b.*\b(enforc\w*|force|guarantee\w*|ensure\w*|make)\b.*\b(run|execut\w*)\b.*\b(before|after|order)\b|"
     r"\border(ing)? (of execution )?between (two )?processes", "semaphores",
     "Use a semaphore `synch` initialised to **0**:\n\n"
     "```\nP1:  S1;  signal(synch);\nP2:  wait(synch);  S2;\n```\n\n"
     "If P2 gets there first, wait(synch) blocks it until P1 has run S1 and signalled. If P1 is first, synch becomes "
     "1 and P2 passes straight through. Either way S2 runs after S1.", True),
    (r"(sequence|trace|scenario|interleaving|order of execution)\b.*\bdeadlock\b.*\b(producer|consumer|bounded)|wait\s*\(\s*empty\s*\).*wait\s*\(\s*mutex|wait\s*\(\s*mutex\s*\).*wait\s*\(\s*(empty|full)|order of (the )?waits?|swap\w*\b.*\bwaits?\b", "bounded_buffer",
     "Because of what happens when the buffer is **full**. If the producer takes `mutex` first, `wait(empty)` blocks "
     "it **while it still holds mutex**. The consumer then blocks on `wait(mutex)`, so it can never remove an item and "
     "`signal(empty)`: **deadlock**.\n\n"
     "Waiting on the counting semaphore first means a producer takes mutex only when it can actually add an item. "
     "The same goes for the consumer: `wait(full)` before `wait(mutex)`. The order of the two signals doesn't cause "
     "this problem.\n\nThe exact sequence, with the buffer full (empty = 0, full = n, mutex = 1):\n\n"
     "1. Producer: wait(mutex), so mutex = 0, and it enters.\n2. Producer: wait(empty), so empty = −1: it **blocks "
     "while holding mutex**.\n3. Consumer: wait(full) passes (full = n − 1).\n4. Consumer: wait(mutex), so mutex = −1: "
     "it blocks.\n\nNow each waits for the other forever. With the waits in the right order, the producer blocks on "
     "empty *before* taking mutex, so the consumer can still get in and free a slot.", True),
    (r"readers?\b.*\bwriters?\b.*\bstarv|\bstarv\w*\b.*\b(readers?|writers?)\b|(first|second) readers?[- ]writers?", "readers_writers",
     "In the **first** readers–writers problem (readers have priority), **writers** can starve. No reader waits "
     "unless a writer already has the shared data, so while readers keep arriving, readcount never drops to 0 and the "
     "writer never gets `wrt`.\n\n"
     "The **second** problem gives writers priority: once a writer is waiting, no new reader may start, and then "
     "**readers** can starve. A fair version makes readers and writers queue in arrival order (an extra semaphore "
     "that everyone takes first).", True),
    (r"(dining|philosoph\w*)\b.*\b(avoid\w*|prevent\w*|solv\w*|solution|fix\w*|deadlock)\b|"
     r"\b(avoid\w*|prevent\w*|deadlock|fix\w*|solv\w*|solution)\b.*\b(dining|philosoph\w*)", "dining",
     "If every philosopher picks up the left chopstick and then waits for the right one, all five can hold one and "
     "wait forever: **hold and wait plus circular wait**. Ways to avoid it:\n\n"
     "- Allow at most **four** philosophers at the table at once (a counting semaphore initialised to 4).\n"
     "- Pick up chopsticks only if **both** are free, inside a critical section (the monitor solution in the notes).\n"
     "- **Asymmetric** order: odd philosophers pick up the left chopstick first, even ones the right, so no circle "
     "forms.\n\n"
     "Deadlock-free is not automatically starvation-free: a philosopher can still be passed over repeatedly.", True),
    (r"\bmonitors?\b", "critical_section",
     "A **monitor** is a language construct: shared data plus the procedures that use it, where only **one** process "
     "can be active inside at a time. Mutual exclusion is automatic, the compiler adds it.\n\n"
     "To wait for a condition it has **condition variables**: `x.wait()` suspends the caller (and lets another process "
     "into the monitor), `x.signal()` resumes exactly one waiting process and **does nothing** if none is waiting.\n\n"
     "Compared with a semaphore: with semaphores the programmer must put every wait() and signal() in the right place, "
     "and one mistake breaks mutual exclusion or deadlocks. A semaphore also remembers a signal (S goes up), while "
     "`x.signal()` with no waiter is lost. Monitors can be implemented with semaphores.", True, "monitors"),
    (r"busy[- ]wait\w*|spin\s*-?locks?", "critical_section",
     "**Busy waiting:** a process that can't enter keeps looping on a condition, using the CPU without doing any "
     "work. A **spinlock** is a lock that waits this way.\n\n"
     "It is acceptable when the lock is held for a **very short** time on a **multiprocessor**: spinning on one core "
     "is cheaper than blocking and rescheduling (roughly, when the wait is shorter than two context switches). It is a "
     "bad idea on a single CPU, where the lock holder can't run while you spin, or for long critical sections; use a "
     "blocking semaphore there.", True),
    (r"\b(at most|maximum|max|only|limit\w*|no more than)\b.*\b(users?|processes|connections|people|cars|seats|students|threads|clients)\b|"
     r"counting semaphore\b.*\b(limit|allow|users?|connections|capacity)\b", "semaphores",
     "Use a **counting semaphore initialised to the capacity**:\n\n"
     "```\nsemaphore slots = 10;\n\nuser:  wait(slots);\n       /* use the database */\n       signal(slots);\n```\n\n"
     "The first 10 users pass. The 11th user's wait() finds no free slot and blocks until someone leaves and calls "
     "signal(). If the users also update shared data inside, protect that with a separate `mutex = 1`.", True),
    (r"prevention\b.*\bavoidance|avoidance\b.*\bprevention", "deadlock",
     "- **Prevention** makes deadlock impossible by design: it makes sure at least one of the four conditions can "
     "never hold. For example, request all resources at once (no hold and wait), allow preemption, or number the "
     "resources and request them only in increasing order (no circular wait). No run-time knowledge is needed, but "
     "resources are used less efficiently.\n"
     "- **Avoidance** allows all four conditions but decides each request **at run time**. It needs each process's "
     "maximum claim in advance and grants a request only if the system stays in a **safe state** (the Banker's "
     "algorithm, or the resource-allocation-graph algorithm with claim edges when every resource has one instance).", True,
     "prevention"),
    (r"\b(two|2) processes\b.*\b(at most|max\w*)\b.*\b(two|2)\b.*\b(three|3)\b", "deadlock",
     "**No.** In the worst case each process holds 1 instance and wants 1 more. That uses 2 of the 3 instances, so 1 "
     "is still free: one process gets it, finishes and releases both.\n\n"
     "General rule: with n processes each needing at most m instances of a resource that has R instances, deadlock is "
     "impossible if **R ≥ n(m − 1) + 1**. Here 3 ≥ 2 × (2 − 1) + 1.", True),
    (r"\brecover\w*\b.*\bdeadlock|deadlock\b.*\brecover\w*", "deadlock",
     "Once a deadlock is detected there are two ways out:\n\n"
     "1. **Process termination:** abort all deadlocked processes (certain, but expensive), or abort them **one at a "
     "time**, running detection again after each, until the cycle is gone. Choose victims by priority, how long they "
     "have run and how much is left, and the resources they hold.\n"
     "2. **Resource preemption:** take resources from a victim and give them to others. The victim must be **rolled "
     "back** to a safe state (often a full restart), and the choice must avoid **starvation**: count the number of "
     "rollbacks in the cost so the same process isn't picked every time.", True, "recovery"),
    (r"\brequest\w*\b.*\bneed\b|\bneed\b.*\brequest\w*\b", "bankers",
     "Because a request larger than **Need** means the process is asking for more than the **maximum** it declared "
     "(Need = Max − Allocation). The Banker's algorithm relies on those maximums, so that is an **error**, not "
     "something to wait for.\n\n"
     "Only a valid request is then compared with **Available** (if it is larger, the process waits), and only then "
     "does the system pretend to grant it and run the safety algorithm. Example from CAT-2 2025-26: P2's request "
     "(0, 3, 0, 0) is refused at the first step because its need is (1, 0, 1, 2).", True, "bankers_request"),
    (r"wait[- ]for graph", "deadlock",
     "A **wait-for graph** has only process nodes: an edge Pi → Pj means Pi is waiting for a resource that Pj holds. "
     "You get it from the resource-allocation graph by removing the resource nodes and joining the edges.\n\n"
     "It can be used only when **every resource type has a single instance**. Then a cycle in the wait-for graph "
     "means deadlock, and detection is just looking for a cycle. With several instances per resource, use the "
     "detection algorithm instead (like the Banker's safety check, with Request in place of Need).", True, "detection"),
    (r"\b(prevent\w*|break\w*|avoid\w*|eliminat\w*|deny\w*)\b.*\bcircular wait|circular wait\b.*\b(prevent\w*|break\w*|avoid\w*)\b", "deadlock",
     "Give every resource type a number (R1, R2, …) and make every process request resources **only in increasing "
     "order**. A process holding Rj may request Ri only if i > j; otherwise it must first release what it holds.\n\n"
     "A cycle P1 → P2 → … → P1 would need some process to request a lower-numbered resource while holding a higher "
     "one, which the rule forbids, so no cycle can form. In practice: always take locks in the same order. The dining "
     "philosophers' asymmetric fix breaks the circle in the same way.", True, "prevention"),
    (r"types? of schedulers?|(long|short|medium)[- ]term scheduler|job scheduler|degree of multi-?programming|\bswapping\b",
     "basics",
     "There are three schedulers:\n\n"
     "- **Long-term (job) scheduler:** chooses which jobs are loaded from disk into memory (the ready queue). It runs "
     "rarely and controls the **degree of multiprogramming**; it should admit a good mix of CPU-bound and I/O-bound "
     "processes.\n"
     "- **Short-term (CPU) scheduler:** picks the next process from the ready queue to run on the CPU. It runs very "
     "often (every few milliseconds), so it must be fast. FCFS, SJF, Round Robin and priority are its algorithms.\n"
     "- **Medium-term scheduler:** **swaps** a partly executed process out of memory to disk and back in later, to "
     "lower the degree of multiprogramming.", True, "schedulers"),
    (r"scheduling queues?|job queue|device queues?|queu(e|ing) diagram", "basics",
     "A process moves between **scheduling queues**: the **job queue** (every process in the system), the **ready "
     "queue** (in memory, waiting for the CPU) and **device (I/O) queues** (waiting for a device). The queueing "
     "diagram shows the cycle: the CPU scheduler dispatches a process from the ready queue; it leaves the CPU when it "
     "finishes, issues an I/O request (to a device queue), creates a child, or its time slice expires (back to the "
     "ready queue).", True, "queues"),
    (r"multi-?level (feedback )?queues?|\bmlfq\b", "rr",
     "**Multilevel feedback queue** scheduling uses several ready queues with different priorities, and processes "
     "**move between them** according to how they behave. A typical setup: Q0 is Round Robin with q = 8 ms, Q1 is "
     "Round Robin with q = 16 ms, Q2 is FCFS.\n\n"
     "A new process enters Q0. If it uses its whole quantum it drops to the next queue; a lower queue runs only when "
     "the higher ones are empty. So short, I/O-bound processes stay at high priority and CPU-bound ones sink. A process "
     "that waits too long in a low queue is moved up (**aging**), which prevents starvation.\n\n"
     "In a plain **multilevel queue** (no feedback), each process stays in the queue it was first assigned to.", True,
     "mlfq"),
    (r"inter-?process communication|\bipc\b|message passing|shared memory", None,
     "**Inter-process communication (IPC)** lets cooperating processes exchange data (for information sharing, "
     "computation speed-up, modularity and convenience). There are two models:\n\n"
     "- **Shared memory:** a region both processes can read and write directly. Fast, since no system call is needed "
     "per access, but the processes must synchronize themselves: the producer–consumer buffer is the classic example.\n"
     "- **Message passing:** send() and receive() through the kernel. Easier and works across machines, but slower.\n\n"
     "Message-passing design choices: direct or indirect (mailbox / port) naming, blocking or non-blocking send and "
     "receive, and the buffer's capacity (zero, bounded or unbounded).", False, "ipc"),
    (r"^(?!.*(philosoph|dining|chopstick)).*(\bfork\s*\(|\bfork\b.*\b(system call|syscall|child|parent|returns?|process(es)?|times|called)\b|"
     r"\b(system call|syscall|child process)\b.*\bfork\b)", None,
     "**fork()** creates a new process, the **child**, as a copy of the calling process, the **parent**: same code, "
     "data and open files, but its own address space and a different PID. Both continue from the instruction after "
     "fork().\n\nIt returns **0 in the child**, the **child's PID (a positive number) in the parent**, and **−1** if "
     "no child could be created. n fork() calls in a row give **2ⁿ processes** in total: after three forks there are "
     "8 processes, so a printf after them prints 8 times.", False, "fork"),
    (r"\bwait\s*\(\s*\)\s*(system call|syscall)|\bwait\b\s*(system call|syscall)|\bzombie|\borphan|"
     r"\bwait\b.*\b(child|parent)\b|\b(child|parent)\b.*\bwait\b", None,
     "**wait()** blocks the parent until one of its children terminates; it returns that child's PID and can collect "
     "its exit status. Without it, parent and child run concurrently and their output can appear in any order; with "
     "wait() in the parent, the child's output comes first.\n\n"
     "A child that has finished but has not been waited for is a **zombie**; a child whose parent exited first is an "
     "**orphan** (adopted by init).\n\n_This is the system call, not the semaphore operation wait(S)._", False, "wait"),
    (r"\bexec(l|lp|le|v|vp|ve|vpe)?\b", None,
     "The **exec** family (execl, execlp, execv, execvp, …) **replaces** the program of the calling process with a "
     "new one: same PID, new code, data and stack. If exec succeeds it never returns, so the lines after it don't "
     "run; if it fails it returns −1.\n\n"
     "**execv(path, argv)** takes the program's path and an argument array ending in NULL; **execlp(file, arg0, …, "
     "NULL)** takes the arguments as a list ending in NULL and searches PATH for the file. fork() followed by exec() "
     "in the child is how a shell runs a command.", False, "exec"),
    (r"\bsleep\s*\(|\bexit\s*\(|\b(sleep|exit)\b.*\b(system call|syscall)\b", None,
     "**sleep(n)** puts the calling process in the waiting (blocked) state for n seconds, so the CPU can run other "
     "processes meanwhile.\n\n**exit(status)** terminates the calling process: status 0 means success and a non-zero "
     "value an error; the parent can collect it with wait(). Code after exit() never runs.", False, "sleep_exit"),
    (r"(\bsjf\b|shortest[- ]job).*\b(optimal|best|minimum|minimi[sz]e)|\b(optimal|best)\b.*(\bsjf\b|shortest[- ]job)", "sjf",
     "**Yes, with a condition.** Among **non-preemptive** algorithms, SJF gives the **minimum average waiting time** when "
     "all the jobs are available together: putting a shorter job before a longer one saves the short job more waiting "
     "than it costs the long one. Allowing preemption, **SRTF** is the optimal one.\n\n"
     "Two catches: the OS cannot know the next CPU burst in advance, so real systems only **estimate** it (exponential "
     "averaging of past bursts), and long jobs can **starve** if short ones keep arriving.", True),
    (r"(round[- ]?robin|\brr\b).*starv|starv.*(round[- ]?robin|\brr\b)", "rr",
     "**No.** In Round Robin every process in the ready queue gets one time quantum per round, so with n processes and "
     "quantum q a process waits at most **(n − 1) × q** before its next turn. Nothing can overtake it forever.\n\n"
     "Starvation is a risk in **SJF/SRTF** (long jobs keep being passed over) and in **priority scheduling** "
     "(low-priority jobs), where **aging** is the usual fix.", True),
    (r"unsafe.*deadlock|deadlock.*unsafe", "bankers",
     "**No: unsafe ≠ deadlock.** A state is **safe** if there is at least one order (a safe sequence) in which every "
     "process can get its remaining Need and finish. **Unsafe** only means no such order is guaranteed: if the processes "
     "ask for their maximum, a deadlock **can** happen, but it has not happened yet and may never happen (a process may "
     "release resources early or never ask for its full Max).\n\n"
     "So deadlocked states are a subset of unsafe states. The Banker's algorithm avoids deadlock by never granting a "
     "request that would leave the system unsafe.", True),
    (r"\bcycle\b.*\b(deadlock|always)\b|(resource[- ]allocation graph|\brag\b).*\bcycle\b", "deadlock",
     "**Only if every resource has a single instance.** With one instance per resource type, a cycle in the "
     "resource-allocation graph means deadlock. With **several instances**, a cycle is necessary but **not sufficient**: "
     "a process outside the cycle can release an instance and break it (Silberschatz Fig. 7.3 has a cycle and no "
     "deadlock).\n\nNo cycle always means no deadlock. With several instances, run the detection algorithm to decide.", True, "rag"),
    (r"semaphore.*\bnegative\b|\bnegative\b.*semaphore", "semaphores",
     "**In the blocking implementation, yes.** wait() decrements first and blocks the process if the value is now below "
     "0, so **S = −k means k processes are waiting** in the semaphore's queue.\n\n"
     "In the **busy-waiting** definition (P and V in the Module 4 notes: wait spins while S ≤ 0, then decrements), "
     "S never goes below 0.", True),
    (r"\bnon[- ]?pre-?emptive\b.*\b(vs|versus|differ\w*|compare\w*)\b|\b(vs|versus|differ\w*|compare\w*)\b.*\bnon[- ]?pre-?emptive\b|"
     r"\bpre-?emptive\b.*\b(vs|versus)\b.*\bnon", "basics",
     "**Non-preemptive:** once a process gets the CPU, it keeps it until it finishes its burst or blocks for I/O "
     "(FCFS, SJF, non-preemptive priority).\n\n"
     "**Preemptive:** the OS can take the CPU away from the running process: when a shorter job arrives (SRTF), a "
     "higher-priority one arrives (preemptive priority) or the time quantum runs out (Round Robin).\n\n"
     "Preemptive scheduling gives better response time, at the cost of more context switches and more care with "
     "shared data.", True),
    (r"\bconvoy\b", "fcfs",
     "The **convoy effect** happens in **FCFS**: one long CPU-bound process holds the CPU while many short processes "
     "queue behind it, like cars stuck behind a slow truck. The short jobs' waiting times grow, the average waiting "
     "time goes up, and I/O devices sit idle while everyone waits.\n\nSJF or Round Robin avoid it.", True),
    (r"\bage?ing\b", "priority",
     "**Aging** prevents **starvation**: the longer a process waits, the higher its priority becomes (for example, "
     "+1 priority for every 15 minutes of waiting). Eventually even the lowest-priority process becomes the highest and "
     "gets the CPU.\n\nIt is used with **priority scheduling**, and the same idea helps long jobs under SJF.", True),
    (r"deadlock.*\b(one|single|a|1)\s+(process|thread)\b(?!es)|\b(one|single)\s+(process|thread)\b.*deadlock", "deadlock",
     "**Not in the textbook sense.** A deadlock is a *set* of processes each waiting for a resource held by another "
     "one in the set, and circular wait needs **at least two** processes (P1 → P2 → P1).\n\n"
     "A single thread can still hang itself, for example by calling wait(mutex) twice on a mutex it already holds. "
     "That is sometimes called self-deadlock, but it is a programming bug, not the four-condition deadlock this "
     "course examines.", True),
    (r"starvation.*deadlock|deadlock.*starvation", "deadlock",
     "**Deadlock:** a set of processes each waiting for a resource held by another one in the set, so **none of them** "
     "can ever continue (circular wait).\n\n"
     "**Starvation:** a process *could* run, but keeps being passed over, like a low-priority job while higher-priority "
     "jobs keep arriving. The others still make progress.\n\n"
     "Aging fixes starvation; deadlock needs prevention, avoidance (Banker's algorithm) or detection and recovery.", True),
    (r"\bmutex\b.*\b(vs|versus|differ\w*|same)\b.*semaphore|semaphore.*\b(vs|versus|differ\w*|same)\b.*\bmutex\b|"
     r"binary semaphore.*\b(vs|versus|differ\w*|same)\b|\b(vs|versus|differ\w*)\b.*binary semaphore|"
     r"binary semaphore\b.*\b(basically|equivalent|like|just|really)\b.*\bmutex|mutex\b.*\b(basically|equivalent|like|just)\b.*binary semaphore|"
     r"\b(binary|counting)\b[^.?]{0,20}\b(or|vs)\b[^.?]{0,20}\b(binary|counting)\b", "semaphores",
     "A **counting semaphore** is an integer that counts n identical resources, and any process can signal it.\n\n"
     "A **mutex** (lock) protects one critical section and has an **owner**: the process that locked it must unlock it. "
     "A **binary semaphore** (values 0 and 1) works like a mutex but has no owner.\n\n"
     "In this course, a semaphore named mutex with initial value 1 is used as the lock: "
     "`wait(mutex); critical section; signal(mutex);`", True),
    (r"test[- ]and[- ]set.*\b(bounded|starv\w*)\b|\bbounded waiting\b.*test[- ]and[- ]set", "critical_section",
     "**No.** Plain test_and_set gives **mutual exclusion** and **progress**, but not **bounded waiting**: a process can "
     "lose the race for the lock every single time.\n\nThe fix in Silberschatz keeps a waiting[] array and, on exit, "
     "hands the lock to the next waiting process in cyclic order, so each one gets in within n − 1 turns.", True, "tas"),
    (r"banker.*\b(real|practice|actual|used|use it|modern|windows|linux)\b|\b(real|practice|modern)\b.*banker", "bankers",
     "**Rarely, in its textbook form.** The Banker's algorithm needs every process to declare its **maximum** need in "
     "advance, a fixed number of processes and resources, and a safety check on every request, which costs "
     "O(m × n²). General-purpose systems like Windows and Linux don't know those maximums, so they don't use it; they "
     "mostly ignore deadlock in user programs (the \"ostrich\" approach) or prevent it with rules such as lock "
     "ordering.\n\nThe idea of **avoidance** (grant a request only if a safe state remains) does appear where demands "
     "are known up front, such as some real-time and embedded systems and resource managers. In this course it "
     "matters because it is how deadlock *avoidance* is examined.", True),
    (r"(normal|ordinary|plain|simple|regular|global|shared|boolean|integer|int)\s+(variable|flag|int|integer|counter)"
     r".*(semaphore|lock|mutex|critical section)|(semaphore|lock|mutex)\b.*\b(normal|ordinary|plain|simple)\s+(variable|flag)", "semaphores",
     "Because checking a normal variable and then changing it are **two separate steps**, and a process can be "
     "interrupted between them. Two processes can both read `flag == 0`, both set it to 1, and both enter the critical "
     "section: a **race condition**, so no mutual exclusion.\n\n"
     "A semaphore's wait() and signal() are **atomic** (the OS or hardware makes the test and the change one "
     "indivisible step), and a process that cannot enter is **blocked** instead of looping and wasting the CPU.", True),
    (r"safe sequence.*\b(unique|only one|one only)\b|\b(unique|only one)\b.*safe sequence|"
     r"safe state\b.*\b(more than one|two|multiple|several|many|different)\b.*\bsequences?|(more than one|two|multiple|several) (valid )?(safe )?sequences", "bankers",
     "**No.** A safe state usually has **several** safe sequences. Any order works as long as each process you pick has "
     "**Need ≤ Work** at its turn. In an exam, check your own sequence step by step: it does not have to match the "
     "textbook's.", True),
    (r"\b(requirements?|conditions?|criteria|properties)\b.*critical[- ]section|critical[- ]section.*\b(requirements?|criteria|properties)\b", "critical_section",
     "A solution to the critical-section problem must satisfy three requirements:\n\n"
     "1. **Mutual exclusion:** at most one process is in its critical section at a time.\n"
     "2. **Progress:** if nobody is inside, only the processes trying to enter decide who goes next, and that decision "
     "cannot be postponed forever.\n"
     "3. **Bounded waiting:** there is a limit on how many times others can enter before a waiting process gets in.", True),
    (r"(?=.*\bprocess(es)?\b)(?=.*\bthreads?\b).*\b(vs|versus|differ\w*|compare\w*)\b", "basics",
     "A **process** is a program in execution with its own address space (code, data, heap), open files and a PCB.\n\n"
     "A **thread** is a unit of execution inside a process. Threads of the same process **share** its code, data and "
     "open files, but each has its **own** registers, program counter and stack.\n\n"
     "Creating and switching threads is cheaper than processes, and threads communicate through shared memory, which "
     "is exactly why they need synchronization.", True, "threads"),
    (r"process control block|\bpcb\b", "basics",
     "The **process control block (PCB)** is the record the OS keeps for each process: process ID, state (new, ready, "
     "running, waiting, terminated), program counter, CPU registers, scheduling information (priority, queue "
     "pointers), memory-management information, accounting information and I/O status (open files, devices).\n\n"
     "On a **context switch** the OS saves the running process's state into its PCB and loads the next one's.", True),
    (r"^\W*(what('?s| is| are)|define|explain|meaning of)\b[^?]*\bcontext switch(es|ing)?\b[\s?.!]*$|^\W*context switch(es|ing)?[\s?.!]*$", "basics",
     "A **context switch** is the CPU moving from one process to another: the OS saves the running process's state "
     "(registers, program counter) in its PCB and loads the saved state of the next one.\n\n"
     "It is pure overhead, since no useful work happens during it. That is why a very small Round Robin quantum is a "
     "bad idea: too much time goes on switching.", True),
    (r"\bsystem calls?\b|\bsyscalls?\b", None,
     "A **system call** is how a program asks the kernel for a service it cannot perform in user mode: reading a file "
     "(read()), creating a process (fork()), allocating memory and so on. The call traps into the kernel (switching to "
     "kernel mode), the kernel does the work, and control returns to the program in user mode.", False, "syscalls"),
    (r"\bthrash", None,
     "**Thrashing** is when the system spends more time paging than executing: processes don't have enough frames for "
     "their working sets, so almost every few instructions cause a page fault. CPU utilization drops, and a scheduler "
     "that admits more processes to raise utilization makes it worse.\n\nThe fix is to give each process enough frames "
     "(working-set model, page-fault frequency) or to lower the degree of multiprogramming.", False),
    (r"page replacement|\blru\b|least recently used|\bbelady|optimal page|\bfifo\b.*\bpages?\b", None,
     "When a page fault finds no free frame, a **page replacement** algorithm chooses the victim:\n\n"
     "- **FIFO** evicts the page that was loaded earliest. It can show **Belady's anomaly**: more frames, more faults.\n"
     "- **Optimal** evicts the page that will not be used for the longest time. It is the best possible, but needs the "
     "future, so it is used as a benchmark.\n"
     "- **LRU** evicts the page that has not been used for the longest time: a good approximation of Optimal, with no "
     "Belady's anomaly.", False),
    (r"virtual memory|demand paging|page faults?", None,
     "**Virtual memory** lets a process run without all of it in RAM: pages are loaded only when they are used "
     "(**demand paging**). Touching a page that isn't in memory causes a **page fault**; the OS loads the page from "
     "disk (evicting another page if no frame is free) and restarts the instruction.", False),
    (r"\bpaging\b|page tables?", None,
     "**Paging** divides a process's logical memory into fixed-size **pages** and physical memory into **frames** of "
     "the same size. A **page table** maps each page number to a frame number, and a logical address is split into "
     "(page number, offset).\n\nPages can go into any free frames, so there is no external fragmentation (only some "
     "internal fragmentation in the last page).", False),
    (r"segmentation|fragmentation", None,
     "**Segmentation** divides a program into variable-size logical segments (code, data, stack), each with a base and "
     "a limit.\n\n**External fragmentation:** enough free memory in total, but split into holes too small to use (a "
     "problem for segmentation and contiguous allocation). **Internal fragmentation:** unused space inside an allocated "
     "block, such as the end of the last page in paging.", False),
    (r"disk scheduling|\bsstf\b|\bc-?scan\b|elevator algorithm|seek time", None,
     "Disk scheduling orders the pending I/O requests to cut seek time:\n\n"
     "- **FCFS:** in arrival order.\n- **SSTF:** the nearest cylinder first (can starve far requests).\n"
     "- **SCAN** (elevator): sweep to one end, then back.\n"
     "- **C-SCAN:** sweep one way, jump back to the start, sweep again (more uniform waiting).\n"
     "- **LOOK / C-LOOK:** like SCAN / C-SCAN, but turn at the last request instead of the disk's end.", False),
]
_COMPILED = [(re.compile(e[0], re.I), e[1], e[2], e[3], e[4] if len(e) > 4 else None) for e in ENTRIES]


def lookup(text: str) -> dict | None:
    """The checked answer for a question, or None. A message with problem data (P1 0 5, arrival, allocation...) is
    about a specific problem: not here. "video" names the lecture clips that go with the answer (tutor/videos.py)."""
    bare_numbers = re.findall(r"(?<![A-Za-z\d.])\d+(?:\.\d+)?(?![A-Za-z\d])", text)
    nonzero = [n for n in bare_numbers if float(n) != 0]
    data_words = re.search(r"\barrival\b|\bburst\b|\balloc|\bavail|\bmax\b|quantum\s*=?\s*\d", text, re.I)
    if len(bare_numbers) >= 4 or (data_words and len(nonzero) >= 2) or \
            re.search(r"\bwhat do (my|the) notes\b|\b(my|the|class|lecture) notes say about\b|\bfrom (my|the) notes\b", text, re.I):
        return None
    for rx, lid, answer, inside, video in _COMPILED:
        if rx.search(text):
            return {"lesson": lid, "text": answer if inside else answer + OUTSIDE, "inside": inside, "video": video or lid}
    return None
