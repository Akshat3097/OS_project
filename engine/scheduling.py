"""
CPU scheduling algorithms (deterministic part of the OS Engine).

Every algorithm returns a ScheduleResult with:
  * the Gantt chart (list of Segments, adjacent segments of the same process merged)
  * per-process metrics (CT, TAT, WT, RT)
  * a decision log: what the ready queue looked like each time the CPU made a choice,
    and why it chose what it chose. The tutor uses this log as "facts" for hints, so
    the LLM never has to work out the schedule itself.

Conventions (stated explicitly because textbooks differ and students get confused):
  * Time is in integer units. Burst times must be >= 1.
  * Ties are broken by earlier arrival time, then by the order processes were listed.
  * SRTF / preemptive priority: a running process is preempted only if the new
    process is STRICTLY better (shorter remaining time / higher priority).
  * Priority: a LOWER number means a HIGHER priority (Silberschatz convention).
    `lower_is_higher=False` flips this (used to detect the "reversed priority" mistake).
  * Round Robin: a process that arrives at the same instant a time slice ends joins
    the ready queue BEFORE the preempted process (`new_arrivals_first=True`).
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field

ALGORITHMS: dict[str, str] = {
    "FCFS": "First Come First Serve",
    "SJF": "Shortest Job First (non-preemptive)",
    "SRTF": "Shortest Remaining Time First (preemptive SJF)",
    "RR": "Round Robin",
    "PRIORITY_NP": "Priority (non-preemptive)",
    "PRIORITY_P": "Priority (preemptive)",
}
PREEMPTIVE = {"SRTF", "RR", "PRIORITY_P"}
USES_PRIORITY = {"PRIORITY_NP", "PRIORITY_P"}
IDLE = "IDLE"


@dataclass
class Process:
    pid: str
    arrival: int
    burst: int
    priority: int = 0


@dataclass
class Segment:
    pid: str
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass
class Decision:
    time: int
    ready: list[dict]          # [{"pid", "arrival", "burst", "remaining", "priority"}]
    chosen: str
    reason: str
    preempted: str | None = None
    kind: str = "dispatch"     # dispatch | preempt | no_preempt | idle


@dataclass
class ProcessResult:
    pid: str
    arrival: int
    burst: int
    priority: int
    completion: int
    turnaround: int
    waiting: int
    response: int


@dataclass
class ScheduleResult:
    algorithm: str
    quantum: int | None
    processes: list[Process]
    gantt: list[Segment]
    results: dict[str, ProcessResult]
    decisions: list[Decision] = field(default_factory=list)

    @property
    def avg_tat(self) -> float:
        return sum(r.turnaround for r in self.results.values()) / len(self.results)

    @property
    def avg_wt(self) -> float:
        return sum(r.waiting for r in self.results.values()) / len(self.results)

    @property
    def avg_rt(self) -> float:
        return sum(r.response for r in self.results.values()) / len(self.results)

    @property
    def makespan(self) -> int:
        return self.gantt[-1].end if self.gantt else 0

    @property
    def cpu_utilisation(self) -> float:
        busy = sum(s.length for s in self.gantt if s.pid != IDLE)
        return busy / self.makespan if self.makespan else 0.0

    def timeline(self) -> list[str]:
        """One entry per time unit: which process (or IDLE) had the CPU."""
        return expand_timeline(self.gantt)

    def to_dict(self) -> dict:
        return {
            "algorithm": self.algorithm,
            "quantum": self.quantum,
            "gantt": [asdict(s) for s in self.gantt],
            "results": {k: asdict(v) for k, v in self.results.items()},
            "avg_tat": round(self.avg_tat, 2),
            "avg_wt": round(self.avg_wt, 2),
            "avg_rt": round(self.avg_rt, 2),
            "decisions": [asdict(d) for d in self.decisions],
        }


# ----------------------------------------------------------------------------- helpers

def _validate(processes: list[Process]) -> None:
    if not processes:
        raise ValueError("At least one process is required.")
    seen = set()
    for p in processes:
        if p.pid in seen:
            raise ValueError(f"Duplicate process id {p.pid}.")
        seen.add(p.pid)
        if p.arrival < 0:
            raise ValueError(f"{p.pid}: arrival time cannot be negative.")
        if p.burst < 1:
            raise ValueError(f"{p.pid}: burst time must be at least 1.")


def _add_segment(gantt: list[Segment], pid: str, start: int, end: int) -> None:
    if end <= start:
        return
    if gantt and gantt[-1].pid == pid and gantt[-1].end == start:
        gantt[-1].end = end
    else:
        gantt.append(Segment(pid, start, end))


def merge_segments(segments: list[Segment]) -> list[Segment]:
    merged: list[Segment] = []
    for s in segments:
        _add_segment(merged, s.pid, s.start, s.end)
    return merged


def expand_timeline(gantt: list[Segment]) -> list[str]:
    tl: list[str] = []
    for s in gantt:
        tl.extend([s.pid] * s.length)
    return tl


def _ready_view(procs: list[Process], ids: list[str], remaining: dict[str, int]) -> list[dict]:
    by_id = {p.pid: p for p in procs}
    return [
        {
            "pid": i,
            "arrival": by_id[i].arrival,
            "burst": by_id[i].burst,
            "remaining": remaining[i],
            "priority": by_id[i].priority,
        }
        for i in ids
    ]


def _finish(algorithm: str, quantum: int | None, procs: list[Process], gantt: list[Segment],
            first_start: dict[str, int], completion: dict[str, int],
            decisions: list[Decision]) -> ScheduleResult:
    results: dict[str, ProcessResult] = {}
    for p in procs:
        ct = completion[p.pid]
        tat = ct - p.arrival
        results[p.pid] = ProcessResult(
            pid=p.pid, arrival=p.arrival, burst=p.burst, priority=p.priority,
            completion=ct, turnaround=tat, waiting=tat - p.burst,
            response=first_start[p.pid] - p.arrival,
        )
    return ScheduleResult(algorithm, quantum, list(procs), gantt, results, decisions)


# ----------------------------------------------------------------------------- non-preemptive

def _non_preemptive(procs: list[Process], key, algorithm: str, rule_text: str) -> ScheduleResult:
    order = {p.pid: i for i, p in enumerate(procs)}
    remaining = {p.pid: p.burst for p in procs}
    done: set[str] = set()
    gantt: list[Segment] = []
    decisions: list[Decision] = []
    first_start: dict[str, int] = {}
    completion: dict[str, int] = {}
    t = 0
    while len(done) < len(procs):
        ready = [p for p in procs if p.pid not in done and p.arrival <= t]
        if not ready:
            nxt = min(p.arrival for p in procs if p.pid not in done)
            decisions.append(Decision(t, [], IDLE, f"No process has arrived yet; CPU idle until t={nxt}.", kind="idle"))
            _add_segment(gantt, IDLE, t, nxt)
            t = nxt
            continue
        chosen = min(ready, key=lambda p: (*key(p), p.arrival, order[p.pid]))
        reason = rule_text.format(pid=chosen.pid)
        if len(ready) > 1:
            ties = [p for p in ready if key(p) == key(chosen)]
            if len(ties) > 1:
                reason += " (tie broken by earlier arrival, then list order)"
        decisions.append(Decision(t, _ready_view(procs, [p.pid for p in ready], remaining), chosen.pid, reason))
        first_start[chosen.pid] = t
        _add_segment(gantt, chosen.pid, t, t + chosen.burst)
        t += chosen.burst
        remaining[chosen.pid] = 0
        completion[chosen.pid] = t
        done.add(chosen.pid)
    return _finish(algorithm, None, procs, gantt, first_start, completion, decisions)


def fcfs(procs: list[Process]) -> ScheduleResult:
    _validate(procs)
    return _non_preemptive(procs, key=lambda p: (p.arrival,), algorithm="FCFS",
                           rule_text="{pid} arrived earliest among the waiting processes.")


def sjf(procs: list[Process]) -> ScheduleResult:
    _validate(procs)
    return _non_preemptive(procs, key=lambda p: (p.burst,), algorithm="SJF",
                           rule_text="{pid} has the shortest burst time among the arrived processes.")


def priority_np(procs: list[Process], lower_is_higher: bool = True) -> ScheduleResult:
    _validate(procs)
    sign = 1 if lower_is_higher else -1
    return _non_preemptive(procs, key=lambda p: (sign * p.priority,), algorithm="PRIORITY_NP",
                           rule_text="{pid} has the highest priority among the arrived processes.")


# ----------------------------------------------------------------------------- preemptive (unit-step)

def _preemptive(procs: list[Process], key, algorithm: str, what: str, best_what: str) -> ScheduleResult:
    """Unit-time simulation. key(p, remaining) -> tuple; smaller is better."""
    order = {p.pid: i for i, p in enumerate(procs)}
    remaining = {p.pid: p.burst for p in procs}
    done: set[str] = set()
    gantt: list[Segment] = []
    decisions: list[Decision] = []
    first_start: dict[str, int] = {}
    completion: dict[str, int] = {}
    current: str | None = None
    t = 0
    by_id = {p.pid: p for p in procs}

    def full_key(p: Process):
        return (*key(p, remaining[p.pid]), p.arrival, order[p.pid])

    while len(done) < len(procs):
        ready = [p for p in procs if p.pid not in done and p.arrival <= t]
        if not ready:
            nxt = min(p.arrival for p in procs if p.pid not in done)
            decisions.append(Decision(t, [], IDLE, f"No process has arrived yet; CPU idle until t={nxt}.", kind="idle"))
            _add_segment(gantt, IDLE, t, nxt)
            t = nxt
            current = None
            continue
        best = min(ready, key=full_key)
        ready_ids = [p.pid for p in sorted(ready, key=full_key)]
        new_arrivals = [p.pid for p in ready if p.arrival == t and p.pid != current]

        if current is not None:
            cur = by_id[current]
            if key(best, remaining[best.pid]) < key(cur, remaining[current]):
                decisions.append(Decision(
                    t, _ready_view(procs, ready_ids, remaining), best.pid,
                    f"{best.pid} has {what} ({_describe(best, remaining, key)}) than running "
                    f"{current} ({_describe(cur, remaining, key)}), so {current} is preempted.",
                    preempted=current, kind="preempt"))
                chosen = best
            else:
                chosen = cur
                if new_arrivals:
                    decisions.append(Decision(
                        t, _ready_view(procs, ready_ids, remaining), current,
                        f"{', '.join(new_arrivals)} arrived, but no ready process has {what} than running "
                        f"{current} ({_describe(cur, remaining, key)}), so {current} continues.",
                        kind="no_preempt"))
        else:
            chosen = best
            decisions.append(Decision(
                t, _ready_view(procs, ready_ids, remaining), best.pid,
                f"CPU is free; {best.pid} has {best_what} among the ready processes "
                f"({_describe(best, remaining, key)}).", kind="dispatch"))

        first_start.setdefault(chosen.pid, t)
        _add_segment(gantt, chosen.pid, t, t + 1)
        remaining[chosen.pid] -= 1
        t += 1
        if remaining[chosen.pid] == 0:
            done.add(chosen.pid)
            completion[chosen.pid] = t
            current = None
        else:
            current = chosen.pid
    return _finish(algorithm, None, procs, gantt, first_start, completion, decisions)


def _describe(p: Process, remaining: dict[str, int], key) -> str:
    k = key(p, remaining[p.pid])[0]
    if key.__name__ == "srtf_key":
        return f"remaining {k}"
    return f"priority {p.priority}"


def srtf(procs: list[Process]) -> ScheduleResult:
    _validate(procs)

    def srtf_key(p: Process, rem: int):
        return (rem,)
    return _preemptive(procs, srtf_key, "SRTF", "a shorter remaining time", "the shortest remaining time")


def priority_p(procs: list[Process], lower_is_higher: bool = True) -> ScheduleResult:
    _validate(procs)
    sign = 1 if lower_is_higher else -1

    def prio_key(p: Process, rem: int):
        return (sign * p.priority,)
    return _preemptive(procs, prio_key, "PRIORITY_P", "a higher priority", "the highest priority")


# ----------------------------------------------------------------------------- round robin

def round_robin(procs: list[Process], quantum: int, new_arrivals_first: bool = True) -> ScheduleResult:
    _validate(procs)
    if quantum < 1:
        raise ValueError("Time quantum must be at least 1.")
    order = {p.pid: i for i, p in enumerate(procs)}
    arrival_order = sorted(procs, key=lambda p: (p.arrival, order[p.pid]))
    remaining = {p.pid: p.burst for p in procs}
    admitted: set[str] = set()
    queue: deque[str] = deque()
    gantt: list[Segment] = []
    decisions: list[Decision] = []
    first_start: dict[str, int] = {}
    completion: dict[str, int] = {}
    t = 0

    def admit(upto: int) -> None:
        for p in arrival_order:
            if p.pid not in admitted and p.arrival <= upto:
                queue.append(p.pid)
                admitted.add(p.pid)

    admit(0)
    while len(completion) < len(procs):
        if not queue:
            nxt = min(p.arrival for p in procs if p.pid not in admitted)
            decisions.append(Decision(t, [], IDLE, f"Ready queue empty; CPU idle until t={nxt}.", kind="idle"))
            _add_segment(gantt, IDLE, t, nxt)
            t = nxt
            admit(t)
            continue
        snapshot = list(queue)
        pid = queue.popleft()
        run = min(quantum, remaining[pid])
        reason = f"{pid} is at the front of the ready queue; it runs for {run} unit(s)"
        reason += " (finishes)." if run == remaining[pid] else f" (one time quantum of {quantum})."
        decisions.append(Decision(t, _ready_view(procs, snapshot, remaining), pid, reason))
        first_start.setdefault(pid, t)
        _add_segment(gantt, pid, t, t + run)
        t += run
        remaining[pid] -= run
        if remaining[pid] == 0:
            completion[pid] = t
            admit(t)
        else:
            if new_arrivals_first:
                admit(t)
                queue.append(pid)
            else:
                queue.append(pid)
                admit(t)
    return _finish("RR", quantum, procs, gantt, first_start, completion, decisions)


# ----------------------------------------------------------------------------- dispatcher

def run(algorithm: str, procs: list[Process], quantum: int | None = None, **options) -> ScheduleResult:
    algorithm = algorithm.upper()
    if algorithm == "FCFS":
        return fcfs(procs)
    if algorithm == "SJF":
        return sjf(procs)
    if algorithm == "SRTF":
        return srtf(procs)
    if algorithm == "RR":
        if quantum is None:
            raise ValueError("Round Robin needs a time quantum.")
        return round_robin(procs, quantum, options.get("new_arrivals_first", True))
    if algorithm == "PRIORITY_NP":
        return priority_np(procs, options.get("lower_is_higher", True))
    if algorithm == "PRIORITY_P":
        return priority_p(procs, options.get("lower_is_higher", True))
    raise ValueError(f"Unknown algorithm {algorithm}.")


def ready_state_at(result: ScheduleResult, t: int) -> list[dict]:
    """Processes that have arrived and are not finished at time t, with remaining burst at t."""
    tl = result.timeline()
    executed: dict[str, int] = {p.pid: 0 for p in result.processes}
    for pid in tl[:t]:
        if pid != IDLE:
            executed[pid] += 1
    out = []
    for p in result.processes:
        rem = p.burst - executed[p.pid]
        if p.arrival <= t and rem > 0:
            out.append({"pid": p.pid, "arrival": p.arrival, "burst": p.burst,
                        "remaining": rem, "priority": p.priority})
    return out


def governing_decision(result: ScheduleResult, t: int) -> Decision | None:
    """Latest decision made at or before time t."""
    best = None
    for d in result.decisions:
        if d.time <= t:
            best = d
    return best
