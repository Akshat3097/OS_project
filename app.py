"""
Adaptive OS Tutor — Streamlit front end.

Run:  streamlit run app.py
"""
from __future__ import annotations

import time
import uuid

import altair as alt
import pandas as pd
import streamlit as st

import config
import learn_ui
import ui
from engine import bankers, generator, question_bank, scheduling, semaphore
from engine.advanced import performance
from engine.scheduling import ALGORITHMS, Process
from rag.store import KnowledgeBase
from tutor.error_analysis import parse_gantt
from tutor.llm import OllamaClient
from tutor.student_model import SKILLS, TOPIC_NAMES, TOPICS, StudentModel
from tutor.tutor import Tutor

st.set_page_config(page_title="Adaptive OS Tutor", page_icon="🖥️", layout="wide")
ss = st.session_state


@st.cache_resource
def get_students() -> StudentModel:
    return StudentModel()


@st.cache_resource
def get_kb() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.load_or_build()
    return kb


students = get_students()
kb = get_kb()

# ============================================================================ sidebar
with st.sidebar:
    st.title("🖥️ Adaptive OS Tutor")
    st.caption("BCSE303P · Llama 3.1 + RAG + OS Engine + student model")
    sid = st.text_input("Student name", value=ss.get("sid", "demo")).strip() or "demo"
    ss.sid = sid

    st.subheader("Language model")
    probe = OllamaClient()
    models = probe.list_models()
    online = bool(models) or probe.available()
    if online:
        chat_models = [m for m in models if "embed" not in m] or models
        default = next((m for m in chat_models if m.startswith(config.DEFAULT_MODEL)), chat_models[0] if chat_models else config.DEFAULT_MODEL)
        model = st.selectbox("Model (Ollama)", chat_models, index=chat_models.index(default) if default in chat_models else 0)
        st.success(f"Ollama online · {model}", icon="✅")
    else:
        model = config.DEFAULT_MODEL
        st.warning("Ollama not reachable. The tutor still works using template feedback. Start it with `ollama serve`.",
                   icon="⚠️")
    use_llm = st.toggle("Use the LLM for feedback", value=online, disabled=not online)
    client = OllamaClient(model=model) if online else None
    tutor = Tutor(students, kb, client)

    st.subheader("Knowledge base (RAG)")
    st.caption(f"{len(kb.chunks)} chunks · {kb.mode}")
    c1, c2 = st.columns(2)
    if c1.button("Rebuild", help="Re-read rag/knowledge and rag/sources"):
        kb.build()
        st.rerun()
    has_embedder = any(config.EMBED_MODEL in m for m in models)
    if c2.button("+ Embeddings", disabled=not has_embedder,
                 help=f"Needs `ollama pull {config.EMBED_MODEL}`"):
        with st.spinner("Embedding chunks…"):
            kb.build(client=client, embed=True)
        st.rerun()

    st.divider()
    if st.button("Reset my progress", type="secondary"):
        students.reset(sid)
        ss.prac = None
        st.rerun()

TAB_NAMES = ["📘 Learn", "📝 Practice", "💬 Ask the tutor", "⚙️ OS Engine", "📈 My progress", "🏗️ How it works"]
if "_goto_tab" in ss:                       # set by "Practise now" in a lesson
    ss["main_tabs"] = ss.pop("_goto_tab")
tab_learn, tab_practice, tab_ask, tab_engine, tab_progress, tab_how = st.tabs(TAB_NAMES, key="main_tabs", on_change="rerun")


# ============================================================================ practice helpers
def new_problem(topic: str, difficulty: int, reason: str | None) -> None:
    if topic in ("PAST_PAPERS", "NOTES_EXAMPLES"):
        got = question_bank.random_problem(source="papers" if topic == "PAST_PAPERS" else "notes")
        prob, item = got
        reason = (f"📄 Past paper question · " if topic == "PAST_PAPERS" else "📒 Worked example from your class notes · ") + \
            f"{item.get('paper', item.get('source', ''))} {item.get('question', '')}"
    elif topic == "BANKERS":
        prob = generator.generate_bankers(difficulty)
    elif topic == "SEMAPHORE":
        prob = generator.generate_semaphore(difficulty)
    else:
        prob = generator.generate_scheduling(topic, difficulty)
    ss.prac = {"problem": prob.to_dict(), "pid": uuid.uuid4().hex[:10], "started": time.time(), "attempts": 0,
               "hints": 0, "revealed": False, "analysis": None, "feed": [], "reason": reason, "ver": 0,
               "prefill": None, "solved": False, "show_solution": False, "last_segments": None, "last_metrics": None,
               "bank_item": item if topic in ("PAST_PAPERS", "NOTES_EXAMPLES") else None}


def add_feedback(strat, kind: str, extra: dict | None = None) -> None:
    with st.spinner("Tutor is thinking…"):
        fb = tutor.feedback(strat, use_llm=use_llm)
    ss.prac["feed"].append({"kind": kind, "strategy": strat.to_dict(), **fb, **(extra or {})})


