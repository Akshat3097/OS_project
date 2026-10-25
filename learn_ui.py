"""Learn tab: teaches each topic from scratch in five stages (Understand → Watch → Try it → Check → Practice)."""
from __future__ import annotations

import random

import pandas as pd
import streamlit as st

import ui
from engine import bankers, generator, scheduling
from engine.generator import SchedulingProblem
from engine.scheduling import ALGORITHMS
from tutor import lessons as L
from tutor import speech
from tutor import teachback as TB
from tutor.error_analysis import analyse_scheduling

ss = st.session_state
SHORT = {"basics": "Scheduling basics", "fcfs": "FCFS", "sjf": "SJF", "srtf": "SRTF (preemptive SJF)",
         "rr": "Round Robin", "priority": "Priority scheduling", "critical_section": "Critical section",
         "semaphores": "Semaphores", "deadlock": "Deadlocks", "bankers": "Banker's algorithm"}


# ============================================================================ helpers
def _state() -> dict:
    return ss.setdefault("learn", {"lesson": None})


def _open_lesson(lid: str, students, sid: str) -> None:
    ss.learn = {"lesson": lid, "stage": 0, "watch_i": 0, "alt_text": None, "alt_source": None, "qa": [],
                "try": None, "mcq_checked": False, "tb": None}
    students.update_lesson(sid, lid, stage=0)


def recommended_lesson(progress: dict, recurring: list[dict]) -> str:
    topic_to_lesson = {"FCFS": "fcfs", "SJF": "sjf", "SRTF": "srtf", "RR": "rr", "PRIORITY_NP": "priority",
                       "PRIORITY_P": "priority", "SEMAPHORE": "semaphores", "BANKERS": "bankers",
                       "CT_READING": "basics", "TAT_FORMULA": "basics", "WT_FORMULA": "basics",
                       "BANKERS_NEED": "bankers", "BANKERS_SAFETY": "bankers"}
    for r in recurring:
        lid = topic_to_lesson.get(r.get("skill") or "") or topic_to_lesson.get(r.get("topic") or "")
        if lid:
            return lid
    return next((lid for lid in L.ORDER if not progress.get(lid, {}).get("completed")), L.ORDER[0])


def _ready_df(ready: list[dict], algorithm: str, show_remaining: bool = True) -> pd.DataFrame:
    rows = []
    for r in sorted(ready, key=lambda r: (len(r["pid"]), r["pid"])):   # fixed order, so the table never hints the answer
        row = {"Process": r["pid"], "Arrived": r["arrival"], "Burst": r["burst"]}
        if show_remaining and algorithm in scheduling.PREEMPTIVE:
            row["Remaining"] = r["remaining"]
        if algorithm in scheduling.USES_PRIORITY:
            row["Priority"] = r["priority"]
        rows.append(row)
    return pd.DataFrame(rows).set_index("Process") if rows else pd.DataFrame()


def _stage_bar(lesson: dict, idx: int) -> None:
    names = L.stages_for(lesson)
    st.progress((idx + 1) / len(names), text=f"Stage {idx + 1} of {len(names)}: **{names[idx]}**")
    st.caption("  →  ".join(f"**{n}**" if i == idx else n for i, n in enumerate(names)))


def _nav(lesson: dict, students, sid: str, next_label: str = "Next ▶") -> None:
    learn = _state()
    names = L.stages_for(lesson)
    c = st.columns([1, 1, 3])
    if learn["stage"] > 0 and c[0].button("◀ Back", key=f"back_{learn['stage']}"):
        learn["stage"] -= 1
        st.rerun()
    if learn["stage"] < len(names) - 1 and c[1].button(next_label, type="primary", key=f"next_{learn['stage']}"):
        learn["stage"] += 1
        learn["watch_i"] = 0
        students.update_lesson(sid, lesson["id"], stage=learn["stage"])
        st.rerun()


