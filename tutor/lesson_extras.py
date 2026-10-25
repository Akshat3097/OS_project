"""
Extra lesson content for teaching from real life and for the "Explain it back" step.

For each lesson:
  real_life       concrete everyday situations and where the idea shows up in a real computer
  ideas           the key ideas a good explanation should contain. Each has
                    statement  what the student should be able to say
                    groups     keyword groups for the offline rubric: the idea is CLEAR if every group
                               has a match, PARTIAL if at least half do (speech-to-text friendly words)
                    question   which question to ask when this idea is missing (see tutor/teachback.py)
  misconceptions  wrong beliefs to listen for (pattern = regex for the offline rubric; empty = LLM only)
  extra_mcq       more multiple-choice questions, appended after the lesson's own (index 3, 4, ...)
"""
from __future__ import annotations

EXTRAS: dict[str, dict] = {
    "basics": {
        "real_life": [
            "**Canteen billing counter.** One cashier (the CPU) and a line of students (processes). You join the line at "
            "12:02 (arrival), billing takes 3 minutes (burst), you leave at 12:10 (completion). You spent 8 minutes there "
            "(turnaround) but only 3 being served, so you waited 5.",
            "**In your laptop.** Chrome, Spotify and VS Code all look like they run together, but each CPU core runs one of "
            "them at a time. The scheduler switches between them thousands of times a second.",
        ],
        "ideas": [
            {"id": "one_cpu", "statement": "One CPU core runs one process at a time; the scheduler picks which ready process runs next.",
             "groups": [["one process", "one at a time", "single", "only one"], ["schedul", "decide", "choose", "pick", "who runs", "ready queue"]],
             "question": {"type": "mcq", "index": 3}},
            {"id": "tat", "statement": "Turnaround time is from arrival to completion: TAT = CT − AT.",
             "groups": [["turnaround", "tat", "turn around"], ["completion", "finish", "complete"], ["arriv"]],
             "question": {"type": "metric", "algorithm": "FCFS", "field": "TAT", "difficulty": 2}},
            {"id": "wt", "statement": "Waiting time is time spent ready but not running: WT = TAT − BT.",
             "groups": [["waiting", "wait"], ["burst", "running", "minus", "subtract", "turnaround"]],
             "question": {"type": "metric", "algorithm": "FCFS", "field": "WT", "difficulty": 2}},
            {"id": "ct_last", "statement": "Completion time is where the process's LAST block ends in the Gantt chart.",
             "groups": [["completion", "finish", "ends", "complete"], ["last", "gantt", "chart", "end of"]],
             "question": {"type": "mcq", "index": 2}},
            {"id": "preemption", "statement": "Non-preemptive: a process keeps the CPU until done. Preemptive: the OS can take the CPU away.",
             "groups": [["preempt", "interrupt", "take away", "taken away", "stop"]],
             "question": {"type": "mcq", "index": 4}},
        ],
        "misconceptions": [
            {"id": "wt_equals_tat", "idea": "wt", "text": "Waiting time is the same as turnaround time",
             "pattern": r"waiting time (is|equals|=|means) (the |same as )?(the )?turnaround"},
            {"id": "tat_equals_ct", "idea": "tat", "text": "Turnaround time is just the completion time",
             "pattern": r"turnaround (time )?(is|equals|=) (just |simply )?(the )?completion"},
        ],
        "extra_mcq": [
            {"q": "What does the CPU scheduler do?",
             "options": [("Chooses which ready process gets the CPU next", True, "Right: with one core only one process runs at a time, so someone must choose."),
                         ("Runs all ready processes at the same time", False, "One core executes one process at a time; it only looks simultaneous because of fast switching."),
                         ("Decides how much memory each process gets", False, "That is memory management, not CPU scheduling."),
                         ("Creates new processes", False, "Processes are created by system calls like fork(); the scheduler only picks who runs.")]},
            {"q": "In a non-preemptive algorithm, a more urgent process arrives while another is running. What happens?",
             "options": [("It waits until the running process finishes its burst", True, "Right: non-preemptive means nobody is interrupted."),
                         ("It immediately takes the CPU", False, "That is preemption, which non-preemptive algorithms never do."),
                         ("Both share the CPU", False, "One core runs one process at a time."),
                         ("It is discarded", False, "It waits in the ready queue.")]},
        ],
    },
    "fcfs": {
        "real_life": [
            "**Bank token system.** You take token 42; tokens are served strictly in order. A person with a 1-minute job "
            "behind someone opening a new account (20 minutes) still waits the full 20 minutes: that is the convoy effect.",
            "**In a real computer.** A shared printer prints jobs in the order they were sent, and simple batch queues "
            "run jobs first-come-first-served.",
        ],
        "ideas": [
            {"id": "arrival_order", "statement": "Processes run in the order they arrive.",
             "groups": [["arriv", "come", "came", "first"], ["order", "first", "queue", "line"]],
             "question": {"type": "decision", "algorithm": "FCFS", "event": "dispatch", "difficulty": 2}},
            {"id": "non_preemptive", "statement": "Once a process starts, it runs until its burst is finished.",
             "groups": [["non preempt", "nonpreempt", "not preempt", "no preempt", "until it finish", "until finish", "runs to completion", "not interrupted", "complete",
                         "until its burst", "until it is done", "until done", "till it finish", "keeps the cpu", "cannot be interrupted", "can't be interrupted", "whole burst", "burst is finished", "finishes its burst"]],
             "question": {"type": "mcq", "index": 3}},
            {"id": "idle", "statement": "If no process has arrived, the CPU sits idle until the next arrival.",
             "groups": [["idle", "empty", "nothing", "no process"]],
             "question": {"type": "mcq", "index": 2}},
            {"id": "convoy", "statement": "Short processes stuck behind a long one wait a long time (convoy effect).",
             "groups": [["convoy", "long", "stuck", "behind", "short"]],
             "question": {"type": "mcq", "index": 1}},
        ],
        "misconceptions": [
            {"id": "shortest_first", "idea": "arrival_order", "text": "FCFS picks the shortest job", "pattern": r"(shortest|smallest) (job|burst|process)"},
        ],
        "extra_mcq": [
            {"q": "Under FCFS, P1 (burst 10) is running when P2 (burst 1) arrives. When does P2 start?",
             "options": [("When P1 finishes", True, "Right: FCFS is non-preemptive and serves in arrival order."),
                         ("Immediately, because it is shorter", False, "FCFS never looks at burst length."),
                         ("After half of P1's burst", False, "There are no time slices in FCFS."),
                         ("Never", False, "Every process eventually runs in FCFS; it cannot starve.")]},
        ],
    },
    "sjf": {
        "real_life": [
            "**Photocopy shop.** The shopkeeper finishes the current job, then takes the customer with the fewest pages "
            "among those already in the shop. A 1-page customer walking in mid-job must wait for that job to end.",
            "**In a real computer.** Batch systems that know job lengths (e.g. scheduled reports on a server) run short "
            "jobs first so most users get results quickly.",
        ],
        "ideas": [
            {"id": "shortest_arrived", "statement": "When the CPU is free, pick the shortest burst among ARRIVED processes.",
             "groups": [["short", "small", "least"], ["burst", "job", "time"], ["arriv", "already", "waiting", "ready", "present"]],
             "question": {"type": "decision", "algorithm": "SJF", "event": "dispatch", "difficulty": 2}},
            {"id": "non_preemptive", "statement": "Once started, a process runs to completion; a shorter arrival does not interrupt it.",
             "groups": [["non preempt", "nonpreempt", "not preempt", "no preempt", "not interrupt", "completion", "until it finish", "until finish", "complete",
                         "until its burst", "until it is done", "until done", "till it finish", "keeps the cpu", "cannot be interrupted", "can't be interrupted", "whole burst", "burst is finished", "finishes its burst"]],
             "question": {"type": "mcq", "index": 0}},
            {"id": "tie", "statement": "Ties are broken by arrival order (FCFS).",
             "groups": [["tie", "ties", "tied", "same burst", "equal", "same time"], ["arriv", "first come", "fcfs", "earlier"]],
             "question": {"type": "mcq", "index": 1}},
            {"id": "optimal_starvation", "statement": "Gives the lowest average waiting time, but burst times must be predicted and long jobs can starve.",
             "groups": [["average", "minimum", "optimal", "lowest", "best"], ["starv", "predict", "unknown", "estimate", "long job", "long process"]],
             "question": {"type": "mcq", "index": 2}},
        ],
        "misconceptions": [
            {"id": "preempts", "idea": "non_preemptive", "text": "SJF interrupts the running process when a shorter one arrives",
             "pattern": r"(sjf|it) (will )?(interrupt|preempt)s?"},
            {"id": "ignores_arrival", "idea": "shortest_arrived", "text": "Chooses the shortest job even if it has not arrived", "pattern": ""},
        ],
        "extra_mcq": [],
    },
    "srtf": {
        "real_life": [
            "**Hospital casualty desk.** The doctor always treats whoever needs the least time left. A patient needing a "
            "2-minute dressing walks in while the current patient needs 7 more minutes: the doctor pauses and does the "
            "dressing first. If the newcomer needs exactly as long as what is left, the doctor just continues.",
            "**In a real computer.** Short interactive tasks (a key press, a click) finish almost instantly because "
            "schedulers favour work that will be done soon.",
        ],
        "ideas": [
            {"id": "preemptive", "statement": "SRTF is preemptive: a newly arrived shorter process interrupts the running one.",
             "groups": [["preempt", "interrupt", "stop", "pause", "take over", "switch"], ["arriv", "new", "come", "comes"]],
             "question": {"type": "decision", "algorithm": "SRTF", "event": "preempt", "difficulty": 2}},
            {"id": "remaining", "statement": "Decisions use the REMAINING time, not the original burst.",
             "groups": [["remaining", "left", "rest", "still need"]],
             "question": {"type": "decision", "algorithm": "SRTF", "event": "dispatch_after_preempt", "difficulty": 2}},
            {"id": "strictly", "statement": "Preempt only if the newcomer is strictly shorter; on a tie the running process continues.",
             "groups": [["strict", "tie", "equal", "same", "less than"]],
             "question": {"type": "decision", "algorithm": "SRTF", "event": "no_preempt", "difficulty": 2}},
            {"id": "wt_pieces", "statement": "A process can run in pieces; WT = CT − AT − BT counts every wait.",
             "groups": [["waiting", "wait"], ["piece", "part", "again", "multiple", "minus", "completion", "ct"]],
             "question": {"type": "metric", "algorithm": "SRTF", "field": "WT", "multi_piece": True, "difficulty": 2}},
        ],
        "misconceptions": [
            {"id": "same_as_sjf", "idea": "preemptive", "text": "SRTF never interrupts a running process (that is SJF)",
             "pattern": r"(does not|doesn't|never|won't|will not) (preempt|interrupt)"},
            {"id": "burst_not_remaining", "idea": "remaining", "text": "Compares original burst times instead of remaining times", "pattern": ""},
        ],
        "extra_mcq": [],
    },
    "rr": {
        "real_life": [
            "**Cricket nets practice.** Each batter gets 6 balls (the time quantum), then goes to the back of the line, "
            "even if they wanted more. A batter who gets out on ball 3 leaves early and the next one starts at once.",
            "**In your laptop.** Time slices of a few milliseconds let a music player, a browser and a download all make "
            "progress, which is why the computer feels responsive.",
        ],
        "ideas": [
            {"id": "quantum", "statement": "Each process runs for at most one time quantum at a time.",
             "groups": [["quantum", "time slice", "slice", "fixed time", "turn"]],
             "question": {"type": "mcq", "index": 3}},
            {"id": "back_of_queue", "statement": "An unfinished process goes to the back of the FIFO ready queue; the front process runs next.",
             "groups": [["back", "end", "rear", "tail"], ["queue", "line"]],
             "question": {"type": "decision", "algorithm": "RR", "event": "dispatch", "difficulty": 2}},
            {"id": "arrival_convention", "statement": "A process arriving when a slice ends joins the queue before the preempted process.",
             "groups": [["arriv", "new"], ["before", "ahead", "first"]],
             "question": {"type": "mcq", "index": 1}},
            {"id": "early_finish", "statement": "A process that finishes before its quantum ends gives up the CPU immediately.",
             "groups": [["finish", "done", "complete", "less than"], ["early", "before", "leaves", "next", "immediately", "less than"]],
             "question": {"type": "mcq", "index": 0}},
            {"id": "q_size", "statement": "Huge quantum ≈ FCFS; tiny quantum = too many context switches.",
             "groups": [["large", "big", "small", "tiny"], ["fcfs", "context switch", "overhead", "switch"]],
             "question": {"type": "mcq", "index": 2}},
        ],
        "misconceptions": [
            {"id": "preempted_first", "idea": "arrival_convention", "text": "The preempted process goes ahead of a process arriving at the same moment", "pattern": ""},
            {"id": "runs_to_end", "idea": "quantum", "text": "Each process runs until it finishes", "pattern": r"runs? (until|till) (it )?(finish|complete)"},
        ],
        "extra_mcq": [
            {"q": "q = 3. P1 needs 7 units and is first in the queue. How long does P1 run in its first turn?",
             "options": [("3 units", True, "Right: at most one quantum, then it goes to the back of the queue."),
                         ("7 units", False, "That would be FCFS. Round Robin stops it after one quantum."),
                         ("1 unit", False, "The quantum is 3, not 1."),
                         ("Until another process arrives", False, "RR does not preempt on arrival; only the timer interrupts.")]},
        ],
    },
    "priority": {
        "real_life": [
            "**Hospital emergency.** An accident victim is treated before someone with a cold, even if the cold patient "
            "came first. If the emergency room is non-preemptive, a doctor already treating a patient finishes first.",
            "**In a real computer.** Linux uses nice values: a lower nice value means higher priority. Handling your mouse "
            "and keyboard gets priority over a background antivirus scan.",
        ],
        "ideas": [
            {"id": "lower_number", "statement": "The arrived process with the highest priority runs; here a LOWER number means higher priority.",
             "groups": [["lower", "smaller", "least", "less"], ["number", "value", "priority"]],
             "question": {"type": "mcq", "index": 0}},
            {"id": "np_vs_p", "statement": "Non-preemptive waits for the running process; preemptive interrupts it.",
             "groups": [["preempt", "interrupt"], ["non", "wait", "finish"]],
             "question": {"type": "decision", "algorithm": "PRIORITY_P", "event": "preempt", "difficulty": 2}},
            {"id": "strict", "statement": "Preemption only for a STRICTLY higher priority; equal priority does not preempt.",
             "groups": [["strict", "equal", "same", "tie"]],
             "question": {"type": "mcq", "index": 2}},
            {"id": "aging", "statement": "Low-priority processes can starve; aging raises their priority over time.",
             "groups": [["starv", "never run", "wait forever", "forever"], ["aging", "ageing", "increase", "raise", "boost"]],
             "question": {"type": "mcq", "index": 1}},
        ],
        "misconceptions": [
            {"id": "higher_number", "idea": "lower_number", "text": "A larger priority number means a higher priority (opposite of this course)",
             "pattern": r"(higher|bigger|larger|greater) (number|value)s? (means|is|=|gets?|has)? ?(a )?(higher|more|first|top)"},
        ],
        "extra_mcq": [],
    },
    "critical_section": {
        "real_life": [
            "**Booking the last train seat.** Two people on IRCTC click 'Book' for the last berth at the same moment. If "
            "both read \"1 seat left\" before either writes \"0 left\", both get confirmed: a race condition. The booking "
            "update must be a critical section.",
            "**Shared bank account.** You and your parent withdraw ₹500 at two ATMs at the same instant from a balance of "
            "₹1000. Without locking, both read ₹1000 and both write ₹500, so the bank loses ₹500.",
        ],
        "ideas": [
            {"id": "race", "statement": "A race condition: the result depends on the timing of processes that share data.",
             "groups": [["race", "same time", "simultaneous", "together", "timing"], ["shared", "share", "same data", "same variable", "common"]],
             "question": {"type": "mcq", "index": 0}},
            {"id": "three_steps", "statement": "count++ is load, add, store, so two threads can interleave and lose an update.",
             "groups": [["load", "read"], ["store", "write", "save"], ["lost", "lose", "overwrite", "wrong"]],
             "question": {"type": "mcq", "index": 3}},
            {"id": "mutual_exclusion", "statement": "Mutual exclusion: only one process may be in the critical section at a time.",
             "groups": [["mutual exclusion", "only one", "one at a time", "one process"]],
             "question": {"type": "mcq", "index": 1}},
            {"id": "progress_bounded", "statement": "Also needed: progress (no blocking from outside) and bounded waiting (no endless overtaking).",
             "groups": [["progress"], ["bounded", "limit", "wait forever"]],
             "question": {"type": "mcq", "index": 2}},
            {"id": "tools", "statement": "Solutions: Peterson's algorithm (2 processes), atomic instructions, locks, semaphores.",
             "groups": [["peterson", "lock", "mutex", "semaphore", "test and set", "atomic"]],
             "question": {"type": "mcq", "index": 4}},
        ],
        "misconceptions": [
            {"id": "single_step", "idea": "three_steps", "text": "count++ is a single, atomic step", "pattern": r"(count\s*\+\+|counter\s*\+\+|increment\w*)\s+(is|happens in|takes|runs as)\s+(just\s+)?(a |an |one )?(single|one|atomic)\b"},
        ],
        "extra_mcq": [
            {"q": "Why can two threads running count++ lose an update?",
             "options": [("count++ is a load, an add and a store, and the steps can interleave", True, "Right: both can load the old value before either stores."),
                         ("count++ is a single machine instruction that can fail", False, "It is several instructions; the danger is interleaving, not failure."),
                         ("The CPU adds numbers incorrectly under load", False, "Arithmetic is correct; the problem is the order of steps."),
                         ("Threads cannot share variables", False, "Threads do share memory; that is why this matters.")]},
            {"q": "Peterson's solution is designed for how many processes?",
             "options": [("Two", True, "Right: it uses flag[0], flag[1] and one turn variable."),
                         ("Any number", False, "The classic algorithm only handles two processes."),
                         ("One", False, "A single process needs no mutual exclusion."),
                         ("Three", False, "It is a two-process solution.")]},
        ],
    },
    "semaphores": {
        "real_life": [
            "**Mall parking with a display board.** The board shows free spaces (S). A car entering takes one (wait: S−1). "
            "If the board goes to −2, two cars are queued at the gate. A car leaving frees one (signal: S+1) and the first "
            "queued car drives in.",
            "**In a real computer.** A server with 10 database connections uses a counting semaphore set to 10: the 11th "
            "request waits until one connection is returned.",
        ],
        "ideas": [
            {"id": "wait_block", "statement": "wait() (P) decreases S; a process that cannot get it waits "
                                              "(blocking version: blocks when S becomes negative; Module 4 version: loops while S ≤ 0).",
             "groups": [["wait", "p operation", "p", "down", "proberen"], ["decrease", "decrement", "minus", "reduce", "subtract", "s--"],
                        ["block", "sleep", "wait", "negative", "loop", "spin", "busy"]],
             "question": {"type": "semaphore", "want": "block"}},
            {"id": "signal_wake", "statement": "signal() (V) increases S; if processes are waiting, one of them can now proceed.",
             "groups": [["signal", "v operation", "v", "up", "post", "verhogen"], ["increase", "increment", "plus", "add", "s++"],
                        ["wake", "release", "unblock", "proceed", "enter", "waiting process"]],
             "question": {"type": "semaphore", "want": "wake"}},
            {"id": "negative", "statement": "Blocking version: a negative value −k means k processes are waiting. "
                                            "Busy-waiting version (Module 4 P/V): S stays at 0 and the waiting processes spin.",
             "groups": [["negative", "minus", "below zero", "never below", "spin", "busy wait", "busy-wait", "busy waiting", "loop"],
                        ["waiting", "blocked", "queue", "spin", "loop"]],
             "question": {"type": "mcq", "index": 0}},
            {"id": "mutex", "statement": "A binary semaphore (initial 1) works as a mutex: wait before, signal after the critical section.",
             "groups": [["binary", "mutex", "lock"], ["critical section", "one at a time", "before", "after"]],
             "question": {"type": "mcq", "index": 1}},
            {"id": "order", "statement": "Order of waits matters: holding mutex while waiting on another semaphore can deadlock.",
             "groups": [["order", "sequence"], ["deadlock", "stuck"]],
             "question": {"type": "mcq", "index": 2}},
        ],
        "misconceptions": [
            {"id": "signal_always_wakes", "idea": "signal_wake",
             "text": "signal() always wakes a process (it only wakes one if someone is waiting; otherwise it just increases S)",
             "pattern": r"signal (always|will always) (wake|wakes|release|releases)"},
        ],
        "extra_mcq": [],
    },
    "bounded_buffer": {
        "real_life": [
            "**Juice stall counter.** Room for 2 glasses: `empty` is the free spots, `full` the glasses waiting, and only one "
            "hand on the counter at a time (`mutex`).",
            "**In a computer.** A web server produces pages that the browser consumes; a compiler produces assembly code that "
            "the assembler consumes. A keyboard driver fills a buffer that a program empties.",
        ],
        "ideas": [
            {"id": "three_sems", "statement": "Three semaphores: mutex = 1 protects the buffer, empty = n counts free slots, full = 0 counts filled slots.",
             "groups": [["mutex", "lock"], ["empty", "free slot"], ["full", "filled"]],
             "question": {"type": "mcq", "index": 0}},
            {"id": "signal_other", "statement": "Each side signals the other: the producer does signal(full), the consumer signal(empty).",
             "groups": [["signal", "up", "post", "v"], ["full", "empty"], ["producer", "consumer", "other"]],
             "question": {"type": "mcq", "index": 1}},
            {"id": "who_blocks", "statement": "The consumer blocks when the buffer is empty (full = 0); the producer blocks when it is full (empty = 0).",
             "groups": [["block", "wait", "sleep", "stuck"], ["empty buffer", "buffer is empty", "buffer is full", "full buffer", "nothing", "no item", "no space", "no slot"]],
             "question": {"type": "mcq", "index": 2}},
            {"id": "order", "statement": "Wait on empty/full before mutex: sleeping while holding mutex deadlocks the buffer.",
             "groups": [["order", "before", "first", "holding", "holds"], ["deadlock", "stuck", "forever"]],
             "question": {"type": "mcq", "index": 4}},
        ],
        "misconceptions": [
            {"id": "one_semaphore", "idea": "three_sems", "text": "One semaphore is enough for producer–consumer",
             "pattern": r"only one semaphore|one semaphore is enough|single semaphore (is )?enough"},
        ],
        "extra_mcq": [
            {"q": "What does mutex protect in the bounded-buffer solution?",
             "options": [("The buffer itself, so adding and removing never happen at the same time", True, "Right: it is the lock on the shared buffer."),
                         ("The number of empty slots", False, "empty counts those."),
                         ("Which process runs next", False, "The scheduler decides that, not mutex."),
                         ("The number of filled slots", False, "full counts those.")]},
            {"q": "The producer calls wait(mutex) and then wait(empty) while the buffer is full. What can happen?",
             "options": [("Deadlock: it sleeps holding mutex, so the consumer can never free a slot", True, "Right: always wait on empty first."),
                         ("Nothing; the order does not matter", False, "The order matters exactly because of this case."),
                         ("The consumer takes two items", False, "The consumer cannot even enter: mutex is held."),
                         ("The buffer overflows", False, "The producer is asleep; nothing is added.")]},
        ],
    },
    "readers_writers": {
        "real_life": [
            "**Department notice board.** Many students can read it at once, but whoever is pinning a new notice needs it to "
            "themselves.",
            "**In a computer.** A railway or flight booking database: thousands of people check seats (readers) while a few "
            "bookings change them (writers).",
        ],
        "ideas": [
            {"id": "many_readers", "statement": "Many readers can read together; a writer needs exclusive access.",
             "groups": [["reader"], ["same time", "together", "simultaneous", "many", "multiple", "at once"], ["writer"]],
             "question": {"type": "mcq", "index": 0}},
            {"id": "first_last", "statement": "The first reader does wait(wrt) to lock writers out; the last reader does signal(wrt).",
             "groups": [["first"], ["last"], ["wrt", "writer"]],
             "question": {"type": "mcq", "index": 1}},
            {"id": "mutex_count", "statement": "mutex protects the shared counter readcount.",
             "groups": [["mutex", "lock"], ["readcount", "read count", "count", "counter"]],
             "question": {"type": "mcq", "index": 2}},
            {"id": "starvation", "statement": "If readers keep arriving, a waiting writer can starve.",
             "groups": [["starv", "wait forever", "never get", "never write"], ["writer"]],
             "question": {"type": "mcq", "index": 3}},
        ],
        "misconceptions": [
            {"id": "one_reader", "idea": "many_readers", "text": "Readers also need exclusive access, one at a time",
             "pattern": r"one reader at a time|only one reader (can|may)"},
        ],
        "extra_mcq": [
            {"q": "Readers keep arriving, so readcount never drops to 0. What happens to a writer that is waiting?",
             "options": [("It can starve: it may wait indefinitely", True, "Right: this version favours readers."),
                         ("Deadlock", False, "Readers still make progress, so it is not a deadlock."),
                         ("It writes while the readers read", False, "That is exactly what wrt prevents."),
                         ("New readers are blocked automatically", False, "Not in this version; they walk in while readcount > 0.")]},
        ],
    },
    "dining": {
        "real_life": [
            "**A round table, five friends, five chopsticks.** Everyone needs both neighbouring chopsticks to eat.",
            "**In a computer.** Several processes that each need two shared resources, such as a program that must lock two "
            "files or two database rows before it can update both.",
        ],
        "ideas": [
            {"id": "setup", "statement": "Five philosophers share five chopsticks and each needs both neighbouring chopsticks to eat.",
             "groups": [["philosopher"], ["chopstick", "fork"], ["both", "two", "left and right", "neighbo"]],
             "question": {"type": "mcq", "index": 2}},
            {"id": "deadlock", "statement": "If all pick up their left chopstick at once, each waits forever for the right one: deadlock.",
             "groups": [["deadlock", "stuck", "forever"], ["left", "all at once", "same time", "everyone"]],
             "question": {"type": "mcq", "index": 0}},
            {"id": "circular", "statement": "It is a circular wait: P0 waits for P1, P1 for P2, …, P4 for P0, each holding one chopstick.",
             "groups": [["circular", "circle", "cycle", "round"], ["wait", "hold"]],
             "question": {"type": "mcq", "index": 1}},
            {"id": "fix", "statement": "Fix it by picking up chopsticks only when both are free (monitor), at most four at the table, or odd/even order.",
             "groups": [["fix", "prevent", "avoid", "solution", "solve"], ["both", "four", "odd", "even", "monitor", "order"]],
             "question": {"type": "mcq", "index": 4}},
        ],
        "misconceptions": [
            {"id": "semaphores_prevent", "idea": "deadlock", "text": "Using one semaphore per chopstick prevents deadlock",
             "pattern": r"(semaphores?|this) (prevents?|avoids?|stops?) (the )?deadlock"},
        ],
        "extra_mcq": [
            {"q": "The Theory notes' attempt 3 wraps take–eat–put in one lock(mutex) … unlock(mutex). What is wrong with it?",
             "options": [("Only one philosopher can eat at a time", True, "Right: it is correct but wastes the chopsticks."),
                         ("It deadlocks", False, "With one lock around everything, no circle can form."),
                         ("Two neighbours can eat together", False, "Only one philosopher is ever inside."),
                         ("Nothing; it is the best solution", False, "It is safe but slow.")]},
            {"q": "Which change stops the dining philosophers from deadlocking?",
             "options": [("Pick up the chopsticks only if both are free", True, "Right: no philosopher ever holds one while waiting for the other."),
                         ("Make every chopstick semaphore start at 0", False, "Then nobody could ever pick one up."),
                         ("Use busy waiting instead of blocking", False, "Everyone would spin forever instead: still deadlocked."),
                         ("Let philosophers think for longer", False, "That makes it rarer, not impossible.")]},
        ],
    },
    "deadlock": {
        "real_life": [
            "**Gridlock at a four-way junction.** Every car has entered the junction and waits for the car in front, which "
            "waits for the next, in a circle. Nobody can reverse (no preemption).",
            "**Two friends, one charger and one cable.** One holds the charger, the other the cable, and each waits for the "
            "other to hand theirs over.",
        ],
        "ideas": [
            {"id": "definition", "statement": "Deadlock: processes each wait for a resource held by another in the set, so none can continue.",
             "groups": [["wait", "waiting"], ["each other", "another", "held", "holding", "circle", "forever"]],
             "question": {"type": "mcq", "index": 3}},
            {"id": "four_conditions", "statement": "All four must hold: mutual exclusion, hold and wait, no preemption, circular wait.",
             "groups": [["mutual exclusion"], ["hold and wait", "hold"], ["no preemption", "preempt"], ["circular"]],
             "question": {"type": "mcq", "index": 0}},
            {"id": "rag", "statement": "In a resource-allocation graph with single instances, a cycle means deadlock.",
             "groups": [["graph", "cycle", "loop"]],
             "question": {"type": "mcq", "index": 1}},
            {"id": "handling", "statement": "Handle by prevention (break a condition), avoidance (Banker's) or detection and recovery.",
             "groups": [["prevent", "avoid", "detect", "recover", "banker"]],
             "question": {"type": "mcq", "index": 2}},
        ],
        "misconceptions": [
            {"id": "starvation_condition", "idea": "four_conditions", "text": "Starvation is one of the deadlock conditions", "pattern": ""},
            {"id": "any_cycle", "idea": "rag", "text": "Any cycle always means deadlock, even with several instances", "pattern": ""},
        ],
        "extra_mcq": [
            {"q": "Which situation is a deadlock?",
             "options": [("P1 holds R1 and waits for R2, while P2 holds R2 and waits for R1", True, "Right: each waits for the other's resource, forever."),
                         ("P1 waits a long time because higher-priority processes keep arriving", False, "That is starvation: P1 could run once they stop arriving."),
                         ("P1 and P2 both run slowly", False, "Slowness is not a deadlock."),
                         ("P1 is waiting for user input", False, "Waiting for input is normal blocking, not deadlock.")]},
        ],
    },
    "bankers": {
        "real_life": [
            "**Bank loans.** The bank has ₹10 lakh. Each business declares its maximum loan. The bank lends only if it can "
            "still see an order in which every business could get its full limit, finish its project and repay.",
            "**Lending cricket kits.** A team that finishes returns ALL the kits it was holding, so your pile of spare kits "
            "grows after each team finishes.",
        ],
        "ideas": [
            {"id": "need", "statement": "Need = Max − Allocation (what each process may still request).",
             "groups": [["need"], ["max", "maximum"], ["allocation", "allocated", "holding", "minus"]],
             "question": {"type": "mcq", "index": 0}},
            {"id": "need_le_work", "statement": "A process can finish when its Need ≤ Work (available) for every resource.",
             "groups": [["need"], ["available", "work", "less than", "enough", "free"]],
             "question": {"type": "bankers"}},
            {"id": "release", "statement": "When it finishes, Work increases by its Allocation.",
             "groups": [["release", "return", "give back", "free", "finish", "complet"], ["allocation", "allocated", "everything", "all", "work increase", "add"]],
             "question": {"type": "mcq", "index": 1}},
            {"id": "safe", "statement": "Safe if all processes can finish in some order (a safe sequence); several orders may be valid.",
             "groups": [["safe"], ["sequence", "order", "all process", "every process"]],
             "question": {"type": "bankers"}},
            {"id": "unsafe", "statement": "Unsafe does not mean deadlock; it means deadlock is possible.",
             "groups": [["unsafe"], ["possible", "may", "might", "not necessarily", "risk"]],
             "question": {"type": "mcq", "index": 2}},
        ],
        "misconceptions": [
            {"id": "unsafe_is_deadlock", "idea": "unsafe", "text": "An unsafe state is already a deadlock",
             "pattern": r"unsafe (state )?(means|is|=) (already )?(a )?deadlock"},
            {"id": "release_need", "idea": "release", "text": "A finished process adds its Need to Work", "pattern": r"add(s|ing)? (the )?need"},
        ],
        "extra_mcq": [],
    },
}


def merge_into(lessons: list[dict]) -> None:
    for l in lessons:
        ex = EXTRAS.get(l["id"], {})
        l["real_life"] = ex.get("real_life", [])
        l["ideas"] = ex.get("ideas", [])
        l["misconceptions"] = ex.get("misconceptions", [])
        l["mcq"] = l["mcq"] + ex.get("extra_mcq", [])