def blank_gantt(n: int) -> pd.DataFrame:
    return pd.DataFrame({"Process": pd.Series([None] * n, dtype="object"),
                         "Start": pd.Series([None] * n, dtype="float"),
                         "End": pd.Series([None] * n, dtype="float")})


def _nn(v):
    return None if v is None or (isinstance(v, float) and v != v) else v


def start_practice(topic: str, reason: str) -> None:
    new_problem(topic, 1, reason)
    ss["_goto_tab"] = TAB_NAMES[1]


# ============================================================================ learn tab
with tab_learn:
    learn_ui.render(students, tutor, sid, start_practice)


# ============================================================================ practice tab
with tab_practice:
    top = st.columns([2.2, 1.2, 1, 1.2])
    bank = question_bank.load()
    bank_opts = (["PAST_PAPERS"] if any(not question_bank.is_notes_example(i) for i in bank) else []) + \
                (["NOTES_EXAMPLES"] if any(question_bank.is_notes_example(i) for i in bank) else [])
    choice = top[0].selectbox("Topic", ["ADAPTIVE"] + TOPICS + bank_opts,
                              format_func=lambda t: "🎯 Adaptive (tutor chooses)" if t == "ADAPTIVE" else
                              "📄 Past paper questions" if t == "PAST_PAPERS" else
                              "📒 Class-notes examples" if t == "NOTES_EXAMPLES" else TOPIC_NAMES[t])
    diff_choice = top[1].selectbox("Difficulty", [0, 1, 2, 3],
                                   format_func=lambda d: "Auto" if d == 0 else generator.DIFFICULTY_NAMES[d])
    top[2].write("")
    top[2].write("")
    if top[2].button("New problem", type="primary"):
        if choice == "ADAPTIVE":
            rec = students.recommend_next(sid)
            d = diff_choice or rec["difficulty"]
            new_problem(rec["topic"], d, rec["reason"])
        elif choice in ("PAST_PAPERS", "NOTES_EXAMPLES"):
            new_problem(choice, 2, None)
        else:
            d, why = students.difficulty_for(sid, choice) if diff_choice == 0 else (diff_choice, "chosen manually")
            new_problem(choice, d, f"{TOPIC_NAMES[choice]} · {why}")
        st.rerun()

    prac = ss.get("prac")
    if not prac:
        st.info("Press **New problem** to start. In *Adaptive* mode the tutor picks the topic and difficulty "
                "from your learning profile and tells you why.")
    else:
        problem = generator.problem_from_dict(prac["problem"])
        kind = problem.kind
        topic = problem.algorithm if kind == "scheduling" else kind.upper()
        head = st.columns([3, 1])
        head[0].subheader(f"{TOPIC_NAMES.get(topic, topic)} · {generator.DIFFICULTY_NAMES.get(problem.difficulty, '')}")
        head[1].caption(f"Attempts: {prac['attempts']} · Hints: {prac['hints']}")
        if prac["reason"]:
            st.caption(f"🎯 Why this problem: {prac['reason']}")
        lesson_for = {"FCFS": "fcfs", "SJF": "sjf", "SRTF": "srtf", "RR": "rr", "PRIORITY_NP": "priority",
                      "PRIORITY_P": "priority", "BANKERS": "bankers", "SEMAPHORE": "semaphores"}.get(topic)
        if lesson_for and not students.lesson_progress(sid).get(lesson_for, {}).get("completed"):
            st.info("New to this topic? The **📘 Learn** tab teaches it step by step before you practise.", icon="📘")
        bank_item = prac.get("bank_item")
        if bank_item:
            st.markdown(f"**📄 {bank_item.get('paper', '')} · {bank_item.get('question', '')}"
                        + (f" · {bank_item['marks']} marks" if bank_item.get("marks") else "") + f"**  \n{bank_item.get('text', '')}")
        st.write(problem.statement())

        answer: dict = {}
        ver = prac["ver"]
        pre = prac.get("prefill") or {}

        # ---------------------------------------------------------------- scheduling inputs
        if kind == "scheduling":
            left, right = st.columns([1, 1.4])
            with left:
                st.dataframe(ui.process_table(problem))
                conv = "Ties → earlier arrival, then list order."
                if topic in scheduling.PREEMPTIVE and topic != "RR":
                    conv += " Preempt only if strictly better."
                if topic == "RR":
                    conv += " New arrivals join the queue before the preempted process."
                st.caption(conv)
            with right:
                st.markdown("**Your Gantt chart** (one row per block; leave idle gaps out or write IDLE)")
                g0 = pd.DataFrame(pre["gantt"], columns=["Process", "Start", "End"]) if pre.get("gantt") \
                    else blank_gantt(len(problem.processes) + (2 if topic in scheduling.PREEMPTIVE else 0))
                gdf = st.data_editor(g0, key=f"g_{prac['pid']}_{ver}", num_rows="dynamic", hide_index=True,
                                     column_config={"Process": st.column_config.TextColumn(help="e.g. P1 or IDLE"),
                                                    "Start": st.column_config.NumberColumn(step=1, format="%d"),
                                                    "End": st.column_config.NumberColumn(step=1, format="%d")})
            rows = gdf.to_dict("records")
            segs, issues = parse_gantt(rows)
            seg_tuples = [(x.pid, x.start, x.end) for x in segs]
            hl = None
            if prac["analysis"] and prac["analysis"].get("divergence") and prac.get("last_segments") == seg_tuples:
                hl = prac["analysis"]["divergence"]["time"]
            st.markdown(ui.gantt_html(segs, [p.pid for p in problem.processes], hl, "Preview of your chart"),
                        unsafe_allow_html=True)
            for msg in issues:
                st.caption(f"⚠️ {msg}")
            st.markdown("**Completion, turnaround and waiting times**")
            m0 = pd.DataFrame(
                [{"Process": p.pid, **{k: _nn((pre.get("metrics") or {}).get(p.pid, {}).get(k)) for k in ("CT", "TAT", "WT")}}
                 for p in problem.processes]).set_index("Process").astype("float")
            mdf = st.data_editor(m0, key=f"m_{prac['pid']}_{ver}",
                                 column_config={k: st.column_config.NumberColumn(step=1) for k in ("CT", "TAT", "WT")})
            metrics = {pid: {k: _nn(r[k]) for k in ("CT", "TAT", "WT")} for pid, r in mdf.to_dict("index").items()}
            answer = {"gantt": rows, "metrics": metrics, "_segments": seg_tuples}

        # ---------------------------------------------------------------- banker's inputs
        elif kind == "bankers":
            res = problem.resources
            procs = [f"P{i}" for i in range(len(problem.maximum))]
            c = st.columns(3)
            c[0].markdown("**Allocation**")
            c[0].dataframe(pd.DataFrame(problem.allocation, columns=res, index=procs))
            c[1].markdown("**Max**")
            c[1].dataframe(pd.DataFrame(problem.maximum, columns=res, index=procs))
            c[2].markdown("**Available**")
            c[2].dataframe(pd.DataFrame([problem.available], columns=res, index=["Avail"]))
            c = st.columns([1.2, 1])
            with c[0]:
                st.markdown("**Your Need matrix**")
                n0 = pd.DataFrame(pre["need"] if pre.get("need") is not None else [[None] * len(res)] * len(procs),
                                  columns=res, index=procs).astype("float")
                ndf = st.data_editor(n0, key=f"n_{prac['pid']}_{ver}")
            with c[1]:
                safe_opts = ["Not answered", "Safe", "Unsafe"]
                pre_safe = {True: 1, False: 2}.get(pre.get("safe"), 0)
                verdict = st.radio("Is the state safe?", safe_opts, index=pre_safe, key=f"s_{prac['pid']}_{ver}",
                                   horizontal=True)
                seq = st.text_input("Safe sequence (comma separated)", value=pre.get("sequence", ""),
                                    key=f"q_{prac['pid']}_{ver}", placeholder="P1, P3, P4, P0, P2")
            need_vals = ndf.values.tolist()
            has_need = any(_nn(v) is not None for row in need_vals for v in row)
            answer = {"need": need_vals if has_need else None,
                      "safe": None if verdict == "Not answered" else verdict == "Safe",
                      "sequence": [s for s in seq.replace(";", ",").replace(" ", ",").split(",") if s.strip()]}

        # ---------------------------------------------------------------- exam-style inputs (I/O bursts, multilevel queues)
        elif kind == "advanced":
            rows = []
            for j in problem.jobs:
                r = {"Process": j.pid, "Arrival": f"{j.arrival:g}",
                     "Bursts": " → ".join(f"{'I/O' if k == 'IO' else 'CPU'} {v:g}" for k, v in j.bursts)}
                if problem.queues:
                    r["Queue"] = f"Q{j.queue}"
                if problem.algorithm and "PRIORITY" in problem.algorithm:
                    r["Priority"] = j.priority
                rows.append(r)
            st.dataframe(pd.DataFrame(rows).set_index("Process"))
            st.caption("Enter CT, TAT and WT for every process. For WT, either convention is accepted: "
                       "TAT − CPU − I/O, or TAT − CPU (I/O counted as waiting), as long as you are consistent.")
            m0 = pd.DataFrame([{"Process": j.pid, **{k: _nn((pre.get("metrics") or {}).get(j.pid, {}).get(k))
                                                     for k in ("CT", "TAT", "WT")}} for j in problem.jobs]
                              ).set_index("Process").astype("float")
            mdf = st.data_editor(m0, key=f"am_{prac['pid']}_{ver}",
                                 column_config={k: st.column_config.NumberColumn(step=0.1) for k in ("CT", "TAT", "WT")})
            answer = {"metrics": {pid: {k: _nn(r[k]) for k in ("CT", "TAT", "WT")} for pid, r in mdf.to_dict("index").items()}}

        # ---------------------------------------------------------------- semaphore inputs
        else:
            steps = pd.DataFrame([{"#": i + 1, "Process": o["pid"], "Operation": f"{o['op']}({o['sem']})"}
                                  for i, o in enumerate(problem.ops)]).set_index("#")
            c = st.columns([1, 1.2])
            c[0].dataframe(steps)
            with c[1]:
                finals = {}
                for s in problem.initial:
                    v = (pre.get("final") or {}).get(s)
                    finals[s] = st.number_input(f"Final value of {s}", value=v, step=1, key=f"f_{s}_{prac['pid']}_{ver}",
                                                placeholder="enter a number")
                blocked = st.multiselect("Blocked at the end", ["P1", "P2", "P3", "P4"], default=pre.get("blocked", []),
                                         key=f"b_{prac['pid']}_{ver}")
            answer = {"final": finals, "blocked": blocked}

        with st.expander("🎬 Demo shortcuts (fill a typical answer)"):
            presets = (ui.scheduling_presets(problem) if kind == "scheduling" else
                       ui.bankers_presets(problem) if kind == "bankers" else
                       ui.advanced_presets(problem) if kind == "advanced" else ui.semaphore_presets(problem))
            pc = st.columns([3, 1])
            pick = pc[0].selectbox("Preset", list(presets), label_visibility="collapsed")
            if pc[1].button("Fill"):
                prac["prefill"] = presets[pick]
                prac["ver"] += 1
                st.rerun()

        b = st.columns([1, 1, 1, 3])
        if b[0].button("✔ Submit", type="primary"):
            prac["attempts"] += 1
            out = tutor.submit(sid, problem, prac["pid"], answer, prac["attempts"], prac["hints"], prac["revealed"],
                               prac["started"])
            prac["analysis"] = out["analysis"]
            prac["last_segments"] = answer.get("_segments")
            prac["last_metrics"] = answer.get("metrics")
            if out["analysis"]["correct"]:
                prac["solved"] = True
            add_feedback(out["strategy"], "submission",
                         {"attempt": prac["attempts"], "changes": out["mastery_changes"],
                          "correct": out["analysis"]["correct"]})
            st.rerun()
        if b[1].button("💡 Hint"):
            prac["hints"] += 1
            strat = tutor.hint(sid, problem, prac["analysis"], prac["attempts"], prac["hints"])
            if strat.reveal and not prac["solved"]:
                prac["revealed"] = True
            add_feedback(strat, "hint", {"hint_no": prac["hints"]})
            st.rerun()
        if b[2].button("📖 Solution"):
            prac["show_solution"] = True
            prac["revealed"] = True
            st.rerun()

        # ---------------------------------------------------------------- results
        a = prac["analysis"]
        if a:
            st.divider()
            if a["correct"]:
                st.success("Verified correct by the OS Engine. 🎉")
            else:
                root = a.get("root_cause")
                cat = {"decision": "Scheduling decision error" if kind == "scheduling" else "Reasoning error",
                       "calculation": "Calculation error", "format": "Incomplete answer"}.get(root["category"] if root else "", "")
                st.error(f"**{cat}** — {root['label'] if root else 'Answer incomplete'}")
            cols = st.columns([1.3, 1])
            with cols[0]:
                if kind == "advanced" and a.get("metrics_given"):
                    st.markdown("**Cell-by-cell check**")
                    st.dataframe(ui.cells_table(problem, a["cells"], prac.get("last_metrics") or {}, pids=[j.pid for j in problem.jobs]))
                    if a.get("wt_modes"):
                        st.caption("Your waiting times " + " and ".join(a["wt_modes"]) + ".")
                if kind == "scheduling" and a.get("metrics_given"):
                    st.markdown("**Cell-by-cell check** (↪️ = wrong only because an earlier value was wrong — your formula is fine)")
                    st.dataframe(ui.cells_table(problem, a["cells"], prac.get("last_metrics") or {}))
                if kind == "semaphore" and a.get("semaphore_mode"):
                    other = {k: v for k, v in a["engine"]["final_values"].items()}
                    st.caption("Your values follow the **busy-waiting** definition from your Module 4 notes "
                               "(P(S): while (S <= 0); S--), so S never goes below 0. With the blocking definition "
                               f"(OSTEP / Theory slides) the values would be {other}. Both are accepted."
                               if a["semaphore_mode"] == "busy_wait" else
                               "Your values follow the **blocking** definition (OSTEP / Theory slides: the value can go "
                               "negative). With the busy-waiting P/V from your Module 4 notes the values would be "
                               f"{a.get('engine_busy_wait')}. Both are accepted.")
                if kind == "bankers" and a.get("sequence_check"):
                    sc = a["sequence_check"]
                    (st.success if sc["valid"] else st.warning)(f"Your sequence: {sc['message']}")
            with cols[1]:
                if a["errors"]:
                    st.markdown("**Error analysis**")
                    for e in a["errors"]:
                        if e["type"] == "missing_value":
                            continue
                        st.markdown(f"- **{e['label']}** · _{e['category']}_ ×{e['count']}"
                                    + (f"  \n  ↳ {e['misconception']}" if e.get("misconception") else ""))
                obs = a.get("observations", {})
                if obs:
                    st.caption("Skills evidenced: " + ", ".join(f"{SKILLS.get(k, k)} {'✓' if v else '✗'}" for k, v in obs.items()))

        for item in reversed(prac["feed"]):
            s = item["strategy"]
            with st.chat_message("assistant", avatar="🧑‍🏫"):
                label = (f"Attempt {item['attempt']}" if item["kind"] == "submission" else f"Hint {item.get('hint_no')}")
                st.caption(f"{label} · strategy **{s['action']}** · {item['source']}"
                           + (f" · {item['latency']:.1f}s" if item.get("latency") else ""))
                st.markdown(item["text"])
                if item.get("changes"):
                    st.caption("Mastery: " + " · ".join(f"{SKILLS.get(k, k)} {b0:.2f}→{b1:.2f}"
                                                        for k, (b0, b1) in item["changes"].items()))
                with st.expander("Why this response? (strategy, verified facts, guard)"):
                    st.markdown(f"**Rationale:** {s['rationale']}  \n**Reveal answer:** {'yes' if s['reveal'] else 'no'}"
                                f" · **Level:** {s['level']} · **Hint level:** {s['escalation']}")
                    st.markdown("**Facts given to the LLM (from the OS Engine):**")
                    st.code("\n".join(s["facts"]), language=None)
                    if item.get("issues"):
                        st.markdown("**Guard checks:**")
                        for i in item["issues"]:
                            st.markdown(f"- `{i['type']}` — {i['detail']}")
                    if item.get("llm_text") and item["llm_text"] != item["text"]:
                        st.markdown("**Blocked LLM reply:**")
                        st.code(item["llm_text"], language=None)
                    if item.get("notes"):
                        st.markdown("**Course notes retrieved (RAG):** " +
                                    "; ".join(f"{n['meta'].get('subtopic')} — {n['meta'].get('section', n['meta'].get('source'))}"
                                              for n in item["notes"]))
                    if item.get("error"):
                        st.caption(f"LLM error: {item['error']}")

        if prac["show_solution"]:
            st.divider()
            st.subheader("Full solution (OS Engine)")
            if kind == "scheduling":
                res = problem.solve()
                st.markdown(ui.gantt_html(res.gantt, [p.pid for p in problem.processes]), unsafe_allow_html=True)
                st.dataframe(ui.results_table(res))
                pf = performance(res.gantt, len(problem.processes))
                st.caption(f"Average TAT {res.avg_tat:.2f} · Average WT {res.avg_wt:.2f} · Average RT {res.avg_rt:.2f}  \n"
                           f"CPU utilisation {pf['cpu_utilization']:g}% · Throughput {pf['throughput']:.3g} processes/unit · "
                           f"Context switches {pf['context_switches']} (as counted in the Module 3 notes)")
                with st.expander("Step-by-step decisions"):
                    st.dataframe(ui.decisions_table(res), hide_index=True)
            elif kind == "advanced":
                res = problem.solve()
                st.markdown(ui.gantt_html(res.gantt, [j.pid for j in problem.jobs]), unsafe_allow_html=True)
                st.dataframe(pd.DataFrame([{"Process": r.pid, "AT": r.arrival, "CPU": r.cpu, "I/O": r.io, "CT": r.completion,
                                            "TAT": r.turnaround, "WT": r.waiting, "WT (I/O as waiting)": r.waiting_incl_io,
                                            "RT": r.response} for r in res.results.values()]).set_index("Process"))
                pf = performance(res.gantt, len(problem.jobs))
                st.caption(f"Average TAT {res.avg('turnaround'):.2f} · Average WT {res.avg('waiting'):.2f}"
                           + (f" (or {res.avg('waiting_incl_io'):.2f} counting I/O as waiting, as the Module 3 notes do)"
                              if problem.has_io() else "") + f" · Average RT {res.avg('response'):.2f}  \n"
                           f"CPU utilisation {pf['cpu_utilization']:g}% · Throughput {pf['throughput']:.3g} processes/unit · "
                           f"Context switches {pf['context_switches']}")
            elif kind == "bankers":
                eng = problem.solve()
                st.dataframe(pd.DataFrame(eng["need"], columns=problem.resources,
                                          index=[f"P{i}" for i in range(len(eng["need"]))]))
                st.write("**Safe**, sequence: " + ", ".join(eng["sequence"]) if eng["safe"]
                         else f"**Unsafe** — processes that can never finish: {', '.join(eng['stuck'])}")
                st.dataframe(pd.DataFrame(eng["steps"]), hide_index=True)
            else:
                eng = problem.solve()
                st.dataframe(pd.DataFrame([{k: v for k, v in s.items() if k != "queues"} for s in eng["steps"]]),
                             hide_index=True)
                busy_v = {k: max(0, v) for k, v in eng["final_values"].items()}
                st.write(f"Final values: {eng['final_values']} (blocking definition)"
                         + (f", {busy_v} (busy-waiting definition from the Module 4 notes)" if busy_v != eng["final_values"] else "")
                         + f" · Blocked: {', '.join(eng['blocked']) or 'none'}")
            if bank_item:
                chk = question_bank.check(bank_item)
                with st.container(border=True):
                    st.markdown("**📄 Official answer key**")
                    off = bank_item.get("official", {})
                    st.markdown(" · ".join(f"{k.replace('_', ' ')}: {v}" for k, v in off.items()))
                    status = {True: "✅ The OS Engine agrees with the key.", False: "⚠️ The OS Engine disagrees with part of the key.",
                              None: "No numbers to compare."}[chk["match"]]
                    st.markdown(status + (f"  \n_{bank_item['notes']}_" if bank_item.get("notes") else ""))