# ============================================================================ stages
def _understand(lesson: dict, students, tutor, sid: str) -> None:
    learn = _state()
    st.markdown(f"🎯 **Goal:** {lesson['goal']}")
    st.info(f"**Everyday picture.** {lesson['analogy']}", icon="💡")
    if lesson.get("real_life"):
        st.markdown("**🌍 Real-life examples**")
        for ex in lesson["real_life"]:
            st.markdown(f"- {ex}")
    st.markdown("---\n**Now the exact rule**")
    st.markdown(lesson["concept"])
    notes = tutor.class_notes_for(lesson)
    if notes:
        with st.expander("📒 What your class notes say"):
            for n in notes:
                body = n["text"].split(": ", 1)[1] if ": " in n["text"] else n["text"]
                st.markdown(f"**{n['meta'].get('section', '')}** · _{n['meta'].get('source', '')}_")
                st.markdown(body[:1200] + ("…" if len(body) > 1200 else ""))
    c = st.columns([1.3, 1, 2])
    if c[0].button("🔁 Explain it differently", key=f"alt_{lesson['id']}"):
        with st.spinner("Finding another way to explain it…"):
            reply, source = tutor.lesson_reply(lesson, students.overall_level(sid))
            if isinstance(reply, str):
                learn["alt_text"] = reply
            else:
                learn["alt_text"] = None
                learn["alt_stream"] = reply
        learn["alt_source"] = source
    if learn.get("alt_stream") is not None:
        with st.container(border=True):
            st.caption(f"Another way to see it · {learn['alt_source']}")
            learn["alt_text"] = st.write_stream(learn.pop("alt_stream"))
    elif learn.get("alt_text"):
        with st.container(border=True):
            st.caption(f"Another way to see it · {learn['alt_source']}")
            st.markdown(learn["alt_text"])
    with st.expander("❓ Ask a question about this lesson"):
        for m in learn["qa"]:
            st.markdown(("**You:** " if m["role"] == "user" else "**Tutor:** ") + m["content"])
        q = st.text_input("Your question", key=f"lq_{lesson['id']}_{len(learn['qa'])}",
                          placeholder="e.g. Why is SJF not used directly in real systems?")
        if q:
            reply, source = tutor.lesson_reply(lesson, students.overall_level(sid), q, learn["qa"])
            text = reply if isinstance(reply, str) else st.write_stream(reply)
            learn["qa"] += [{"role": "user", "content": q}, {"role": "assistant", "content": text}]
            st.rerun()


