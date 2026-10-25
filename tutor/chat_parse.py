"""
Read what students type or paste into the chat: scheduling and Banker's problems, and answers
(Gantt charts, CT/TAT/WT values, safe/unsafe with a sequence, semaphore values).

Everything here is plain pattern matching, so it is fast, predictable and testable. The parsers are
deliberately forgiving about layout (exam tables, inline lists, "P1(0,5)", "P1 AT=0 BT=5", column lists),
and return None when they are not sure, so the tutor asks instead of guessing.
"""
from __future__ import annotations

import re
import unicodedata

from engine.scheduling import IDLE, Process

ALGO_ORDER = ["FCFS", "SJF", "SRTF", "RR", "PRIORITY_NP", "PRIORITY_P"]


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"[–—−]", "-", text)
    return text.replace("→", "->").replace("⟶", "->")


# --------------------------------------------------------------------------- algorithms
_PRE = re.compile(r"(?<!non)(?<!non-)(?<!non )\bpre-?emptive|\bpreemption", re.I)
_NONPRE = re.compile(r"\bnon[- ]?pre-?emptive|\bnon[- ]?preemption", re.I)
_ALGO_PATTERNS = [
    (r"\bsrtf\b|\bsrt\b|shortest[- ]remaining|\bstcf\b", "SRTF"),
    (r"round[- ]?robin|\brr\b", "RR"),
    (r"\bfcfs\b|first[- ]come|\bfifo\b", "FCFS"),
    (r"\bsjf\b|shortest[- ]job|\bspn\b|shortest[- ]process", "SJF"),
    (r"\bpriority\b", "PRIORITY"),
]


_PRIO_PHRASE = re.compile(r"non[- ]?pre-?emptive\s*priority|pre-?emptive\s*priority|priority\s*\(?\s*(?:non[- ]?)?pre-?emptive|"
                          r"priority\s*(?:scheduling|algorithm|based)|(?:using|with|by|use)\s*priority", re.I)


def detect_algorithms(text: str) -> list[str]:
    """All scheduling algorithms named in the text, in order of appearance."""
    t = norm(text)
    hits: list[tuple[int, str]] = []
    pre = bool(_PRE.search(t)) and not _NONPRE.search(t)
    for pat, algo in _ALGO_PATTERNS[:-1]:
        m = re.search(pat, t, re.I)
        if not m:
            continue
        if algo == "SJF" and re.search(r"(?<!non-)(?<!non )(?<!non)pre-?emptive\s*(?:sjf|shortest)|(?:sjf|shortest job first)\s*\(?\s*pre-?emptive", t, re.I):
            algo = "SRTF"
        hits.append((m.start(), algo))
    pm = _PRIO_PHRASE.search(t)
    if pm:                      # a "priority" column in an SJF table is not a request for priority scheduling
        phrase = pm.group(0).lower()
        p_pre = bool(re.search(r"pre-?emptive", phrase)) and not re.search(r"non[- ]?pre", phrase) if "emptive" in phrase else pre
        hits.append((pm.start(), "PRIORITY_P" if p_pre else "PRIORITY_NP"))
    elif not hits and re.search(r"\bpriorit\w*|\bprio\b|\bpri?\s*\d", t, re.I):
        hits.append((0, "PRIORITY_P" if pre else "PRIORITY_NP"))
    out: list[str] = []
    for _, a in sorted(hits):
        if a not in out:
            out.append(a)
    return out


def detect_quantum(text: str) -> int | None:
    m = re.search(r"(?:quantum|time[- ]?slice|\btq\b|\bq\b)\s*(?:=|:|is|of|as|size)?\s*(?:=|:)?\s*(\d+)", norm(text), re.I)
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------- scheduling problems
_PID = r"(?:(?i:P\s?\d{1,2})|[A-H](?![a-z]))"
_PID_RE = re.compile(rf"(?<![\w])({_PID})(?![\w])")
_STOP = re.compile(r"[;\n]|\b(?:quantum|time[- ]?slice|tq|find|draw|calculate|compute|average|gantt|solve|determine|"
                   r"what|using|use)\b", re.I)