# ============================================================================ ask tab
with tab_ask:
    st.caption(f"Answers are grounded in the course knowledge base ({kb.mode}). Add your own notes and question "
               "papers to `rag/sources/` and press *Rebuild* in the sidebar.")
    ss.setdefault("qa", [])
    sugg = ["Why does SJF give the minimum average waiting time?", "What is the convoy effect?",
            "Explain the Banker's safety algorithm", "What does a negative semaphore value mean?"]
    sc = st.columns(len(sugg))
    clicked = None
    for i, q in enumerate(sugg):
        if sc[i].button(q, key=f"sugg{i}"):
            clicked = q
    for m in ss.qa:
        with st.chat_message(m["role"], avatar="🧑‍🏫" if m["role"] == "assistant" else None):
            st.markdown(m["content"])
            if m.get("sources"):
                st.caption("Sources: " + " · ".join(m["sources"]))
    q = st.chat_input("Ask about CPU scheduling or synchronization…") or clicked
    if q:
        with st.chat_message("user"):
            st.markdown(q)
        topic_level = students.overall_level(sid)
        with st.chat_message("assistant", avatar="🧑‍🏫"):
            reply, chunks = tutor.ask(q, topic_level, [m for m in ss.qa if m["role"] in ("user", "assistant")])
            if isinstance(reply, str):
                st.markdown(reply)
                text = reply
            else:
                text = st.write_stream(reply)
            srcs = [f"[{i}] {c['meta'].get('source')} — {c['meta'].get('subtopic')}"
                    + (f" p.{c['meta']['page']}" if c['meta'].get('page') else "") for i, c in enumerate(chunks, start=1)]
            st.caption("Sources: " + " · ".join(srcs))
        ss.qa += [{"role": "user", "content": q}, {"role": "assistant", "content": text, "sources": srcs}]