def _watch(lesson: dict) -> None:
    learn = _state()
    w = lesson["watch"]
    st.caption(w.get("intro", ""))
    if w["kind"] == "scheduling":
        prob = SchedulingProblem(w["algorithm"], 1, w["processes"], w.get("quantum"))
        res = prob.solve()
        steps = L.scheduling_steps(res)
        order = [p.pid for p in prob.processes]
        st.dataframe(ui.process_table(prob))
        if w.get("quantum"):
            st.caption(f"Time quantum q = {w['quantum']}")
        i = learn["watch_i"]
        done = i >= len(steps)
        if done:
            st.markdown(ui.gantt_html(res.gantt, order, title="Finished Gantt chart"), unsafe_allow_html=True)
            st.markdown("**Now the numbers** (TAT = CT − AT, WT = TAT − BT)")
            for line in L.results_breakdown(res):
                st.markdown(f"- {line}")
            st.caption(f"Average WT = {res.avg_wt:.2f} · average TAT = {res.avg_tat:.2f}")
        else:
            s = steps[i]
            st.markdown(ui.gantt_html(L.gantt_until(res.gantt, s["time"]), order,
                                      title=f"Gantt chart so far (decision {i + 1} of {len(steps)})",
                                      total_time=res.makespan), unsafe_allow_html=True)
            with st.container(border=True):
                st.markdown(f"**{s['event']}**")
                st.dataframe(_ready_df(s["ready"], w["algorithm"]))
                if s["queue"]:
                    st.caption("Ready queue (front → back): " + " → ".join(s["queue"]))
                st.success(f"**{s['answer']}** gets the CPU. {s['reason']}")
        c = st.columns([1, 1, 1, 2])
        if c[0].button("◀ Step", disabled=i == 0, key="w_prev"):
            learn["watch_i"] -= 1
            st.rerun()
        if c[1].button("Step ▶", disabled=done, key="w_next", type="primary"):
            learn["watch_i"] += 1
            st.rerun()
        if c[2].button("Show all", disabled=done, key="w_all"):
            learn["watch_i"] = len(steps)
            st.rerun()

    elif w["kind"] == "semaphore":
        steps = L.semaphore_steps(w["initial"], w["ops"])
        i = min(learn["watch_i"], len(steps))
        st.markdown(f"Initial value: **S = {w['initial']['S']}**")
        rows = []
        for k, s in enumerate(steps):
            shown = k < i
            rows.append({"#": k + 1, "Operation": f"{s['pid']}: {s['op']}(S)",
                         "S after": str(s["after"]) if shown else "", "What happens": s["effect"] if shown else "",
                         "Waiting queue": (", ".join(s["queue"]) or "—") if shown else ""})
        st.dataframe(pd.DataFrame(rows).set_index("#"))
        if 0 < i <= len(steps):
            s = steps[i - 1]
            sign = "−" if s["op"] == "wait" else "+"
            st.success(f"Step {i}: {s['pid']} calls {s['op']}(S). S = {s['before']} {sign} 1 = **{s['after']}**. {s['effect']}.")
        c = st.columns([1, 1, 3])
        if c[0].button("◀ Step", disabled=i == 0, key="ws_prev"):
            learn["watch_i"] -= 1
            st.rerun()
        if c[1].button("Step ▶", disabled=i >= len(steps), key="ws_next", type="primary"):
            learn["watch_i"] += 1
            st.rerun()
        if i >= len(steps):
            st.caption(f"Check: final S = {w['initial']['S']} − {sum(o['op'] == 'wait' for o in w['ops'])} waits + "
                       f"{sum(o['op'] == 'signal' for o in w['ops'])} signals = {steps[-1]['after']}.")

    elif w["kind"] == "bankers":
        res_names = w["resources"]
        procs = [f"P{k}" for k in range(len(w["maximum"]))]
        out = bankers.safety(w["available"], w["maximum"], w["allocation"])
        need = out["need"]
        tbl = pd.DataFrame({"Allocation": [" ".join(map(str, r)) for r in w["allocation"]],
                            "Max": [" ".join(map(str, r)) for r in w["maximum"]],
                            "Need = Max − Alloc": [" ".join(map(str, r)) for r in need]}, index=procs)
        st.dataframe(tbl)
        st.caption(f"Resources {', '.join(res_names)} · Available = {w['available']}")
        steps = out["steps"]
        i = min(learn["watch_i"], len(steps))
        finished = [s["process"] for s in steps[:i]]
        work = steps[i - 1]["work_after"] if i else w["available"]
        st.markdown(f"**Work = {work}** · finished so far: {', '.join(finished) or 'none'}")
        if i < len(steps):
            s = steps[i]
            cand = [f"P{k}" for k in range(len(procs)) if f"P{k}" not in finished]
            checks = []
            for p in cand:
                nd = need[int(p[1:])]
                ok = all(a <= b for a, b in zip(nd, work))
                checks.append(f"{p}: Need {nd} ≤ Work {work}? {'✅ yes' if ok else '❌ no'}")
            with st.container(border=True):
                st.markdown("**Which unfinished process can finish now?**")
                st.markdown("\n".join(f"- {c}" for c in checks))
                st.success(f"Choose **{s['process']}**. It finishes and returns its allocation "
                           f"{s['allocation_released']}: Work = {s['work_before']} + {s['allocation_released']} = {s['work_after']}.")
        else:
            st.success(f"Every process can finish, so the state is **safe**. Safe sequence: **{', '.join(out['sequence'])}**. "
                       f"Other orders can be safe too, as long as each pick has Need ≤ Work.")
        c = st.columns([1, 1, 3])
        if c[0].button("◀ Step", disabled=i == 0, key="wb_prev"):
            learn["watch_i"] -= 1
            st.rerun()
        if c[1].button("Step ▶", disabled=i >= len(steps), key="wb_next", type="primary"):
            learn["watch_i"] += 1
            st.rerun()

    else:  # slides
        slides = w["slides"]
        i = min(learn["watch_i"], len(slides) - 1)
        with st.container(border=True):
            st.markdown(f"#### {slides[i][0]}")
            st.markdown(slides[i][1])
            st.caption(f"Slide {i + 1} of {len(slides)}")
        c = st.columns([1, 1, 3])
        if c[0].button("◀ Slide", disabled=i == 0, key="wsl_prev"):
            learn["watch_i"] = i - 1
            st.rerun()
        if c[1].button("Slide ▶", disabled=i >= len(slides) - 1, key="wsl_next", type="primary"):
            learn["watch_i"] = i + 1
            st.rerun()


# ---------------------------------------------------------------------------- try it
def _new_try(lesson: dict) -> dict:
    t = lesson["try"]
    seed = random.randrange(10**9)
    if t["kind"] == "predict":
        prob = generator.generate_scheduling(t["algorithm"], t["difficulty"], seed)
        return {"kind": "predict", "problem": prob.to_dict(), "i": 0, "results": [], "answered": None}
    if t["kind"] == "metrics":
        prob = SchedulingProblem(t["algorithm"], 1, t["processes"])
        return {"kind": "metrics", "problem": prob.to_dict(), "analysis": None, "metrics": None}
    if t["kind"] == "semaphore":
        prob = generator.generate_semaphore(t["difficulty"], seed)
        return {"kind": "semaphore", "problem": prob.to_dict(), "i": 0, "results": [], "answered": None}
    prob = generator.generate_bankers(t["difficulty"], seed)
    return {"kind": "bankers", "problem": prob.to_dict(), "seq": [], "mistakes": 0, "msg": None}


