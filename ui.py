"""Rendering helpers for the Streamlit app (Gantt charts, tables, demo answer presets)."""
from __future__ import annotations

import html

import pandas as pd

from engine import scheduling
from engine.scheduling import IDLE, Segment

PALETTE = ["#2563eb", "#db2777", "#059669", "#d97706", "#7c3aed", "#0891b2", "#dc2626", "#4d7c0f"]


def color_for(pid: str, order: list[str]) -> str:
    if pid == IDLE:
        return "repeating-linear-gradient(45deg,#9ca3af33,#9ca3af33 6px,#9ca3af55 6px,#9ca3af55 12px)"
    i = order.index(pid) if pid in order else hash(pid) % len(PALETTE)
    return PALETTE[i % len(PALETTE)]


def gantt_html(segments: list, order: list[str] | None = None, highlight_time: int | None = None,
               title: str | None = None, total_time: int | None = None) -> str:
    """total_time fixes the scale (e.g. the final makespan) so a chart that grows step by step keeps its scale."""
    segs = [s if isinstance(s, Segment) else Segment(*s) for s in segments]
    if not segs and not total_time:
        return "<div style='opacity:.6;font-size:13px'>No Gantt chart yet.</div>"
    order = order or sorted({s.pid for s in segs if s.pid != IDLE})
    start0 = segs[0].start if segs else 0
    end = segs[-1].end if segs else 0
    total = max(total_time or 0, end) - start0 or 1
    blocks = []
    for i, s in enumerate(segs):
        w = 100 * s.length / total
        hl = highlight_time is not None and s.start <= highlight_time < s.end
        border = "3px solid #ef4444" if hl else "1px solid rgba(0,0,0,.15)"
        label = "idle" if s.pid == IDLE else html.escape(s.pid)
        fg = "inherit" if s.pid == IDLE else "#fff"
        end_lbl = f"<span style='position:absolute;right:-4px;bottom:-18px;font-size:11px;font-weight:400;color:#6b7280'>{s.end}</span>" if i == len(segs) - 1 else ""
        mark = ("<span style='position:absolute;left:50%;top:-20px;transform:translateX(-50%);font-size:11px;"
                "color:#ef4444;white-space:nowrap;font-weight:600'>▼ first difference</span>") if hl else ""
        blocks.append(
            f"<div style='position:relative;flex:0 0 {w:.3f}%;min-width:22px;height:38px;background:{color_for(s.pid, order)};"
            f"border:{border};box-sizing:border-box;display:flex;align-items:center;justify-content:center;"
            f"color:{fg};font-weight:600;font-size:13px'>{mark}{label}"
            f"<span style='position:absolute;left:-3px;bottom:-18px;font-size:11px;font-weight:400;color:#6b7280'>{s.start}</span>{end_lbl}</div>")
    if total_time and end < start0 + total:
        rest = 100 * (start0 + total - end) / total
        blocks.append(f"<div style='flex:0 0 {rest:.3f}%;height:38px;border:1px dashed #9ca3af;border-left:none;"
                      f"box-sizing:border-box;display:flex;align-items:center;justify-content:center;color:#9ca3af;"
                      f"font-size:13px'>?</div>")
    head = f"<div style='font-size:13px;margin-bottom:22px;opacity:.8'>{html.escape(title)}</div>" if title else \
        "<div style='height:20px'></div>"
    return (f"<div style='padding:4px 10px 26px 4px'>{head}<div style='display:flex;width:100%;border-radius:6px'>"
            + "".join(blocks) + "</div></div>")


def process_table(problem) -> pd.DataFrame:
    rows = []
    for p in problem.processes:
        r = {"Process": p.pid, "Arrival (AT)": p.arrival, "Burst (BT)": p.burst}
        if problem.algorithm in scheduling.USES_PRIORITY:
            r["Priority"] = p.priority
        rows.append(r)
    return pd.DataFrame(rows).set_index("Process")


def results_table(res: scheduling.ScheduleResult) -> pd.DataFrame:
    rows = [{"Process": r.pid, "AT": r.arrival, "BT": r.burst, "CT": r.completion, "TAT": r.turnaround,
             "WT": r.waiting, "RT": r.response} for r in res.results.values()]
    return pd.DataFrame(rows).set_index("Process")


STATUS_ICON = {"correct": "✅", "consistent": "↪️", "wrong": "❌", "missing": "—"}


def cells_table(problem, cells: dict, metrics: dict, pids: list[str] | None = None) -> pd.DataFrame:
    rows = []
    for pid in pids or [p.pid for p in problem.processes]:
        m = metrics.get(pid, {})
        row = {"Process": pid}
        for k in ("CT", "TAT", "WT"):
            v = m.get(k)
            st = cells.get(pid, {}).get(k, "missing")
            row[k] = f"{STATUS_ICON[st]} {'' if v is None else int(v) if float(v).is_integer() else v}"
        rows.append(row)
    return pd.DataFrame(rows).set_index("Process")


def decisions_table(res: scheduling.ScheduleResult) -> pd.DataFrame:
    rows = []
    for d in res.decisions:
        ready = ", ".join(f"{r['pid']}(rem {r['remaining']})" for r in d.ready) or "—"
        rows.append({"t": d.time, "Event": d.kind, "Ready": ready, "Chosen": d.chosen, "Why": d.reason})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- demo presets