# ============================================================================ engine tab
with tab_engine:
    st.caption("The deterministic half of the system: every number the tutor uses comes from here, not from the LLM.")
    e1, e2, e3 = st.tabs(["CPU scheduling", "Banker's algorithm", "Semaphores"])
    with e1:
        default = pd.DataFrame([{"Process": "P1", "Arrival": 0, "Burst": 8, "Priority": 3},
                                {"Process": "P2", "Arrival": 1, "Burst": 4, "Priority": 1},
                                {"Process": "P3", "Arrival": 2, "Burst": 9, "Priority": 4},
                                {"Process": "P4", "Arrival": 3, "Burst": 5, "Priority": 2}])
        c = st.columns([1.3, 1])
        with c[0]:
            pdf = st.data_editor(default, num_rows="dynamic", hide_index=True, key="eng_procs")
        with c[1]:
            algos = st.multiselect("Algorithms", list(ALGORITHMS), default=["FCFS", "SJF", "SRTF", "RR"],
                                   format_func=lambda a: ALGORITHMS[a])
            q = st.number_input("Time quantum (RR)", 1, 20, 2)
        try:
            procs = [Process(str(r["Process"]).strip(), int(r["Arrival"]), int(r["Burst"]), int(_nn(r.get("Priority")) or 0))
                     for r in pdf.dropna(subset=["Process", "Arrival", "Burst"]).to_dict("records")]
            results = {a: scheduling.run(a, procs, q) for a in algos}
        except (ValueError, TypeError) as ex:
            st.error(str(ex))
            results = {}
        if results:
            comp = pd.DataFrame([{"Algorithm": a, "Avg WT": r.avg_wt, "Avg TAT": r.avg_tat, "Avg RT": r.avg_rt}
                                 for a, r in results.items()])
            perf_rows = {a: performance(r.gantt, len(procs)) for a, r in results.items()}
            st.altair_chart(alt.Chart(comp.melt("Algorithm", var_name="Metric", value_name="Time")).mark_bar().encode(
                x=alt.X("Algorithm:N", sort=algos), xOffset="Metric:N", y="Time:Q", color="Metric:N",
                tooltip=["Algorithm", "Metric", alt.Tooltip("Time:Q", format=".2f")]).properties(height=220))
            for a, r in results.items():
                st.markdown(ui.gantt_html(r.gantt, [p.pid for p in procs],
                                          title=f"{ALGORITHMS[a]}{f' (q={q})' if a == 'RR' else ''} · avg WT {r.avg_wt:.2f} · avg TAT {r.avg_tat:.2f}"),
                            unsafe_allow_html=True)
                pf = perf_rows[a]
                st.caption(f"CPU utilisation {pf['cpu_utilization']:g}% · throughput {pf['throughput']:.3g}/unit · "
                           f"context switches {pf['context_switches']}")
                with st.expander(f"{a}: table and decisions"):
                    st.dataframe(ui.results_table(r))
                    st.dataframe(ui.decisions_table(r), hide_index=True)
    with e2:
        st.caption("Default data: Silberschatz textbook example.")
        res = ["A", "B", "C"]
        procs_b = [f"P{i}" for i in range(5)]
        c = st.columns(3)
        alloc = c[0].data_editor(pd.DataFrame([[0, 1, 0], [2, 0, 0], [3, 0, 2], [2, 1, 1], [0, 0, 2]], columns=res, index=procs_b), key="b_alloc")
        mx = c[1].data_editor(pd.DataFrame([[7, 5, 3], [3, 2, 2], [9, 0, 2], [2, 2, 2], [4, 3, 3]], columns=res, index=procs_b), key="b_max")
        av = c[2].data_editor(pd.DataFrame([[3, 3, 2]], columns=res, index=["Avail"]), key="b_av")
        c[0].caption("Allocation")
        c[1].caption("Max")
        c[2].caption("Available")
        try:
            A, M, V = alloc.values.astype(int).tolist(), mx.values.astype(int).tolist(), av.values.astype(int).tolist()[0]
            out = bankers.safety(V, M, A)
            st.markdown("**Need = Max − Allocation**")
            st.dataframe(pd.DataFrame(out["need"], columns=res, index=procs_b))
            (st.success if out["safe"] else st.error)(
                f"Safe · sequence {', '.join(out['sequence'])}" if out["safe"] else f"Unsafe · stuck: {', '.join(out['stuck'])}")
            st.dataframe(pd.DataFrame(out["steps"]), hide_index=True)
            st.markdown("**Resource request**")
            rc = st.columns([1, 2, 1])
            who = rc[0].selectbox("Process", range(5), format_func=lambda i: f"P{i}")
            req = rc[1].text_input("Request vector", "1, 0, 2")
            if rc[2].button("Check request"):
                rv = [int(x) for x in req.replace(" ", "").split(",")]
                r = bankers.request(V, M, A, who, rv)
                (st.success if r["granted"] else st.warning)(r["message"])
        except ValueError as ex:
            st.error(str(ex))
    with e3:
        sc = st.columns([1, 2])
        init = sc[0].number_input("Initial value of S", -5, 10, 1)
        sem_style = sc[1].radio("Definition", ["blocking", "busy_wait"], horizontal=True,
                                format_func=lambda x: "Blocking (OSTEP: value can go negative)" if x == "blocking"
                                else "Busy-waiting (Module 4 notes: S ≥ 0)")
        ops_df = st.data_editor(pd.DataFrame([{"Process": "P1", "Op": "wait"}, {"Process": "P2", "Op": "wait"},
                                              {"Process": "P3", "Op": "wait"}, {"Process": "P1", "Op": "signal"}]),
                                num_rows="dynamic", hide_index=True, key="sem_ops",
                                column_config={"Op": st.column_config.SelectboxColumn(options=["wait", "signal"])})
        try:
            ops = [{"pid": r["Process"], "op": r["Op"], "sem": "S"} for r in ops_df.dropna().to_dict("records")]
            tr = semaphore.trace({"S": int(init)}, ops, sem_style)
            st.dataframe(pd.DataFrame([{"#": s["step"], "Operation": f"{s['pid']}: {s['op']}(S)", "S before": s["value_before"],
                                        "S after": s["value_after"], "Effect": s["effect"],
                                        ("Waiting queue" if sem_style == "blocking" else "Spinning"):
                                            ", ".join(s["queues"]["S"]) or "—"} for s in tr["steps"]]),
                         hide_index=True)
        except ValueError as ex:
            st.error(str(ex))