def _try(lesson: dict, students, sid: str) -> None:
    learn = _state()
    st.caption(lesson["try"]["intro"])
    if learn.get("try") is None:
        learn["try"] = _new_try(lesson)
    tr = learn["try"]
    prob = generator.problem_from_dict(tr["problem"])

    if tr["kind"] == "predict":
        res = prob.solve()
        steps = [s for s in L.scheduling_steps(res) if len(s["options"]) > 1]
        order = [p.pid for p in prob.processes]
        st.dataframe(ui.process_table(prob))
        if prob.quantum:
            st.caption(f"Time quantum q = {prob.quantum}")
        i = tr["i"]
        if i < len(steps):
            s = steps[i]
            st.markdown(ui.gantt_html(L.gantt_until(res.gantt, s["time"]), order,
                                      title=f"Your chart so far · question {i + 1} of {len(steps)}",
                                      total_time=res.makespan), unsafe_allow_html=True)
            with st.container(border=True):
                st.markdown(f"**{s['event']}** {s['question']}")
                st.dataframe(_ready_df(s["ready"], prob.algorithm))
                if s["queue"]:
                    with st.expander("Peek at the ready queue (try tracking it yourself first)"):
                        st.write(" → ".join(s["queue"]))
                if tr["answered"] is None:
                    cols = st.columns(len(s["options"]))
                    for k, opt in enumerate(s["options"]):
                        if cols[k].button(opt, key=f"opt_{i}_{opt}"):
                            ok = opt == s["answer"]
                            tr["answered"] = {"choice": opt, "ok": ok}
                            tr["results"].append(ok)
                            st.rerun()
                else:
                    a = tr["answered"]
                    if a["ok"]:
                        st.success(f"Correct: **{s['answer']}**. {s['reason']}")
                    else:
                        st.error(f"You chose {a['choice']}, but **{s['answer']}** should have the CPU. {s['reason']}")
                    if st.button("Continue ▶", type="primary", key=f"cont_{i}"):
                        tr["i"] += 1
                        tr["answered"] = None
                        st.rerun()
        else:
            score = sum(tr["results"]) / len(tr["results"]) if tr["results"] else 1.0
            st.markdown(ui.gantt_html(res.gantt, order, title="Completed Gantt chart"), unsafe_allow_html=True)
            (st.success if score >= 0.8 else st.warning)(
                f"You got {sum(tr['results'])} of {len(tr['results'])} decisions right ({score:.0%}).")
            for line in L.results_breakdown(res):
                st.markdown(f"- {line}")
            pass  # guided practice is optional; scores come from the teach-back question
            if st.button("Try another problem", key="try_again"):
                learn["try"] = None
                st.rerun()

    elif tr["kind"] == "metrics":
        res = prob.solve()
        st.dataframe(ui.process_table(prob))
        st.markdown(ui.gantt_html(res.gantt, [p.pid for p in prob.processes], title="Finished Gantt chart"),
                    unsafe_allow_html=True)
        m0 = pd.DataFrame([{"Process": p.pid, "CT": None, "TAT": None, "WT": None} for p in prob.processes]
                          ).set_index("Process").astype("float")
        mdf = st.data_editor(m0, key=f"try_m_{tr['problem'].get('seed')}_{lesson['id']}",
                             column_config={k: st.column_config.NumberColumn(step=1) for k in ("CT", "TAT", "WT")})
        if st.button("Check my numbers", type="primary", key="try_check"):
            metrics = {pid: {k: (None if v != v else v) for k, v in row.items()} for pid, row in mdf.to_dict("index").items()}
            a = analyse_scheduling(prob, [(s.pid, s.start, s.end) for s in res.gantt], metrics)
            tr["analysis"], tr["metrics"] = a, metrics
            cells = [v for row in a["cells"].values() for v in row.values()]
            pass
            st.rerun()
        a = tr.get("analysis")
        if a:
            st.dataframe(ui.cells_table(prob, a["cells"], tr["metrics"]))
            if a["correct"]:
                st.success("All correct. You can read a Gantt chart and use both formulas.")
            for e in a["errors"]:
                if e["type"] == "missing_value":
                    st.warning("Some cells are empty.")
                    continue
                pids = ", ".join(sorted({d.get("pid") for d in e["details"] if d.get("pid")}))
                st.error(f"**{e['label']}** ({pids}). {e.get('misconception') or ''}")

    elif tr["kind"] == "semaphore":
        steps = L.semaphore_steps(prob.initial, prob.ops)
        i = tr["i"]
        st.markdown(f"Initial value: **{', '.join(f'{k} = {v}' for k, v in prob.initial.items())}**")
        done_rows = [{"#": k + 1, "Operation": f"{s['pid']}: {s['op']}({s['sem']})", "Value after": s["after"],
                      "What happened": s["effect"]} for k, s in enumerate(steps[:i])]
        if done_rows:
            st.dataframe(pd.DataFrame(done_rows).set_index("#"))
        if i < len(steps):
            s = steps[i]
            with st.container(border=True):
                st.markdown(f"**Step {i + 1}: {s['pid']} calls {s['op']}({s['sem']}).** {s['sem']} is currently **{s['before']}**"
                            + (f"; waiting: {', '.join(steps[i - 1]['queue'])}" if i and steps[i - 1]["queue"] else "") + ".")
                if tr["answered"] is None:
                    c = st.columns(2)
                    v = c[0].radio(f"New value of {s['sem']}", s["value_options"], index=None, key=f"sv_{i}")
                    o = c[1].radio("What happens?", s["outcomes"], index=None, key=f"so_{i}")
                    if st.button("Check", type="primary", key=f"sc_{i}", disabled=v is None or o is None):
                        ok = v == s["after"] and o == s["outcome"]
                        tr["answered"] = {"ok": ok, "v": v, "o": o}
                        tr["results"].append(ok)
                        st.rerun()
                else:
                    a = tr["answered"]
                    sign = "−" if s["op"] == "wait" else "+"
                    msg = f"{s['sem']} = {s['before']} {sign} 1 = {s['after']}; {s['outcome']}."
                    (st.success if a["ok"] else st.error)(("Correct. " if a["ok"] else f"Not quite (you said {a['v']}, {a['o']}). ") + msg)
                    if st.button("Continue ▶", type="primary", key=f"scont_{i}"):
                        tr["i"] += 1
                        tr["answered"] = None
                        st.rerun()
        else:
            score = sum(tr["results"]) / len(tr["results"])
            (st.success if score >= 0.8 else st.warning)(f"You got {sum(tr['results'])} of {len(tr['results'])} steps right ({score:.0%}).")
            pass
            if st.button("Try another sequence", key="try_again_s"):
                learn["try"] = None
                st.rerun()

    else:  # bankers: build a safe sequence
        need = bankers.compute_need(prob.maximum, prob.allocation)
        procs = [f"P{k}" for k in range(len(prob.maximum))]
        work = list(prob.available)
        for p in tr["seq"]:
            work = [a + b for a, b in zip(work, prob.allocation[int(p[1:])])]
        st.dataframe(pd.DataFrame({"Allocation": [" ".join(map(str, r)) for r in prob.allocation],
                                   "Need": [" ".join(map(str, r)) for r in need]}, index=procs))
        st.markdown(f"**Work = {work}** · sequence so far: {', '.join(tr['seq']) or '—'}")
        if tr.get("msg"):
            (st.success if tr["msg"][0] else st.error)(tr["msg"][1])
        left = [p for p in procs if p not in tr["seq"]]
        if left:
            st.markdown("**Which process can finish next?** (any valid choice is accepted)")
            cols = st.columns(len(left))
            for k, p in enumerate(left):
                if cols[k].button(p, key=f"bk_{len(tr['seq'])}_{p}"):
                    nd = need[int(p[1:])]
                    short = [prob.resources[r] for r, (a, b) in enumerate(zip(nd, work)) if a > b]
                    if short:
                        tr["mistakes"] += 1
                        tr["msg"] = (False, f"{p} needs {nd} but Work is only {work} (not enough {', '.join(short)}). "
                                            f"Pick a process whose Need fits in Work.")
                    else:
                        tr["seq"].append(p)
                        new = [a + b for a, b in zip(work, prob.allocation[int(p[1:])])]
                        tr["msg"] = (True, f"{p} can finish: Need {nd} ≤ Work {work}. It returns "
                                           f"{prob.allocation[int(p[1:])]}, so Work = {new}.")
                    st.rerun()
        else:
            score = len(procs) / (len(procs) + tr["mistakes"])
            st.success(f"Safe sequence found: **{', '.join(tr['seq'])}** ({tr['mistakes']} wrong picks).")
            pass
            if st.button("Try another state", key="try_again_b"):
                learn["try"] = None
                st.rerun()