_NAMED = {
    "arrival": re.compile(r"(?:\bAT\b|\barrival(?:\s*time)?|\barrives?(?:\s*at)?|\barr\b|\b(?:at|arr|a)(?=\d))\s*[:=]?\s*(\d+)", re.I),
    "burst": re.compile(r"(?:\bBT\b|\bburst(?:\s*time)?|\bcpu(?:\s*(?:time|burst))?|\bservice(?:\s*time)?|"
                        r"\bexec(?:ution)?(?:\s*time)?|\bneeds|\bruns?\s*for|\bduration|\b(?:bt|b)(?=\d))\s*[:=]?\s*(\d+)", re.I),
    "priority": re.compile(r"(?:\bpriority|\bprio|\bpr\b|\bpri\b|\b(?:pri|pr|p)(?=\d\b))\s*[:=]?\s*(\d+)", re.I),
}
_HEAD = {"arrival": r"(?i:arrival)|\bAT\b|\bArr\b",
         "burst": r"(?i:burst|\bcpu\b|service|execution|\bexec\b|run\s*time)|\bBT\b",
         "priority": r"(?i:priority|\bprio\b)|\bPR\b|\bPri\b"}


def normalise_pid(raw: str) -> str:
    s = raw.strip().replace(" ", "")
    return s.upper() if s[:1].lower() == "p" else s


def _column_order(head: str) -> list[str] | None:
    """Column order from a table header. 'AT'/'BT' only count in capitals, so English "at" is ignored."""
    found = []
    for name, pat in _HEAD.items():
        m = re.search(pat, head)
        if m:
            found.append((m.start(), name))
    return [n for _, n in sorted(found)] or None


def _ints(s: str) -> list[int]:
    return [int(x) for x in re.findall(r"(?<![\w.])\d+(?![\w]|\.\d)", s)]


def _from_spans(text: str) -> list[dict]:
    """One entry per process mention: its pid and the text up to the next pid."""
    ms = list(_PID_RE.finditer(text))
    spans = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        span = text[m.end():end]
        stop = _STOP.search(span)
        if stop and i + 1 == len(ms):
            span = span[:stop.start()]
        spans.append({"pid": normalise_pid(m.group(1)), "span": span, "pos": m.start()})
    return spans


def parse_scheduling_problem(text: str) -> dict | None:
    """Returns {"processes": [Process], "algorithms": [...], "quantum": int|None} or None."""
    t = norm(text)
    if re.search(r"\b(ct|tat|wt)\s*[:=]?\s*\d", t, re.I) and not re.search(r"\b(burst|arrival|BT|AT)\b", t):
        return None                                      # looks like an answer, not a problem
    head = re.search(r"\b(ct|tat|wt)\b[^\n]*\b(ct|tat|wt)\b", t, re.I)
    if head and not re.search(r"\b(burst|BT|cpu)\b", t, re.I) and \
            re.search(r"(?m)^\s*\S+\s+\d+\s+\d+\s+\d+", t[head.end():]):
        return None                                      # a table of CT / TAT / WT values
    all_arrive_zero = bool(re.search(r"(all|every)\s*(the\s*)?(processes|jobs)?\s*(arrive|arrived)\s*(at\s*)?(time\s*)?(t\s*=\s*)?0", t, re.I))
    spans = _from_spans(t)
    procs: dict[str, dict] = {}
    if spans:
        order = _column_order(t[:spans[0]["pos"]])
        if not order or "burst" not in order:       # e.g. only "priority" from the algorithm's name
            order = ["arrival", "burst", "priority"]
        for sp in spans:
            if sp["pid"] in procs:
                continue
            named = {k: int(m.group(1)) for k, rx in _NAMED.items() if (m := rx.search(sp["span"]))}
            nums = _ints(sp["span"])
            vals: dict[str, int] = {}
            if "burst" in named:
                vals = named
                if "arrival" not in vals:
                    vals["arrival"] = 0
            elif nums:
                if "priority" in named:          # "P5 4 5 prio 2": the named value is not a column
                    pm = _NAMED["priority"].search(sp["span"])
                    nums = _ints(sp["span"][:pm.start()]) or nums
                cols = ["burst"] if len(nums) == 1 else order
                for k, v in zip(cols, nums[:len(cols)]):
                    vals[k] = v
                vals.setdefault("arrival", 0)
                if "priority" in named:
                    vals["priority"] = named["priority"]
            if "burst" in vals:
                procs[sp["pid"]] = vals
    if len(procs) < 2:
        procs = _column_lists(t)
    if len(procs) < 2 or any(v.get("burst", 0) < 1 for v in procs.values()):
        return None
    if all_arrive_zero:
        for v in procs.values():
            v["arrival"] = 0
    processes = [Process(pid, v.get("arrival", 0), v["burst"], v.get("priority", 0)) for pid, v in procs.items()]
    return {"processes": processes, "algorithms": detect_algorithms(t), "quantum": detect_quantum(t)}