# ============================================================================ progress tab
with tab_progress:
    m = students.mastery(sid)
    hist = students.history(sid, 100)
    k = st.columns(4)
    k[0].metric("Submissions", len(hist))
    firsts = [h for h in hist if h["attempt_no"] == 1]
    k[1].metric("First-try accuracy", f"{100 * sum(h['correct'] for h in firsts) / len(firsts):.0f}%" if firsts else "—")
    k[2].metric("Hints used", sum(h["hints_used"] for h in firsts))
    rec = students.recommend_next(sid)
    short = {"PRIORITY_NP": "Priority NP", "PRIORITY_P": "Priority P", "BANKERS": "Banker's", "SEMAPHORE": "Semaphores"}
    k[3].metric("Next recommended", f"{short.get(rec['topic'], rec['topic'])} · {generator.DIFFICULTY_NAMES[rec['difficulty']]}")
    st.caption(f"🎯 {rec['reason']}")

    df = pd.DataFrame([{"Skill": v["name"], "Mastery": round(v["p_known"], 3), "Observations": v["n_obs"],
                        "Band": "easy" if v["p_known"] < config.MASTERY_THRESHOLDS[0] else
                        "medium" if v["p_known"] < config.MASTERY_THRESHOLDS[1] else "hard"} for v in m.values()])
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X("Mastery:Q", scale=alt.Scale(domain=[0, 1]), title="P(skill mastered) — Bayesian Knowledge Tracing"),
        y=alt.Y("Skill:N", sort=None, title=None, axis=alt.Axis(labelLimit=260)),
        opacity=alt.condition(alt.datum.Observations > 0, alt.value(1.0), alt.value(0.35)),
        color=alt.Color("Band:N", scale=alt.Scale(domain=["easy", "medium", "hard"], range=["#ef4444", "#f59e0b", "#10b981"]),
                        title="Next difficulty"),
        tooltip=["Skill", "Mastery", "Observations"])
    rules = alt.Chart(pd.DataFrame({"x": list(config.MASTERY_THRESHOLDS)})).mark_rule(strokeDash=[4, 4]).encode(x="x:Q")
    st.altair_chart((bars + rules).properties(height=330))
    st.caption("Faded bars = not practised yet (prior 0.25). Dashed lines = difficulty thresholds.")

    rec_err = students.recurring_errors(sid)
    if rec_err:
        st.markdown("**Recurring errors (possible misconceptions)**")
        for r in rec_err:
            st.markdown(f"- **{r['label']}** — in {r['count']} recent problems ({TOPIC_NAMES.get(r['topic'], r['topic'])})"
                        + (f"  \n  ↳ {r['misconception']}" if r.get("misconception") else ""))
    if hist:
        st.markdown("**Interaction log** (student interaction dataset)")
        st.dataframe(pd.DataFrame([{
            "When": time.strftime("%d %b %H:%M", time.localtime(h["ts"])), "Topic": TOPIC_NAMES.get(h["topic"], h["topic"]),
            "Difficulty": generator.DIFFICULTY_NAMES.get(h["difficulty"], h["difficulty"]), "Attempt": h["attempt_no"],
            "Correct": "✅" if h["correct"] else "❌", "Hints": h["hints_used"], "Time (s)": round(h["time_taken"] or 0),
            "Errors": ", ".join(h["error_types"])} for h in hist]), hide_index=True)