def _check(lesson: dict, students, sid: str) -> None:
    learn = _state()
    answers = []
    for k, q in enumerate(lesson["mcq"]):
        st.markdown(f"**{k + 1}. {q['q']}**")
        opts = [o[0] for o in q["options"]]
        choice = st.radio(f"q{k}", opts, index=None, key=f"mcq_{lesson['id']}_{k}", label_visibility="collapsed")
        answers.append(choice)
        if learn["mcq_checked"] and choice is not None:
            text, ok, why = next(o for o in q["options"] if o[0] == choice)
            (st.success if ok else st.error)(why)
            if not ok:
                st.caption(f"Correct answer: {next(o[0] for o in q['options'] if o[1])}")
    if st.button("Check answers", type="primary", disabled=any(a is None for a in answers), key="mcq_check"):
        learn["mcq_checked"] = True
        right = sum(next(o[1] for o in q["options"] if o[0] == a) for q, a in zip(lesson["mcq"], answers))
        pass
        st.rerun()


# ---------------------------------------------------------------------------- explain it back
PROMPTS = ["What is this topic about, in one sentence?", "What exactly is the rule? How does it decide?",
           "Give an example, from real life or a small problem.", "What is a common mistake or trap?"]


def _explain_back(lesson: dict, students, tutor, sid: str) -> None:
    learn = _state()
    st.markdown(f"Now **you** teach it. Explain **{lesson['title']}** in your own words for about **one minute**, as if "
                "you were explaining it to a friend who missed the class. Don't look back at the notes.")
    st.caption("Helpful questions to talk through: " + " · ".join(PROMPTS))
    tkey = f"tb_text_{lesson['id']}"
    audio = st.audio_input("🎙️ Record your explanation (about 1 minute)", key=f"tb_audio_{lesson['id']}")
    if audio is not None:
        data = audio.getvalue()
        sig = hash(data)
        if learn.get("tb_audio_sig") != sig:
            if speech.available():
                with st.spinner("Converting your voice to text…"):
                    try:
                        ss[tkey] = speech.transcribe(data)
                        learn["tb_audio_sig"] = sig
                    except Exception as e:  # model download or audio problem
                        st.error(f"Speech-to-text failed ({e}). You can type or dictate in the box instead.")
            else:
                st.warning("In-app speech-to-text needs `pip install faster-whisper`. Meanwhile, click in the box below "
                           "and use voice typing (Windows: **Win + H**).")
    text = st.text_area("Your explanation (edit if the speech-to-text misheard something)", key=tkey, height=170,
                        placeholder="Speak with the mic above, use voice typing (Win + H), or type here…")
    words = len((text or "").split())
    target = 120
    st.progress(min(1.0, words / target), text=f"{words} words · about {target} words is one minute of speaking")
    if st.button("🧠 Check my understanding", type="primary", disabled=words < 15, key="tb_assess"):
        with st.spinner("Listening for the key ideas…"):
            a = TB.assess(lesson, text, tutor.client if tutor.llm_online else None)
        row = students.record_teachback(sid, lesson["id"], text, a)
        learn["tb"] = {"transcript": text, "assessment": a, "row": row, "questions": [], "current": None}
        students.update_lesson(sid, lesson["id"], check_score=a["score"])
        st.rerun()
    tb = learn.get("tb")
    if tb:
        a = tb["assessment"]
        n_clear = sum(v == "clear" for v in a["ideas"].values())
        if n_clear:
            st.success(f"Thanks! You clearly covered **{n_clear} of {len(a['ideas'])}** key ideas. "
                       "Next, one question to check the idea that needs the most work.")
        else:
            st.info("Thanks for explaining. The key ideas didn't come through clearly yet, which is normal on a first "
                    "try. Next, a question to work on the most important one.")
        if a.get("did_well"):
            st.caption(f"What you explained well: {a['did_well']}")
        st.caption(f"Assessed by: {a['source']}")