def _column_lists(t: str) -> dict[str, dict]:
    def grab(pat: str) -> list[int] | None:
        m = re.search(pat + r"[^0-9\n]{0,25}((?:\d+\s*(?:,|and|\s)\s*)+\d+)", t, re.I)
        return _ints(m.group(1)) if m else None
    burst = grab(r"(?:burst|cpu|service|execution|(?-i:\bBT\b)|(?-i:\bbt\b))(?:\s*times?|s)?")
    if not burst or len(burst) < 2:
        return {}
    n = len(burst)
    arr = grab(r"(?:arrival|arrive|(?-i:\bAT\b)|(?-i:\bat\s*:))(?:\s*times?|s)?")
    pri = grab(r"priorit(?:y|ies)")
    names = [normalise_pid(m.group(1)) for m in _PID_RE.finditer(t)]
    names = list(dict.fromkeys(names))
    if len(names) != n:
        names = [f"P{i + 1}" for i in range(n)]
    out = {}
    for i, pid in enumerate(names):
        out[pid] = {"burst": burst[i], "arrival": arr[i] if arr and len(arr) == n else 0}
        if pri and len(pri) == n:
            out[pid]["priority"] = pri[i]
    return out


# --------------------------------------------------------------------------- Banker's problems
def _expand_compact(t: str) -> str:
    """'P0 010 P1 200 ... avail 332' (one digit per resource, typed without spaces) → 'P0 0 1 0 ...'."""
    if len(re.findall(r"\bP\s?\d{1,2}\s*[:=]?\s*\d{2,5}\b(?!\s*[,.]?\s*\d)", t, re.I)) < 2:
        return t
    t = re.sub(r"(\bP\s?\d{1,2}\s*[:=]?\s*)(\d{2,5})\b(?!\s*[,.]?\s*\d)", lambda m: m.group(1) + " ".join(m.group(2)), t, flags=re.I)
    return re.sub(r"(\bavail\w*\s*[:=]?\s*)(\d{2,5})\b(?!\s*[,.]?\s*\d)", lambda m: m.group(1) + " ".join(m.group(2)), t, flags=re.I)


_SECTION = re.compile(r"\b(alloc\w*|max\w*|claim\w*|need\w*|avail\w*|total\w*)\b", re.I)