def swap_two_blocks(gantt: list[tuple], i: int | None = None) -> list[tuple] | None:
    """Swap two adjacent Gantt blocks (a realistic single wrong decision)."""
    g = [x for x in gantt if x[0] != IDLE]
    if len(g) < 3 or len(g) != len(gantt):
        return None
    candidates = [k for k in range(1, len(g) - 1) if g[k][0] != g[k + 1][0]]
    if not candidates:
        return None
    k = i if i in candidates else candidates[0]
    a, b = g[k], g[k + 1]
    nb = (b[0], a[1], a[1] + (b[2] - b[1]))
    na = (a[0], nb[2], nb[2] + (a[2] - a[1]))
    return g[:k] + [nb, na] + g[k + 2:]


def scheduling_presets(problem) -> dict[str, dict]:
    """Ready-made answers for a live demo: correct, typical wrong chart, typical formula mistakes."""
    res = problem.solve()
    correct_g = [(s.pid, s.start, s.end) for s in res.gantt]
    correct_m = {pid: {"CT": r.completion, "TAT": r.turnaround, "WT": r.waiting} for pid, r in res.results.items()}
    presets = {"✅ Correct answer": {"gantt": correct_g, "metrics": correct_m}}
    wrong_rule = {"SRTF": ("SJF", {}), "SJF": ("FCFS", {}), "FCFS": ("SJF", {}),
                  "PRIORITY_NP": ("PRIORITY_NP", {"lower_is_higher": False}),
                  "PRIORITY_P": ("PRIORITY_NP", {}), "RR": ("RR", {"new_arrivals_first": False})}
    algo, opts = wrong_rule[problem.algorithm]
    alt = scheduling.run(algo, problem.processes, problem.quantum, **opts)
    if alt.timeline() == res.timeline() and problem.algorithm == "RR":
        alt = scheduling.round_robin(problem.processes, problem.quantum + 1)
    if alt.timeline() == res.timeline():
        alt = scheduling.fcfs(problem.processes) if problem.algorithm != "FCFS" else scheduling.sjf(problem.processes)
    if alt.timeline() != res.timeline():
        presets["❌ Wrong chart (common confusion), numbers consistent with it"] = {
            "gantt": [(s.pid, s.start, s.end) for s in alt.gantt],
            "metrics": {pid: {"CT": r.completion, "TAT": r.turnaround, "WT": r.waiting} for pid, r in alt.results.items()}}
    else:
        swapped = swap_two_blocks(correct_g)
        if swapped:
            presets["❌ Wrong chart (one wrong decision)"] = {"gantt": swapped, "metrics": {}}
    presets["❌ Right chart, but WT = TAT"] = {
        "gantt": correct_g, "metrics": {pid: {"CT": r.completion, "TAT": r.turnaround, "WT": r.turnaround}
                                        for pid, r in res.results.items()}}
    if any(p.arrival > 0 for p in problem.processes):
        presets["❌ Right chart, but TAT = CT"] = {
            "gantt": correct_g, "metrics": {pid: {"CT": r.completion, "TAT": r.completion, "WT": r.completion - r.burst}
                                            for pid, r in res.results.items()}}
    presets["⬜ Empty"] = {"gantt": [], "metrics": {}}
    return presets


def bankers_presets(problem) -> dict[str, dict]:
    eng = problem.solve()
    n = len(problem.maximum)
    out = {"✅ Correct answer": {"need": eng["need"], "safe": eng["safe"], "sequence": ", ".join(eng["sequence"])}}
    out["❌ Need = Allocation − Max"] = {"need": [[-v for v in row] for row in eng["need"]], "safe": True,
                                        "sequence": ", ".join(f"P{i}" for i in range(n))}
    out["❌ Right Need, sequence in index order"] = {"need": eng["need"], "safe": True,
                                                    "sequence": ", ".join(f"P{i}" for i in range(n))}
    out["⬜ Empty"] = {"need": None, "safe": None, "sequence": ""}
    return out


def semaphore_presets(problem) -> dict[str, dict]:
    eng = problem.solve()
    out = {"✅ Correct answer (blocking definition)": {"final": dict(eng["final_values"]), "blocked": list(eng["blocked"])}}
    clamped = {k: max(0, v) for k, v in eng["final_values"].items()}
    if clamped != eng["final_values"]:
        out["✅ Correct answer (busy-waiting definition, S ≥ 0)"] = {"final": clamped, "blocked": list(eng["blocked"])}
    every_blocked = sorted({s["pid"] for s in eng["steps"] if "blocks" in s["effect"]})
    if every_blocked != list(eng["blocked"]):
        out["❌ Ignores wake-ups"] = {"final": dict(eng["final_values"]), "blocked": every_blocked}
    out["⬜ Empty"] = {"final": {k: None for k in eng["final_values"]}, "blocked": []}
    return out


def advanced_presets(problem) -> dict[str, dict]:
    res = problem.solve()
    ok = {pid: {"CT": r.completion, "TAT": r.turnaround, "WT": r.waiting} for pid, r in res.results.items()}
    out = {"✅ Correct answer": {"metrics": ok}}
    if problem.has_io():
        out["✅ Correct, counting I/O as waiting"] = {"metrics": {pid: {"CT": r.completion, "TAT": r.turnaround,
                                                                          "WT": r.waiting_incl_io} for pid, r in res.results.items()}}
    out["❌ WT = TAT"] = {"metrics": {pid: {"CT": r.completion, "TAT": r.turnaround, "WT": r.turnaround}
                                      for pid, r in res.results.items()}}
    out["⬜ Empty"] = {"metrics": {}}
    return out