def _ensure_assessment(lesson: dict) -> dict | None:
    learn = _state()
    if learn.get("tb"):
        return learn["tb"]
    st.info("Explain the topic first in the previous step; the question is chosen from what you said.")
    if st.button("Skip and just give me a question", key="tb_skip"):
        a = {"ideas": {i["id"]: "missing" for i in lesson["ideas"]}, "misconceptions": [], "source": "skipped",
             "words": 0, "score": 0.0}
        learn["tb"] = {"transcript": "", "assessment": a, "row": None, "questions": [], "current": None}
        st.rerun()
    return None


def _render_question(q: dict, key: str):
    """Show a teach-back question; returns the student's answer (or None until they answer)."""
    if q["kind"] == "mcq":
        st.markdown(f"**{q['q']}**")
        return st.radio("Answer", [o[0] for o in q["options"]], index=None, key=key, label_visibility="collapsed")
    prob = generator.problem_from_dict(q["problem"])
    if q["kind"] in ("decision", "metric"):
        res = prob.solve()
        st.dataframe(ui.process_table(prob))
        conv = f"{ALGORITHMS[prob.algorithm]}" + (f", q = {prob.quantum}" if prob.quantum else "")
        if q["kind"] == "decision":
            step = L.scheduling_steps(res)[q["step"]]
            st.markdown(ui.gantt_html(L.gantt_until(res.gantt, step["time"]), [p.pid for p in prob.processes],
                                      title=f"{conv} · chart so far", total_time=res.makespan), unsafe_allow_html=True)
            st.markdown(f"**{step['event']}** {step['question']}")
            st.dataframe(_ready_df(step["ready"], prob.algorithm))
            return st.radio("Answer", step["options"], index=None, key=key, horizontal=True, label_visibility="collapsed")
        st.markdown(ui.gantt_html(res.gantt, [p.pid for p in prob.processes], title=f"{conv} · finished Gantt chart"),
                    unsafe_allow_html=True)
        st.markdown(f"**What is the {q['field']} of {q['pid']}?**")
        return st.number_input("Answer", value=None, step=1, key=key, label_visibility="collapsed", placeholder="your answer")
    if q["kind"] == "semaphore":
        steps = L.semaphore_steps(prob.initial, prob.ops)
        k = q["step"]
        st.markdown(f"Initial value: **{', '.join(f'{a} = {b}' for a, b in prob.initial.items())}**")
        rows = [{"#": i + 1, "Operation": f"{s['pid']}: {s['op']}({s['sem']})",
                 "Value after": str(s["after"]) if i < k else ("?" if i == k else ""),
                 "Waiting queue": (", ".join(s["queue"]) or "—") if i < k else ""} for i, s in enumerate(steps[:k + 1])]
        st.dataframe(pd.DataFrame(rows).set_index("#"))
        s = steps[k]
        st.markdown(f"**Step {k + 1}: {s['pid']} calls {s['op']}({s['sem']}). What is the new value, and what happens?**")
        c = st.columns(2)
        v = c[0].radio("New value", s["value_options"], index=None, key=key + "_v")
        o = c[1].radio("What happens?", s["outcomes"], index=None, key=key + "_o")
        return None if v is None or o is None else (v, o)
    need = bankers.compute_need(prob.maximum, prob.allocation)
    procs = [f"P{i}" for i in range(len(need))]
    st.dataframe(pd.DataFrame({"Allocation": [" ".join(map(str, r)) for r in prob.allocation],
                               "Max": [" ".join(map(str, r)) for r in prob.maximum]}, index=procs))
    st.markdown(f"Available = **{prob.available}** (resources {', '.join(prob.resources)}). "
                "**Which process can finish FIRST in a safe sequence?** (work out Need yourself)")
    return st.radio("Answer", procs, index=None, key=key, horizontal=True, label_visibility="collapsed")


