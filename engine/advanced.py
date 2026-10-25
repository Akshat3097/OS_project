"""
General scheduler for exam-style problems the basic engine does not cover:

  * processes with several bursts, e.g. CPU 4 → I/O 3 → CPU 3 (or I/O first, then CPU)
  * multilevel queue scheduling (each queue has its own algorithm; a higher queue preempts a lower one)
  * fractional times (e.g. 60% of 8 ms = 4.8 ms), handled by scaling to integer ticks

Conventions (they reproduce the VIT BCSE303L answer keys checked in tests/test_past_papers.py):
  * Ties are broken by the time the process last came into the ready queue from outside (its arrival,
    or the end of its I/O burst; being preempted does not change it), then by list order.
  * SRTF / preemptive priority preempt only when the newcomer is STRICTLY better.
  * Round Robin: a process arriving when a time slice ends joins the queue before the preempted one.
  * Multilevel queues: a lower queue runs only when all higher queues are empty; an arrival in a
    higher queue preempts it. A preempted process keeps its place at the head of its own queue.
    With queue_preempt="slice_end" a higher-queue arrival waits until the running time slice ends
    (the "Round Robin with priority" example in the Module 3 notes works this way).
  * Multilevel feedback queues (feedback=True): every process starts in the top queue; using a whole
    time slice without finishing moves it one queue down; giving up the CPU early (finishing a CPU
    burst, e.g. for I/O) keeps it where it is. This follows the MLFQ example in the Module 3 notes.
  * Waiting time: WT = TAT − CPU − I/O (time spent ready but not running). The I/O-inclusive
    variant WT = TAT − CPU is also reported, because some answer keys count I/O as waiting.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal

IDLE = "IDLE"


@dataclass
class Job:
    pid: str
    arrival: float
    bursts: list[tuple[str, float]]          # [("CPU", 4), ("IO", 3), ("CPU", 3)]
    priority: int = 0
    queue: int = 1

    @property
    def cpu(self) -> float:
        return sum(b for k, b in self.bursts if k == "CPU")

    @property
    def io(self) -> float:
        return sum(b for k, b in self.bursts if k == "IO")


@dataclass
class QueueSpec:
    qid: int                 # 1 = highest priority
    algorithm: str           # FCFS | SJF | SRTF | RR | PRIORITY_NP | PRIORITY_P
    quantum: float | None = None


@dataclass
class JobResult:
    pid: str
    arrival: float
    cpu: float
    io: float
    completion: float
    turnaround: float
    waiting: float           # TAT − CPU − I/O
    waiting_incl_io: float   # TAT − CPU
    response: float


@dataclass
class AdvResult:
    gantt: list[tuple[str, float, float]]
    results: dict[str, JobResult]
    events: list[dict] = field(default_factory=list)

    def avg(self, attr: str) -> float:
        vals = [getattr(r, attr) for r in self.results.values()]
        return sum(vals) / len(vals)


def _decimals(x) -> int:
    d = Decimal(str(x)).normalize().as_tuple().exponent
    return max(0, -d)


def simulate(jobs: list[Job], algorithm: str | None = None, quantum: float | None = None,
             queues: list[QueueSpec] | None = None, lower_is_higher: bool = True,
             new_arrivals_first: bool = True, feedback: bool = False,
             queue_preempt: str = "immediate") -> AdvResult:
    if queues is None:
        queues = [QueueSpec(1, algorithm.upper(), quantum)]
    qspec = {q.qid: q for q in queues}
    order = sorted(qspec)                                    # 1 first = highest priority
    cur_q = {j.pid: (order[0] if feedback else j.queue) for j in jobs}   # queue each process is in now
    nums = [j.arrival for j in jobs] + [b for j in jobs for _, b in j.bursts] + \
           [q.quantum for q in queues if q.quantum]
    scale = 10 ** min(3, max(_decimals(x) for x in nums))
    T = lambda x: int(round(x * scale))                       # noqa: E731
    idx = {j.pid: i for i, j in enumerate(jobs)}
    st = {j.pid: {"k": 0, "rem": None, "state": "new", "since": None, "first": None, "io_until": None,
                  "qused": 0, "ct": None} for j in jobs}
    rr = {qid: deque() for qid in order if qspec[qid].algorithm == "RR"}
    sign = 1 if lower_is_higher else -1
    running: str | None = None
    pending_requeue: list[str] = []
    ticks: list[str] = []
    events: list[dict] = []
    total = len(jobs)
    t = 0

    def make_ready(pid: str, at: int, front: bool = False, keep_since: bool = False):
        s = st[pid]
        s["state"] = "ready"
        if not keep_since:
            s["since"] = at
        q = cur_q[pid]
        if q in rr:
            (rr[q].appendleft if front else rr[q].append)(pid)

    def start_burst(pid: str, at: int):
        """Move pid to its k-th burst starting at time `at` (CPU → ready, I/O → blocked)."""
        s, j = st[pid], jobs[idx[pid]]
        if s["k"] >= len(j.bursts):
            s["state"], s["ct"] = "done", at
            return
        kind, length = j.bursts[s["k"]]
        s["rem"] = T(length)
        if kind == "CPU":
            make_ready(pid, at)
        else:
            s["state"], s["io_until"] = "io", at + T(length)

    while sum(1 for s in st.values() if s["state"] == "done") < total:
        # 1. events at time t: I/O completions and arrivals (list order), then the preempted RR process
        if not new_arrivals_first:
            for pid in pending_requeue:
                make_ready(pid, t)
            pending_requeue = []
        for j in jobs:
            s = st[j.pid]
            if s["state"] == "io" and s["io_until"] == t:
                s["k"] += 1
                start_burst(j.pid, t)
            if s["state"] == "new" and T(j.arrival) == t:
                start_burst(j.pid, t)
        for pid in pending_requeue:
            make_ready(pid, t)
        pending_requeue = []
        if sum(1 for s in st.values() if s["state"] == "done") == total:
            break

        ready = [j.pid for j in jobs if st[j.pid]["state"] == "ready"]
        cand = ready + ([running] if running else [])
        if not cand:
            ticks.append(IDLE)
            t += 1
            if t > 10**6:
                raise RuntimeError("simulation did not finish")
            continue
        top = min(cur_q[p] for p in cand)
        if running and cur_q[running] != top:
            if queue_preempt == "immediate":
                # a higher queue has work: the running process goes back to the head of its own queue
                rq = cur_q[running]
                events.append({"t": t / scale, "event": "queue_preempt", "preempted": running})
                s = st[running]
                s["state"], s["qused"] = "ready", 0
                if rq in rr:
                    rr[rq].appendleft(running)
                running = None
            else:
                top = cur_q[running]          # slice_end: finish the current time slice first
        spec = qspec[top]

        def key(pid):
            j, s = jobs[idx[pid]], st[pid]
            base = {"FCFS": (), "RR": (), "SJF": (s["rem"],), "SRTF": (s["rem"],),
                    "PRIORITY_NP": (sign * j.priority,), "PRIORITY_P": (sign * j.priority,)}[spec.algorithm]
            return (*base, s["since"], idx[pid])

        # 2. keep, preempt or choose
        if running:
            if spec.algorithm in ("SRTF", "PRIORITY_P"):
                others = [p for p in ready if cur_q[p] == top]
                if others:
                    best = min(others, key=key)
                    if key(best)[0] < key(running)[0]:
                        events.append({"t": t / scale, "event": "preempt", "preempted": running, "chosen": best})
                        make_ready(running, t, keep_since=True)   # ties use the time it came in from outside
                        running = best
        if not running:
            pool = [p for p in ready if cur_q[p] == top]
            if spec.algorithm == "RR":
                running = rr[top].popleft()
            else:
                running = min(pool, key=key)
            st[running]["qused"] = 0
            events.append({"t": t / scale, "event": "dispatch", "chosen": running, "queue": top})
        s = st[running]
        s["state"] = "running"
        if s["first"] is None:
            s["first"] = t
        # 3. run one tick
        ticks.append(running)
        s["rem"] -= 1
        s["qused"] += 1
        t += 1
        if s["rem"] == 0:
            s["k"] += 1
            pid, running = running, None
            start_burst(pid, t)
        elif spec.algorithm == "RR" and s["qused"] >= T(spec.quantum):
            if feedback and order.index(cur_q[running]) + 1 < len(order):
                cur_q[running] = order[order.index(cur_q[running]) + 1]
                events.append({"t": t / scale, "event": "demote", "process": running, "to_queue": cur_q[running]})
            s["state"] = "queued"
            pending_requeue.append(running)
            running = None

    # gantt + metrics
    gantt: list[list] = []
    for i, pid in enumerate(ticks):
        if gantt and gantt[-1][0] == pid:
            gantt[-1][2] = i + 1
        else:
            gantt.append([pid, i, i + 1])
    while gantt and gantt[-1][0] == IDLE:
        gantt.pop()
    g = [(p, a / scale, b / scale) for p, a, b in gantt]
    results = {}
    for j in jobs:
        s = st[j.pid]
        ct = s["ct"] / scale
        tat = ct - j.arrival
        first = s["first"] / scale if s["first"] is not None else ct
        r = lambda x: round(x, 4)  # noqa: E731
        results[j.pid] = JobResult(j.pid, j.arrival, j.cpu, j.io, r(ct), r(tat), r(tat - j.cpu - j.io),
                                   r(tat - j.cpu), r(first - j.arrival))
    return AdvResult(g, results, events)


def performance(gantt, n_processes: int) -> dict:
    """Whole-schedule metrics as the Module 3 notes compute them:
    CPU utilisation = CPU busy time / total time × 100, throughput = processes / total time, where the
    total time runs from t = 0 to the last completion; context switches = changes from one process to a
    different one in the Gantt chart (idle gaps and the first dispatch are not counted)."""
    segs = [(s.pid, s.start, s.end) if hasattr(s, "pid") else tuple(s) for s in gantt]
    if not segs:
        return {"cpu_busy": 0, "total_time": 0, "cpu_utilization": 0.0, "throughput": 0.0, "context_switches": 0}
    busy = sum(b - a for p, a, b in segs if p != IDLE)
    total = max(b for _, _, b in segs)
    runs = [p for p, _, _ in segs if p != IDLE]
    switches = sum(1 for a, b in zip(runs, runs[1:]) if a != b)
    r = lambda x: round(x, 4)  # noqa: E731
    return {"cpu_busy": r(busy), "total_time": r(total), "cpu_utilization": round(100 * busy / total, 2) if total else 0.0,
            "throughput": r(n_processes / total) if total else 0.0, "context_switches": switches}


def from_simple(processes, algorithm: str, quantum=None, **kw) -> AdvResult:
    """Run single-burst problems (engine.scheduling.Process) through the general simulator."""
    jobs = [Job(p.pid, p.arrival, [("CPU", p.burst)], p.priority) for p in processes]
    return simulate(jobs, algorithm, quantum, **kw)


# ----------------------------------------------------------------------------- problem wrapper (past papers)
ALGO_NAMES = {"FCFS": "FCFS", "SJF": "SJF (non-preemptive)", "SRTF": "SRTF (preemptive SJF)", "RR": "Round Robin",
              "PRIORITY_NP": "Priority (non-preemptive)", "PRIORITY_P": "Priority (preemptive)"}


@dataclass
class AdvancedProblem:
    jobs: list[Job]
    algorithm: str | None = None          # single-level algorithm, or None when queues are given
    quantum: float | None = None
    queues: list[QueueSpec] | None = None
    lower_is_higher: bool = True
    difficulty: int = 3
    title: str = ""
    kind: str = "advanced"
    feedback: bool = False
    queue_preempt: str = "immediate"

    def solve(self) -> AdvResult:
        return simulate(self.jobs, self.algorithm, self.quantum, self.queues, self.lower_is_higher,
                        feedback=self.feedback, queue_preempt=self.queue_preempt)

    def performance(self) -> dict:
        return performance(self.solve().gantt, len(self.jobs))

    @property
    def label(self) -> str:
        if self.queues:
            return ("Multilevel feedback queue: " if self.feedback else "Multilevel queue: ") + ", ".join(
                f"Q{q.qid} {ALGO_NAMES[q.algorithm]}" + (f" (q={q.quantum:g})" if q.quantum else "") for q in self.queues)
        return ALGO_NAMES[self.algorithm] + (f", q = {self.quantum:g}" if self.quantum else "")

    def has_io(self) -> bool:
        return any(k == "IO" for j in self.jobs for k, _ in j.bursts)

    def statement(self) -> str:
        extra = ""
        if self.has_io():
            extra = " Each process alternates CPU and I/O bursts as listed; I/O runs in parallel with the CPU."
        if self.queues and self.feedback:
            extra += (" Every process starts in Q1; a process that uses its whole time slice without finishing "
                      "moves down one queue. A higher queue always runs first.")
        elif self.queues and self.queue_preempt == "slice_end":
            extra += " A higher queue runs first, but a running process finishes its current time slice."
        elif self.queues:
            extra += " A higher queue (lower number) always runs first and preempts lower queues."
        pr = "" if self.queues or "PRIORITY" not in (self.algorithm or "") else \
            (" Lower number = higher priority." if self.lower_is_higher else " Higher number = higher priority.")
        return f"{self.title} Schedule with {self.label}.{pr}{extra} Find CT, TAT and WT for each process."

    def to_dict(self) -> dict:
        return {"kind": "advanced", "algorithm": self.algorithm, "quantum": self.quantum,
                "lower_is_higher": self.lower_is_higher, "difficulty": self.difficulty, "title": self.title,
                "feedback": self.feedback, "queue_preempt": self.queue_preempt,
                "queues": [q.__dict__ for q in self.queues] if self.queues else None,
                "jobs": [{"pid": j.pid, "arrival": j.arrival, "bursts": [list(b) for b in j.bursts],
                          "priority": j.priority, "queue": j.queue} for j in self.jobs]}

    @staticmethod
    def from_dict(d: dict) -> "AdvancedProblem":
        jobs = [Job(j["pid"], j["arrival"], [tuple(b) for b in j["bursts"]], j.get("priority", 0), j.get("queue", 1))
                for j in d["jobs"]]
        queues = [QueueSpec(**q) for q in d["queues"]] if d.get("queues") else None
        return AdvancedProblem(jobs, d.get("algorithm"), d.get("quantum"), queues, d.get("lower_is_higher", True),
                               d.get("difficulty", 3), d.get("title", ""), feedback=d.get("feedback", False),
                               queue_preempt=d.get("queue_preempt", "immediate"))
