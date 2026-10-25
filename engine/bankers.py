"""
Banker's algorithm (deadlock avoidance) for the OS Engine.

Key teaching point built into the design: a system can have MANY valid safe
sequences. So a student's sequence is checked by *simulating* it
(verify_sequence), not by comparing it with one stored answer.

Scan convention for safety(): "cyclic" walks P0..Pn-1 repeatedly, continuing
from where it last found a process (this reproduces the Silberschatz textbook
answer <P1, P3, P4, P0, P2>). "restart" goes back to P0 after every allocation.
"""
from __future__ import annotations

Vector = list[int]
Matrix = list[list[int]]


def _le(a: Vector, b: Vector) -> bool:
    return all(x <= y for x, y in zip(a, b))


def _add(a: Vector, b: Vector) -> Vector:
    return [x + y for x, y in zip(a, b)]


def _sub(a: Vector, b: Vector) -> Vector:
    return [x - y for x, y in zip(a, b)]


def validate(available: Vector, maximum: Matrix, allocation: Matrix) -> None:
    m = len(available)
    if len(maximum) != len(allocation):
        raise ValueError("Max and Allocation must have the same number of processes.")
    for i, (mx, al) in enumerate(zip(maximum, allocation)):
        if len(mx) != m or len(al) != m:
            raise ValueError(f"P{i}: every row needs {m} resource values.")
        if any(a > x for a, x in zip(al, mx)):
            raise ValueError(f"P{i}: allocation cannot exceed maximum claim.")
        if any(v < 0 for v in mx + al):
            raise ValueError(f"P{i}: values cannot be negative.")
    if any(v < 0 for v in available):
        raise ValueError("Available cannot be negative.")


def compute_need(maximum: Matrix, allocation: Matrix) -> Matrix:
    return [_sub(mx, al) for mx, al in zip(maximum, allocation)]


def safety(available: Vector, maximum: Matrix, allocation: Matrix, scan: str = "cyclic") -> dict:
    """Run the safety algorithm and return the sequence plus a step-by-step trace."""
    validate(available, maximum, allocation)
    n = len(maximum)
    need = compute_need(maximum, allocation)
    work = list(available)
    finish = [False] * n
    sequence: list[str] = []
    steps: list[dict] = []
    checks: list[dict] = []   # every Need <= Work comparison, for detailed explanations
    i = 0
    progress = True
    while progress and not all(finish):
        progress = False
        order = list(range(i, n)) + list(range(0, i)) if scan == "cyclic" else list(range(n))
        for j in order:
            if finish[j]:
                continue
            ok = _le(need[j], work)
            checks.append({"process": f"P{j}", "need": need[j], "work": list(work), "ok": ok})
            if ok:
                before = list(work)
                work = _add(work, allocation[j])
                finish[j] = True
                sequence.append(f"P{j}")
                steps.append({"step": len(sequence), "process": f"P{j}", "need": need[j],
                              "work_before": before, "allocation_released": allocation[j],
                              "work_after": list(work)})
                progress = True
                i = (j + 1) % n
                break
    safe = all(finish)
    return {
        "safe": safe,
        "sequence": sequence if safe else [],
        "partial_sequence": sequence,
        "stuck": [f"P{k}" for k in range(n) if not finish[k]],
        "need": need,
        "steps": steps,
        "checks": checks,
        "final_work": work,
    }


def verify_sequence(available: Vector, maximum: Matrix, allocation: Matrix, sequence: list[str]) -> dict:
    """Check whether a student-proposed sequence is a valid safe sequence."""
    validate(available, maximum, allocation)
    n = len(maximum)
    need = compute_need(maximum, allocation)
    names = [s.strip().upper() for s in sequence if s.strip()]
    expected = {f"P{k}" for k in range(n)}
    if sorted(names) != sorted(expected) or len(set(names)) != n:
        missing = sorted(expected - set(names))
        dupes = sorted({x for x in names if names.count(x) > 1})
        unknown = sorted(set(names) - expected)
        return {"valid": False, "error": "incomplete_sequence", "fail_step": None,
                "detail": {"missing": missing, "duplicates": dupes, "unknown": unknown},
                "message": "A safe sequence must list every process exactly once."}
    work = list(available)
    for step, name in enumerate(names, start=1):
        k = int(name[1:])
        if not _le(need[k], work):
            short = [r for r, (nd, w) in enumerate(zip(need[k], work)) if nd > w]
            return {"valid": False, "error": "need_exceeds_work", "fail_step": step,
                    "detail": {"process": name, "need": need[k], "work": list(work),
                               "short_resources": short},
                    "message": f"At step {step}, {name} needs {need[k]} but only {work} is available."}
        work = _add(work, allocation[k])
    return {"valid": True, "error": None, "fail_step": None, "detail": {"final_work": work},
            "message": "Every process can finish in this order, so the sequence is safe."}


def request(available: Vector, maximum: Matrix, allocation: Matrix, pid: int, req: Vector) -> dict:
    """Resource-request algorithm: can the request be granted immediately?"""
    validate(available, maximum, allocation)
    need = compute_need(maximum, allocation)
    if not _le(req, need[pid]):
        return {"granted": False, "reason": "exceeds_need",
                "message": f"P{pid} asked for {req}, which is more than its remaining need {need[pid]}. This is an error."}
    if not _le(req, available):
        return {"granted": False, "reason": "must_wait",
                "message": f"Request {req} exceeds Available {available}, so P{pid} must wait."}
    new_avail = _sub(available, req)
    new_alloc = [list(r) for r in allocation]
    new_alloc[pid] = _add(new_alloc[pid], req)
    result = safety(new_avail, maximum, new_alloc)
    if result["safe"]:
        return {"granted": True, "reason": "safe", "new_available": new_avail, "new_allocation": new_alloc,
                "safety": result,
                "message": f"Pretending to grant leaves a safe state ({', '.join(result['sequence'])}), so the request is granted."}
    return {"granted": False, "reason": "unsafe", "new_available": new_avail, "new_allocation": new_alloc,
            "safety": result,
            "message": "Granting the request would leave the system unsafe, so P%d must wait." % pid}