def _your_question(lesson: dict, students, sid: str) -> None:
    learn = _state()
    tb = _ensure_assessment(lesson)
    if not tb:
        return
    if tb["current"] is None:
        asked = [q["q"]["idea"] for q in tb["questions"]]
        idea, why = TB.target_idea(lesson, tb["assessment"], asked)
        tb["current"] = {"q": TB.make_question(lesson, idea), "why": why, "result": None}
    cur = tb["current"]
    idea = next(i for i in lesson["ideas"] if i["id"] == cur["q"]["idea"])
    rating = tb["assessment"]["ideas"][idea["id"]]
    if cur["why"] == "challenge":
        st.info("You explained every key idea clearly, so here is a challenge question.", icon="🏆")
    else:
        st.info(f"This question checks an idea that was **{'unclear' if rating == 'partial' else 'missing'}** "
                "in your explanation.", icon="🎯")
    qkey = f"tbq_{len(tb['questions'])}"
    with st.container(border=True):
        ans = _render_question(cur["q"], qkey)
    if cur["result"] is None:
        if st.button("Submit answer", type="primary", disabled=ans is None, key=qkey + "_submit"):
            cur["result"] = TB.check_answer(cur["q"], ans)
            cur["answer"] = ans if not isinstance(ans, tuple) else list(ans)
            st.rerun()
    else:
        r = cur["result"]
        (st.success if r["ok"] else st.error)(("Correct! " if r["ok"] else f"Not quite. Correct answer: **{r['correct']}**. ")
                                              + r["explanation"])
        st.markdown(f"**The idea behind it:** {idea['statement']}")
        done = [q for q in tb["questions"]] + [cur]
        c = st.columns([1.4, 3])
        if len(done) < 3 and c[0].button("Another question", key=qkey + "_more"):
            tb["questions"].append(cur)
            tb["current"] = None
            st.rerun()


def _all_results(tb: dict) -> list[dict]:
    out = []
    for q in tb["questions"] + ([tb["current"]] if tb.get("current") and tb["current"].get("result") else []):
        out.append({"idea": q["q"]["idea"], "ok": q["result"]["ok"], "explanation": q["result"]["explanation"],
                    "correct": q["result"]["correct"]})
    return out