def _unlabelled(t: str) -> dict | None:
    """Matrices given as rows without process names: 'Allocation rows: 1 0 1 / 1 1 0', or a header line followed
    by one row per line ('Banker claim matrix\n7 5 3\n...')."""
    marks = [(m.start(), m.end(), m.group(1).lower()) for m in _SECTION.finditer(t)]
    sections: dict[str, list[list[int]]] = {}
    for i, (_, end, word) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(t)
        rows = [_ints(r) for r in re.split(r"\n|/|;|\|", t[end:stop])]
        rows = [r for r in rows if r]
        key = "max" if word.startswith(("max", "claim")) else word[:4] if word.startswith(("need", "avai")) else \
            "alloc" if word.startswith("alloc") else "total"
        if rows and key not in sections:
            sections[key] = rows
    if "alloc" not in sections or "max" not in sections or len(sections["alloc"]) < 2:
        return None
    alloc, mx = sections["alloc"], sections["max"]
    if len(alloc) != len(mx):
        return None
    if "avai" in sections:
        avail = sections["avai"][0]
    elif "total" in sections:
        total = sections["total"][0]
        avail = [tot - sum(r[j] for r in alloc) for j, tot in enumerate(total)] if len(total) == len(alloc[0]) else None
    else:
        avail = None
    if not avail:
        return None
    return {"alloc": alloc, "max": mx, "avail": avail}


def _single_resource(t: str) -> dict | None:
    """One resource type: '3 processes, max need 10, 4, 9. allocated 5, 2, 4. total 12' (Available = total − held)."""
    def nums(pat):
        m = re.search(pat + r"[^0-9\n]{0,20}((?:\d+\s*(?:,|and|\s)\s*)+\d+)", t, re.I)
        return _ints(m.group(1)) if m else None
    mx = nums(r"\b(?:max(?:imum)?(?:\s*needs?)?|claims?)")
    alloc = nums(r"\balloc\w*")
    if not mx or not alloc or len(mx) != len(alloc) or len(mx) < 2:
        return None
    m = re.search(r"\bavail\w*\D{0,15}(\d+)", t, re.I)
    if m:
        avail = int(m.group(1))
    else:
        m = re.search(r"\btotal\b\D{0,30}(\d+)|(\d+)\s*(?:instances|resources|units)\s*(?:in total|total)", t, re.I)
        if not m:
            return None
        avail = int(m.group(1) or m.group(2)) - sum(alloc)
    return {"alloc": [[a] for a in alloc], "max": [[x] for x in mx], "avail": [avail]}