# ============================================================================ how it works tab
with tab_how:
    st.graphviz_chart("""
digraph G {
  rankdir=TB; node [shape=box, style="rounded,filled", fillcolor="#eef2ff", fontname="Helvetica", fontsize=11];
  S [label="Student", fillcolor="#fde68a"]; UI [label="Streamlit web UI"];
  ENG [label="OS Engine\\n(scheduling, Banker's, semaphores)\\nsolves + generates problems", fillcolor="#dcfce7"];
  EA [label="Error analysis\\nroot cause + misconception", fillcolor="#dcfce7"];
  SM [label="Student model\\nSQLite log + BKT mastery", fillcolor="#dcfce7"];
  TS [label="Teaching strategy\\nrules: hint ladder, worked example", fillcolor="#dcfce7"];
  RAG [label="RAG\\ncourse notes, BM25 + embeddings", fillcolor="#e0f2fe"];
  LLM [label="Llama 3.1 8B via Ollama\\n(+ QLoRA adapter, planned)", fillcolor="#e0f2fe"];
  G [label="Guard\\nblocks leaked answers", fillcolor="#fee2e2"];
  S -> UI -> ENG -> EA -> SM -> TS; RAG -> LLM; TS -> LLM [label=" facts + instruction"]; LLM -> G -> UI [label=" feedback"];
  SM -> UI [label=" next problem", style=dashed];
}""")
    st.markdown(f"""
| Component | Status | What it does |
|---|---|---|
| Learn mode | ✅ working | 10 lessons: real-life examples → worked example → explain it back (voice/text) → targeted question → pointers |
| Teach-back assessment | ✅ working | LLM judge (JSON) or keyword rubric rates each key idea and detects misconceptions; picks the next question |
| OS Engine | ✅ working | FCFS, SJF, SRTF, RR, Priority (both), I/O bursts, multilevel and multilevel feedback queues, Banker's (safety + request + detection), semaphore tracing (blocking and busy-waiting definitions), CPU utilisation / throughput / context switches |
| Problem generator | ✅ working | Unlimited problems at 3 difficulty levels with deliberate "traps" (ties, idle gaps, RR boundary arrivals) |
| Error analysis | ✅ working | 30+ error types; separates root causes from propagated errors; detects misconceptions by re-running wrong rules |
| Student model | ✅ working | Logs every interaction; Bayesian Knowledge Tracing per skill; recurring-error detection |
| Teaching strategy | ✅ working | Hint ladder, worked examples for recurring errors, algorithm contrast, formula reminders |
| RAG | ✅ working | Class notes (Modules 2–4, Theory and Extra slides), 8 OSTEP chapters, past-paper notes and seed notes ({len(kb.chunks)} chunks); BM25 + embeddings with rank fusion; the class notes are preferred and shown in Learn mode |
| Question bank | ✅ working | 20 questions from 9 VIT BCSE303L papers + 33 worked examples from the class notes; the engine reproduces every answer and flags 4 slips in the keys and 4 in the notes |
| LLM | ✅ base model via Ollama | Phrases feedback from verified facts; answer-leak guard |
| QLoRA fine-tuning | 🔜 pipeline ready | Dataset builder + Unsloth training script; next: curate data and train |
| Evaluation | 🔜 harness ready | Automatic leak/hallucination checks across model variants; pre/post test planned |
""")