def _pointers(lesson: dict, students, sid: str, start_practice) -> None:
    learn = _state()
    tb = learn.get("tb")
    if not tb:
        st.info("Do the **Explain it back** step and answer your question to get pointers.")
        return
    results = _all_results(tb)
    if tb.get("row"):
        students.update_teachback_questions(tb["row"], results)
    if results:
        students.update_lesson(sid, lesson["id"], try_score=sum(r["ok"] for r in results) / len(results))
    students.update_lesson(sid, lesson["id"], completed=1)
    p = TB.pointers(lesson, tb["assessment"], results)
    icon = {"Strong understanding": "🌟", "Good start, a few gaps": "👍", "Needs another look": "🔁"}[p["verdict"]]
    st.markdown(f"### {icon} {p['verdict']}")
    c = st.columns(2)
    with c[0]:
        st.markdown("**✅ You explained well**")
        for x in p["clear"] or ["Keep going: try to state the rule in your own words next time."]:
            st.markdown(f"- {x}")
    with c[1]:
        st.markdown("**➕ Add this to your explanation**")
        for x in (p["partial"] + p["missing"]) or ["Nothing missing. Well done!"]:
            st.markdown(f"- {x}")
    if p["misconceptions"]:
        st.error("**Misconception to fix:** " + "; ".join(p["misconceptions"]))
    if results:
        st.markdown("**Your question" + ("s" if len(results) > 1 else "") + "**")
        for r in results:
            st.markdown(f"- {'✅' if r['ok'] else '❌'} {r['explanation']}")
    st.markdown("**Remember:** " + " · ".join(lesson["summary"]))
    st.divider()
    st.markdown("**What next?**")
    b = st.columns(3)
    topic = lesson.get("practice_topic")
    if topic and b[0].button("📝 Practise now", type="primary" if p["next"] == "practice" else "secondary", key="pt_practice"):
        start_practice(topic, f"Just finished the {lesson['title']} lesson → starting easy.")
        st.rerun()
    if b[1].button("🔁 Re-watch the example", type="primary" if p["next"] == "rewatch" else "secondary", key="pt_rewatch"):
        learn["stage"] = 1
        learn["watch_i"] = 0
        st.rerun()
    if b[2].button("🎙️ Explain it again", key="pt_again"):
        learn["stage"] = 2
        learn["tb"] = None
        st.rerun()
    if lesson.get("try"):
        with st.expander("🧩 Guided practice: solve a new problem step by step",
                         expanded=p["next"] == "guided"):
            _try(lesson, students, sid)
    with st.expander("📝 Quick quiz on this lesson"):
        _check(lesson, students, sid)
    nxt_i = L.ORDER.index(lesson["id"]) + 1
    if nxt_i < len(L.ORDER) and st.button("Next lesson ▶", key="pt_next"):
        _open_lesson(L.ORDER[nxt_i], students, sid)
        st.rerun()


# ============================================================================ main
def render(students, tutor, sid: str, start_practice) -> None:
    learn = _state()
    progress = students.lesson_progress(sid)
    rec = recommended_lesson(progress, students.recurring_errors(sid))
    left, right = st.columns([1, 2.8])
    with left:
        done = sum(1 for lid in L.ORDER if progress.get(lid, {}).get("completed"))
        st.progress(done / len(L.ORDER), text=f"{done} of {len(L.ORDER)} lessons done")
        group = None
        for l in L.LESSONS:
            if l["group"] != group:
                group = l["group"]
                st.caption(group.upper())
            p = progress.get(l["id"], {})
            icon = "✅" if p.get("completed") else ("👉" if l["id"] == rec else ("◐" if p else "○"))
            if st.button(f"{icon} {SHORT.get(l['id'], l['title'])}", key=f"pick_{l['id']}", width="stretch",
                         type="primary" if learn.get("lesson") == l["id"] else "secondary"):
                _open_lesson(l["id"], students, sid)
                st.rerun()
    with right:
        if not learn.get("lesson"):
            lr = L.LESSON_BY_ID[rec]
            st.subheader("Learn a topic from scratch")
            st.markdown("Each lesson takes about 10 minutes and has five steps:\n\n"
                        "1. **Understand**: real-life examples first, then the exact rule\n"
                        "2. **Watch**: a worked example, one decision at a time, with the reason\n"
                        "3. **Explain it back**: you explain the topic for a minute (speak or type)\n"
                        "4. **Your question**: one question on the idea you need most\n"
                        "5. **Pointers**: what you got right, what to add, then practice")
            st.info(f"👉 Suggested next: **{lr['title']}** · {lr['goal']}")
            if st.button(f"Start: {lr['title']}", type="primary"):
                _open_lesson(rec, students, sid)
                st.rerun()
            return
        lesson = L.LESSON_BY_ID[learn["lesson"]]
        names = L.stages_for(lesson)
        st.subheader(lesson["title"])
        _stage_bar(lesson, learn["stage"])
        stage = names[learn["stage"]]
        if stage == "Understand":
            _understand(lesson, students, tutor, sid)
        elif stage == "Watch":
            _watch(lesson)
        elif stage == "Explain it back":
            _explain_back(lesson, students, tutor, sid)
        elif stage == "Your question":
            _your_question(lesson, students, sid)
        else:
            _pointers(lesson, students, sid, start_practice)
        st.divider()
        _nav(lesson, students, sid, {"Your question": "Pointers ▶"}.get(stage, "Next ▶"))