def parse_bankers_problem(text: str) -> dict | None:
    """Allocation / Max / Available, either as separate tables or side by side in one table; also compact digits
    ('P0 010'), 'P0(0,1,0)', unlabelled rows, 'claim' for Max, 'total' instead of Available, one resource type."""
    t = _expand_compact(norm(text))
    low = t.lower()
    if "alloc" not in low or not re.search(r"\bmax|\bclaim", low):
        return None
    inter = list(re.finditer(r"\bP\s?(\d{1,2})\s*[:=]?\s*((?:\d+[ \t,]+){0,4}\d+)\s*max\w*\s*[:=]?\s*((?:\d+[ \t,]+){0,4}\d+)", t, re.I))
    if len(inter) >= 2:
        avail_m = re.search(r"avail\w*\s*[:=]?\s*[(\[]?\s*((?:\d+[ \t,]+)*\d+)", t, re.I)
        if avail_m:
            got = _bankers_result([_ints(m.group(2)) for m in inter], [_ints(m.group(3)) for m in inter],
                                  _ints(avail_m.group(1)), int(inter[0].group(1)))
            if got:
                return got
    if not re.search(r"\bP\s?\d", t, re.I):
        found = _unlabelled(t) or _single_resource(t)
        if found is None:
            return None
        return _bankers_result(found["alloc"], found["max"], found["avail"], 0)
    occ: dict[int, list[list[int]]] = {}
    first_row = None
    for m in re.finditer(r"\bP\s?(\d{1,2})\b[ \t:|,(\[=]*((?:\d+[ \t,|]+)*\d+)", t, re.I):
        occ.setdefault(int(m.group(1)), []).append(_ints(m.group(2)))
        first_row = m.start() if first_row is None else first_row
    pids = sorted(occ)
    if len(pids) < 2 or pids != list(range(pids[0], pids[0] + len(pids))):
        return None
    keys = (("alloc", r"alloc"), ("max", r"\bmax|\bclaim"), ("need", r"\bneed"), ("avail", r"\bavail"))
    before = [ln for ln in low[:first_row].splitlines() if ln.strip()]
    header = before[-1] if before else ""
    region = header if sum(k in header for k in ("alloc", "max")) == 2 else low
    found = []
    for k, pat in keys:
        m = re.search(pat, region)
        if m:
            found.append((m.start(), k))
    sec = [k for _, k in sorted(found)]
    alloc, mx, avail = [], [], None
    if all(len(occ[p]) >= 2 for p in pids):                      # separate tables, one after the other
        order = [k for k in sec if k in ("alloc", "max", "need")]
        if "alloc" not in order or "max" not in order:
            return None
        for p in pids:
            if len(occ[p]) < len(order):
                return None
            alloc.append(occ[p][order.index("alloc")])
            mx.append(occ[p][order.index("max")])
    else:                                                        # one table, blocks side by side
        blocks_in_row = [k for k in sec if k in ("alloc", "max", "need", "avail")]
        mats = [k for k in blocks_in_row if k != "avail"] or ["alloc", "max"]
        lens = [len(occ[p][0]) for p in pids]
        if min(lens) % len(mats):
            return None
        m_res = min(lens) // len(mats)
        for p in pids:
            r = occ[p][0]
            blocks = {k: r[i * m_res:(i + 1) * m_res] for i, k in enumerate(blocks_in_row or ["alloc", "max", "avail"])
                      if len(r) >= (i + 1) * m_res}
            if "alloc" not in blocks or "max" not in blocks:
                return None
            alloc.append(blocks["alloc"])
            mx.append(blocks["max"])
            if p == pids[0] and len(blocks.get("avail", [])) == m_res:
                avail = blocks["avail"]
    am = re.search(r"avail\w*\s*(?:\([^)]*\))?\s*(?:vector|is|=|:)?\s*[(\[<]?\s*((?:\d+[ \t,]+)*\d+)", t, re.I)
    if am:
        avail = _ints(am.group(1))
    elif alloc and (tm := re.search(r"\btotal\w*\s*(?:instances|resources)?\s*(?:[A-Z](?:\s*,?\s*[A-Z])*)?\s*[:=(]?\s*((?:\d+[ \t,]+)*\d+)", t, re.I)):
        total = _ints(tm.group(1))                         # 'total 10 5 7': Available = total − everything held
        if len(total) == len(alloc[0]):
            avail = [tot - sum(r[j] for r in alloc) for j, tot in enumerate(total)]
    if not alloc or not avail:
        return None
    return _bankers_result(alloc, mx, avail, pids[0])


def _bankers_result(alloc, mx, avail, first_pid) -> dict | None:
    m_res = len(alloc[0])
    if len(avail) != m_res or any(len(r) != m_res for r in alloc + mx):
        return None
    if any(a > b for ra, rb in zip(alloc, mx) for a, b in zip(ra, rb)):
        return None
    if any(v < 0 for v in avail):
        return None
    return {"available": avail, "maximum": mx, "allocation": alloc, "resources": list("ABCDE")[:m_res],
            "first_pid": first_pid}


def parse_detection_problem(text: str) -> dict | None:
    """Deadlock detection: Allocation and Request (no Max), separate tables or side by side, plus Available."""
    t = norm(text)
    low = t.lower()
    if "alloc" not in low or not re.search(r"\brequest", low) or re.search(r"\bmax", low):
        return None
    occ: dict[int, list[list[int]]] = {}
    for m in re.finditer(r"\bP\s?(\d{1,2})\b[ \t:|,]*((?:\d+[ \t,|]+)*\d+)", t, re.I):
        occ.setdefault(int(m.group(1)), []).append(_ints(m.group(2)))
    pids = sorted(occ)
    if len(pids) < 2 or pids != list(range(pids[0], pids[0] + len(pids))):
        return None
    alloc_first = low.index("alloc") < re.search(r"\brequest", low).start()
    alloc, req = [], []
    for p in pids:
        rows = occ[p]
        if len(rows) >= 2:                                       # two tables, one after the other
            a, r = (rows[0], rows[1]) if alloc_first else (rows[1], rows[0])
        elif len(rows[0]) % 2 == 0:                              # one table: Allocation | Request side by side
            half = len(rows[0]) // 2
            a, r = (rows[0][:half], rows[0][half:]) if alloc_first else (rows[0][half:], rows[0][:half])
        else:
            return None
        alloc.append(a)
        req.append(r)
    am = re.search(r"avail\w*\s*(?:\([^)]*\))?\s*(?:vector|is|=|:)?\s*[(\[<]?\s*((?:\d+[ \t,]+)*\d+)", t, re.I)
    if not am:
        return None
    avail = _ints(am.group(1))
    m_res = len(avail)
    if any(len(row) != m_res for row in alloc + req):
        return None
    return {"available": avail, "allocation": alloc, "request": req, "first_pid": pids[0]}


