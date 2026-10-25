"""
Problem generator. Because the OS Engine can solve any problem exactly, the tutor
can create unlimited practice questions at a chosen difficulty and still know the
correct answer. Difficulty is controlled by what the problem forces the student
to handle, not only by size:

  1 (easy)   few processes, no idle CPU, no ties
  2 (medium) staggered arrivals; SJF order differs from FCFS; preemptive
             algorithms must actually preempt at least once
  3 (hard)   more processes plus a "trap": an idle gap, a tie that needs the
             tie-breaking rule, or (Round Robin) an arrival at the exact moment
             a time slice ends
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

from . import bankers, scheduling, semaphore
from .scheduling import Process

DIFFICULTY_NAMES = {1: "Easy", 2: "Medium", 3: "Hard"}


@dataclass
class SchedulingProblem:
    algorithm: str
    difficulty: int
    processes: list[Process]
    quantum: int | None = None
    seed: int | None = None
    kind: str = "scheduling"

    def solve(self) -> scheduling.ScheduleResult:
        return scheduling.run(self.algorithm, self.processes, self.quantum)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d: dict) -> "SchedulingProblem":
        return SchedulingProblem(
            algorithm=d["algorithm"], difficulty=d["difficulty"],
            processes=[Process(**p) for p in d["processes"]],
            quantum=d.get("quantum"), seed=d.get("seed"))

    def statement(self) -> str:
        name = scheduling.ALGORITHMS[self.algorithm]
        rows = "; ".join(
            f"{p.pid} (AT={p.arrival}, BT={p.burst}"
            + (f", priority={p.priority}" if self.algorithm in scheduling.USES_PRIORITY else "") + ")"
            for p in self.processes)
        q = f" with time quantum {self.quantum}" if self.algorithm == "RR" else ""
        extra = " Lower number = higher priority." if self.algorithm in scheduling.USES_PRIORITY else ""
        return (f"Schedule the processes using {name}{q}: {rows}.{extra} Draw the Gantt chart and find "
                f"completion, turnaround and waiting time for each process.")


@dataclass
class BankersProblem:
    difficulty: int
    available: list[int]
    maximum: list[list[int]]
    allocation: list[list[int]]
    resources: list[str] = field(default_factory=lambda: ["A", "B", "C"])
    seed: int | None = None
    kind: str = "bankers"
    algorithm: str = "BANKERS"

    def solve(self) -> dict:
        return bankers.safety(self.available, self.maximum, self.allocation)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "BankersProblem":
        d = {k: v for k, v in d.items() if k not in ("kind", "algorithm")}
        return BankersProblem(**d)

    def statement(self) -> str:
        return ("Using the Banker's algorithm, compute the Need matrix and decide whether the system is in a "
                "safe state. If it is safe, give a safe sequence.")


@dataclass
class SemaphoreProblem:
    difficulty: int
    initial: dict[str, int]
    ops: list[dict]
    seed: int | None = None
    kind: str = "semaphore"
    algorithm: str = "SEMAPHORE"

    def solve(self) -> dict:
        return semaphore.trace(self.initial, self.ops)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "SemaphoreProblem":
        d = {k: v for k, v in d.items() if k not in ("kind", "algorithm")}
        return SemaphoreProblem(**d)

    def statement(self) -> str:
        init = ", ".join(f"{k} = {v}" for k, v in self.initial.items())
        seq = ", ".join(semaphore.format_op(o) for o in self.ops)
        return (f"Counting semaphore(s) start at {init}. The operations run in this order: {seq}. "
                f"What is the final value of each semaphore, and which processes are blocked at the end?")


# ----------------------------------------------------------------------------- scheduling

def _has_idle_gap(res: scheduling.ScheduleResult) -> bool:
    return any(s.pid == scheduling.IDLE for s in res.gantt)


def _has_tie(res: scheduling.ScheduleResult, algorithm: str) -> bool:
    for d in res.decisions:
        if len(d.ready) < 2:
            continue
        chosen = next((r for r in d.ready if r["pid"] == d.chosen), None)
        if chosen is None:
            continue
        others = [r for r in d.ready if r["pid"] != d.chosen]
        if algorithm == "SJF" and any(r["burst"] == chosen["burst"] for r in others):
            return True
        if algorithm == "SRTF" and any(r["remaining"] == chosen["remaining"] for r in others):
            return True
        if algorithm in scheduling.USES_PRIORITY and any(r["priority"] == chosen["priority"] for r in others):
            return True
        if algorithm == "FCFS" and any(r["arrival"] == chosen["arrival"] for r in others):
            return True
    return False


def _rr_boundary_arrival(res: scheduling.ScheduleResult) -> bool:
    arrivals = {p.arrival for p in res.processes}
    for s in res.gantt:
        if s.pid == scheduling.IDLE:
            continue
        if res.results[s.pid].completion > s.end and s.end in arrivals:
            return True
    return False


def _differs_from_fcfs(res: scheduling.ScheduleResult) -> bool:
    return res.timeline() != scheduling.fcfs(res.processes).timeline()


def _interesting(res: scheduling.ScheduleResult, algorithm: str, difficulty: int) -> bool:
    preempts = any(d.kind == "preempt" for d in res.decisions)
    if difficulty == 1:
        if _has_idle_gap(res) or _has_tie(res, algorithm):
            return False
        if algorithm in ("SJF", "PRIORITY_NP"):
            return _differs_from_fcfs(res)
        if algorithm == "RR":
            return len(res.gantt) > len(res.processes)
        return True
    if algorithm in ("SRTF", "PRIORITY_P") and not preempts:
        return False
    if algorithm in ("SJF", "PRIORITY_NP") and not _differs_from_fcfs(res):
        return False
    if difficulty == 2:
        return not _has_idle_gap(res)
    # difficulty 3: needs a trap
    if algorithm == "RR":
        return _rr_boundary_arrival(res) or _has_idle_gap(res)
    return _has_idle_gap(res) or _has_tie(res, algorithm)


def generate_scheduling(algorithm: str, difficulty: int = 1, seed: int | None = None) -> SchedulingProblem:
    algorithm = algorithm.upper()
    difficulty = max(1, min(3, difficulty))
    seed = seed if seed is not None else random.randrange(10**9)
    rng = random.Random(seed)
    for _ in range(500):
        if difficulty == 1:
            n = rng.choice([3, 4])
            if rng.random() < 0.4 and algorithm not in ("FCFS",):
                arrivals = [0] * n
            else:
                arrivals = sorted([0] + [rng.randint(0, 4) for _ in range(n - 1)])
            bursts = [rng.randint(1, 8) for _ in range(n)]
            prios = rng.sample(range(1, 6), n)
            quantum = rng.choice([2, 3])
        elif difficulty == 2:
            n = rng.choice([4, 5])
            arrivals = sorted([0] + [rng.randint(0, 7) for _ in range(n - 1)])
            bursts = [rng.randint(2, 9) for _ in range(n)]
            prios = [rng.randint(1, 5) for _ in range(n)]
            quantum = rng.choice([2, 3, 4])
        else:
            n = rng.choice([5, 6])
            arrivals = sorted([0] + [rng.randint(0, 14) for _ in range(n - 1)])
            bursts = [rng.randint(1, 9) for _ in range(n)]
            prios = [rng.randint(1, 4) for _ in range(n)]
            quantum = rng.choice([2, 3])
        procs = [Process(f"P{i + 1}", arrivals[i], bursts[i], prios[i]) for i in range(n)]
        q = quantum if algorithm == "RR" else None
        res = scheduling.run(algorithm, procs, q)
        if _interesting(res, algorithm, difficulty):
            if algorithm not in scheduling.USES_PRIORITY:
                for p in procs:
                    p.priority = 0
            return SchedulingProblem(algorithm, difficulty, procs, q, seed)
    if algorithm not in scheduling.USES_PRIORITY:
        for p in procs:
            p.priority = 0
    return SchedulingProblem(algorithm, difficulty, procs, q, seed)


# ----------------------------------------------------------------------------- banker's

def generate_bankers(difficulty: int = 1, seed: int | None = None) -> BankersProblem:
    seed = seed if seed is not None else random.randrange(10**9)
    rng = random.Random(seed)
    n, m = {1: (4, 3), 2: (5, 3), 3: (5, 4)}[max(1, min(3, difficulty))]
    resources = ["A", "B", "C", "D"][:m]
    want_unsafe = difficulty == 3 and rng.random() < 0.4
    for _ in range(2000):
        maximum = [[rng.randint(0, 9) for _ in range(m)] for _ in range(n)]
        allocation = [[rng.randint(0, mx) if mx else 0 for mx in row] for row in maximum]
        available = [rng.randint(0, 4) for _ in range(m)]
        res = bankers.safety(available, maximum, allocation)
        if res["safe"] == want_unsafe:
            continue
        need = res["need"]
        immediately_ok = [i for i in range(n) if all(nd <= a for nd, a in zip(need[i], available))]
        if not immediately_ok:
            if want_unsafe:
                return BankersProblem(difficulty, available, maximum, allocation, resources, seed)
            continue
        if difficulty >= 2 and 0 in immediately_ok:
            continue  # make the student actually search instead of starting at P0
        if res["sequence"] == [f"P{i}" for i in range(n)]:
            continue
        if want_unsafe and len(res["partial_sequence"]) < 2:
            continue
        return BankersProblem(difficulty, available, maximum, allocation, resources, seed)
    return BankersProblem(difficulty, available, maximum, allocation, resources, seed)


# ----------------------------------------------------------------------------- semaphores

def generate_semaphore(difficulty: int = 1, seed: int | None = None) -> SemaphoreProblem:
    seed = seed if seed is not None else random.randrange(10**9)
    rng = random.Random(seed)
    sems = ["S"] if difficulty < 3 else ["S", "T"]
    for _ in range(500):
        initial = {s: rng.randint(0, 2) if difficulty > 1 else rng.randint(1, 3) for s in sems}
        n_ops = {1: 5, 2: 7, 3: 9}[max(1, min(3, difficulty))]
        pids = ["P1", "P2", "P3", "P4"]
        ops: list[dict] = []
        for _ in range(n_ops):
            state = semaphore.trace(initial, ops)
            free = [p for p in pids if p not in state["blocked"]]
            if not free:
                break
            pid = rng.choice(free)
            op = "wait" if rng.random() < 0.55 else "signal"
            ops.append({"pid": pid, "op": op, "sem": rng.choice(sems)})
        result = semaphore.trace(initial, ops)
        blocked_any = any("blocks" in s["effect"] for s in result["steps"])
        woken_any = any(s["woken"] for s in result["steps"])
        if difficulty == 1 and not blocked_any:
            return SemaphoreProblem(difficulty, initial, ops, seed)
        if difficulty == 2 and blocked_any and woken_any and len(result["blocked"]) <= 2:
            return SemaphoreProblem(difficulty, initial, ops, seed)
        if difficulty == 3 and blocked_any and woken_any and result["blocked"]:
            return SemaphoreProblem(difficulty, initial, ops, seed)
    return SemaphoreProblem(difficulty, initial, ops, seed)


def problem_from_dict(d: dict):
    kind = d.get("kind", "scheduling")
    if kind == "advanced":
        from engine.advanced import AdvancedProblem
        return AdvancedProblem.from_dict(d)
    if kind == "bankers":
        return BankersProblem.from_dict(d)
    if kind == "semaphore":
        return SemaphoreProblem.from_dict(d)
    return SchedulingProblem.from_dict(d)