# --------------------------------------------------------------------------- answers
_SEG = re.compile(rf"(?<![\w])((?i:P\s?\d{{1,2}}|idle)|[A-H])\s*[:(\[]?\s*(\d+)\s*(?:-|to|->)\s*(\d+)\s*[)\]]?")
_SEG_REV = re.compile(rf"(?<![\w.])(\d+)\s*(?:-|to|->)\s*(\d+)\s*[:=]?\s*((?i:P\s?\d{{1,2}}|idle)|[A-H])(?![\w])")


def parse_gantt_text(text: str, pids: list[str] | None = None) -> list[tuple[str, int, int]]:
    t = norm(text)
    segs = [(m.group(1), int(m.group(2)), int(m.group(3))) for m in _SEG.finditer(t)]
    if len(segs) < 2:
        segs = [(m.group(3), int(m.group(1)), int(m.group(2))) for m in _SEG_REV.finditer(t)]
    if len(segs) < 2:
        segs = _bar_chart(t)
    out = []
    for pid, s, e in segs:
        p = IDLE if pid.lower() == "idle" else normalise_pid(pid)
        if pids and p != IDLE and p not in pids:
            continue
        if e > s:
            out.append((p, s, e))
    return out if len(out) >= 1 else []


_BAR_NAME = re.compile(rf"(?<![\w])((?i:P\s?\d{{1,2}}|idle)|[A-H](?![a-z]))(?![\w])")


def _bar_chart(t: str) -> list[tuple[str, int, int]]:
    lines = [ln for ln in t.splitlines() if ln.strip()]
    for i, ln in enumerate(lines[:-1]):
        names = [m.group(1) for m in _BAR_NAME.finditer(ln)]          # processes and idle gaps, in order
        if len(names) >= 2 and ("|" in ln or "->" in ln):
            nums = _ints(lines[i + 1])
            if len(nums) == len(names) + 1 and nums == sorted(nums):
                return [(names[k], nums[k], nums[k + 1]) for k in range(len(names))]
    return []


_LABELS = {"CT": r"\bct\b|completion(?:\s*time)?|finish(?:ing)?(?:\s*time)?|\bft\b",
           "TAT": r"\btat\b|turn\s*-?\s*around(?:\s*time)?",
           "WT": r"\bwt\b|waiting(?:\s*time)?"}


def parse_metrics(text: str, pids: list[str]) -> dict[str, dict]:
    """Per-process CT/TAT/WT: labelled ("P1: CT 5, TAT 5, WT 0"), a table with a header, or column lists."""
    t = norm(text)
    out: dict[str, dict] = {}
    # 1) labelled values next to each process
    for sp in _from_spans(t):
        if sp["pid"] not in pids:
            continue
        row = {}
        for k, lab in _LABELS.items():
            m = re.search(rf"(?:{lab})\s*(?:of\s*\w+\s*)?(?:[:=]|is|was)?\s*(?:=\s*)?(-?\d+)(?![\d.])", sp["span"], re.I)
            if m:
                row[k] = int(m.group(1))
        if row:
            out.setdefault(sp["pid"], {}).update(row)
    if out:
        return out
    # 2) a table: header line naming the columns, then one row per process
    lines = t.splitlines()
    for i, ln in enumerate(lines):
        toks = re.findall(r"\b(at|bt|ct|tat|wt|rt|pr|priority|arrival|burst|completion|turnaround|waiting|response)\b", ln, re.I)
        cols = []
        for tok in toks:
            tl = tok.lower()
            cols.append({"arrival": "AT", "burst": "BT", "completion": "CT", "turnaround": "TAT", "waiting": "WT",
                         "response": "RT", "priority": "PR", "pr": "PR"}.get(tl, tl.upper()))
        if sum(c in ("CT", "TAT", "WT") for c in cols) >= 2:
            for ln2 in lines[i + 1:]:
                m = re.match(rf"\s*\|?\s*({_PID})\b(.*)", ln2)
                if not m:
                    continue
                pid = normalise_pid(m.group(1))
                nums = _ints(m.group(2))
                if pid in pids and len(nums) == len(cols):
                    out[pid] = {c: v for c, v in zip(cols, nums) if c in ("CT", "TAT", "WT")}
            if out:
                return out
    # 3) one label, then the processes: "waiting times P1 = 4, P2 = 1, P3 = 0", "WT of P1 is 4, P2 is 1 and P3 is 0"
    any_label = "|".join(f"(?:{lab})" for lab in _LABELS.values())
    for k, lab in _LABELS.items():
        for m in re.finditer(rf"(?:{lab})s?", t, re.I):
            rest = t[m.end():]
            stop = re.search(rf"{any_label}|\b(?:avg|average|mean)\b|\n", rest, re.I)
            seg = rest[:stop.start()] if stop else rest
            pairs = re.findall(rf"(?<![\w])({_PID})(?![\w])\s*(?:=|:|is|was|->|→|-)?\s*(-?\d+)(?![\d.])", seg)
            for pid, v in pairs:
                pid = normalise_pid(pid)
                if pid in pids:
                    out.setdefault(pid, {})[k] = int(v)
            if not pairs:
                vals = _ints(seg)
                if len(vals) == len(pids) and re.match(r"\s*(?:times?|values?)?\s*(?:are|is|=|:|as)?\s*\d", seg):
                    for pid, v in zip(pids, vals):
                        out.setdefault(pid, {})[k] = v
    if out:
        return out
    # 4) column lists: "CT: 5, 8, 12"
    for k, lab in _LABELS.items():
        m = re.search(rf"(?:{lab})s?\s*[:=]\s*((?:-?\d+\s*(?:,|\s)\s*)+-?\d+)", t, re.I)
        if m:
            vals = [int(x) for x in re.findall(r"-?\d+", m.group(1))]
            if len(vals) == len(pids):
                for pid, v in zip(pids, vals):
                    out.setdefault(pid, {})[k] = v
    return out


def parse_averages(text: str) -> dict[str, float]:
    t = norm(text)
    out = {}
    for k, lab in (("WT", r"waiting(?:\s*time)?|wt"), ("TAT", r"turn\s*-?\s*around(?:\s*time)?|tat")):
        m = re.search(rf"(?:avg|average|mean)\.?\s*(?:{lab})[^0-9\n]{{0,25}}(\d+(?:\.\d+)?)", t, re.I) or \
            re.search(rf"\ba(?:vg)?\s*{k.lower()}\s*[:=]\s*(\d+(?:\.\d+)?)", t, re.I)
        if not m:
            # "waiting times P1 = 4, P2 = 1, P3 = 0, average 1.67": the average named after the label's values
            other = r"turn\s*-?\s*around|\btat\b" if k == "WT" else r"waiting|\bwt\b"
            m = re.search(rf"\b(?:{lab})(?:(?!{other})[^\n]){{0,80}}?\b(?:avg|average|mean)\b\s*(?:=|:|is|of)?\s*(\d+(?:\.\d+)?)",
                          t, re.I)
        if m:
            clause = re.split(r"[,;?\n]|\bis (?:this|that|it)\b|\bright\b|\bcorrect\b", t[m.start():], maxsplit=1)[0]
            if clause.count("=") >= 2 or re.search(r"=\s*\(", clause):
                last = re.findall(r"=\s*(\d+(?:\.\d+)?)\s*$|=\s*(\d+(?:\.\d+)?)(?!.*=)", clause)
                vals = [a or b for a, b in last if a or b]
                if vals:
                    out[k] = float(vals[-1])
                    continue
            out[k] = float(m.group(1))
    return out


def parse_order(text: str, pids: list[str]) -> list[str] | None:
    """The order of Gantt slices written without times, after a word like 'order', 'gantt' or 'chart'."""
    t = norm(text)
    m = re.search(r"\b(order|gantt(?:\s*chart)?|chart|sequence|schedule)\b(?:\s*(?:is|was|as|=|:))?", t, re.I)
    if not m:
        return None
    seq = []
    for tok in re.finditer(rf"(?<![\w])({_PID})(?![\w])|[.?!]", t[m.end():]):
        if not tok.group(1):
            break
        seq.append(normalise_pid(tok.group(1)))
    seq = [p for p in seq if p in pids]
    return seq if len(seq) >= 3 else None


def parse_scheduling_answer(text: str, pids: list[str]) -> dict | None:
    gantt = parse_gantt_text(text, pids)
    metrics = parse_metrics(text, pids)
    avgs = parse_averages(text)
    order = None if gantt else parse_order(text, pids)
    if not gantt and not metrics and not avgs:
        return {"gantt": [], "metrics": {}, "averages": {}, "order": order} if order else None
    out = {"gantt": gantt, "metrics": metrics, "averages": avgs}
    if order:
        out["order"] = order
    return out


def parse_bankers_answer(text: str, n: int, first_pid: int = 0) -> dict | None:
    t = norm(text)
    low = t.lower()
    safe = None
    if re.search(r"\bunsafe\b|\bnot\s+(?:in\s+)?(?:a\s+)?safe\b|\bno\s+safe\s+sequence", low):
        safe = False
    elif re.search(r"\bsafe\b", low):
        safe = True
    pids = [normalise_pid(m) for m in re.findall(r"(?i)\bP\s?\d{1,2}\b", t)]
    seq = list(dict.fromkeys(pids))
    sequence = seq if len(seq) == n and len(pids) == n else None
    if safe is None and sequence:
        safe = True
    if safe is None:
        return None
    return {"safe": safe, "sequence": sequence}


def parse_semaphore_answer(text: str, sems: list[str]) -> dict | None:
    t = norm(text)
    low = t.lower()
    final = {}
    for s in sems:
        m = re.search(rf"(?<![\w]){re.escape(s)}(?![\w])\s*(?:=|:|is|becomes|ends at|ends up at|final(?:ly)?)\s*(-?\d+)", t, re.I)
        if m:
            final[s] = int(m.group(1))
    blocked = None
    if re.search(r"\b(no|none|nobody|no process(?:es)?|no one)\b[^.\n]{0,25}\bblocked\b|\bblocked\s*[:=]?\s*(none|nobody|no one|nothing|\[\s*\]|-)", low):
        blocked = []
    else:
        m = re.search(r"\bblocked\b\s*(?:processes?)?\s*(?:are|is|:|=)?\s*([^.\n]*)", t, re.I)
        span = m.group(1) if m else ""
        found = re.findall(r"(?i)\bP\s?\d{1,2}\b", span)
        if not found:
            m2 = re.search(r"((?:P\s?\d{1,2}\s*(?:,|and|&)?\s*)+)\s*(?:is|are|remain|stay)s?\s*blocked", t, re.I)
            found = re.findall(r"(?i)P\s?\d{1,2}", m2.group(1)) if m2 else []
        if found or m:
            blocked = [normalise_pid(x) for x in found]
    if not final and blocked is None:
        return None
    return {"final": final, "blocked": blocked}
