"""
OS Tutor: chat interface.

    streamlit run chat_app.py

One conversation: ask anything, paste a question from a paper, practise, take a quiz or explain a topic back.
The OS Engine, the class notes and the student model work behind the scenes (tutor/chat_agent.py), and
every number in a card comes from the engine. The classic tabbed app is still available: streamlit run app.py
"""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

import config
import ui
from engine import question_bank, scheduling
from engine.advanced import performance
from engine.generator import problem_from_dict
from engine.scheduling import ALGORITHMS, IDLE, Process
from rag.store import KnowledgeBase
from tutor.chat_agent import LESSON, ChatAgent
from tutor.chat_store import load_chat, new_chat, save_chat
from tutor.llm import OllamaClient
from tutor.student_model import SKILLS, StudentModel

st.set_page_config(page_title="OS Tutor", page_icon="🖥️", layout="centered")
ss = st.session_state
AVATAR = "🧑‍🏫"
PREFERRED_MODELS = ("os-tutor", "os-tutor-prompt", config.DEFAULT_MODEL)

st.html("""
<style>
  .block-container {max-width: 860px; padding-top: 3.6rem; padding-bottom: 6rem;}
  /* the student's messages: a soft bubble on the right, like a chat app */
  div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {
      flex-direction: row-reverse; width: fit-content; max-width: 82%; margin-left: auto;
      background: rgba(127,127,140,.12); border-radius: 18px; padding: .5rem 1rem !important;}
  div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) div[data-testid="stChatMessageAvatarUser"] {display: none;}
  div[data-testid="stChatMessage"] {background: transparent; padding-left: 0; padding-right: 0;}
  div[data-testid="stChatMessage"] button[kind="secondary"] {justify-content: flex-start;}
  div[data-testid="stChatMessage"] button[kind="secondary"] p {text-align: left;}
  div[data-testid="stChatMessage"] p {line-height: 1.6;}
  .os-meta {font-size: 12px; opacity: .55; margin-top: -.3rem;}
  .os-hero {font-size: 1.65rem; font-weight: 600; margin: .2rem 0 .1rem 0;}
  .os-sub {opacity: .65; margin-bottom: 1rem;}
  div[data-testid="stPills"] button {border-radius: 999px !important;}
</style>
""")


# ============================================================================ resources
@st.cache_resource
def get_students() -> StudentModel:
    return StudentModel()


@st.cache_resource
def get_kb() -> KnowledgeBase:
    kb = KnowledgeBase()
    kb.load_or_build()
    return kb


def send(text: str, structured: dict | None = None) -> None:
    ss.pending = (text, structured)


def _pick(key: str) -> None:
    if ss.get(key):
        send(ss[key])
    ss[key] = None


students = get_students()
kb = get_kb()

# ============================================================================ sidebar
with st.sidebar:
    st.markdown("### 🖥️ OS Tutor")
    st.caption("BCSE303 · CPU scheduling and process synchronization")
    sid = st.text_input("Your name", value=ss.get("sid", "demo")).strip() or "demo"
    if ss.get("sid") != sid or "chat" not in ss:
        ss.sid = sid
        ss.chat = load_chat(sid)
    if st.button("➕  New chat", width="stretch"):
        ss.chat = new_chat(sid)
        st.rerun()

    probe = OllamaClient()
    models = [m for m in probe.list_models() if "embed" not in m]
    online = bool(models)
    st.divider()
    if online:
        default = next((m for pref in PREFERRED_MODELS for m in models if m.split(":")[0] == pref.split(":")[0]), models[0])
        model = st.selectbox("Model", models, index=models.index(default),
                             help="os-tutor = fine-tuned with QLoRA · os-tutor-prompt = instructions only")
        use_llm = st.toggle("Use the language model", value=True)
    else:
        model, use_llm = config.DEFAULT_MODEL, False
        st.warning("Ollama isn't running, so replies use templates. Everything is still checked by the engine. "
                   "Start it with `ollama serve`.", icon="⚠️")
    show_meta = st.toggle("Show how each reply was made", value=False,
                          help="Route, strategy, the engine facts given to the model, and the guard's checks")
    st.divider()
    st.caption("**Try:** “explain SRTF like I'm new to it” · paste a question from a paper · “give me a hard "
               "Round Robin problem” · “quiz me on deadlocks” · “let me explain semaphores” · “how am I doing?”")
    st.caption(f"Notes: {len(kb.chunks)} chunks ({kb.mode}). Classic tabs: `streamlit run app.py`")

client = OllamaClient(model=model) if online else None
agent = ChatAgent(students, kb, client, use_llm=use_llm)
state = ss.chat
if not state["messages"]:
    state["messages"].append(agent.welcome(state))


# ============================================================================ cards
def _pids(problem) -> list[str]:
    return [j.pid for j in problem.jobs] if problem.kind == "advanced" else [p.pid for p in problem.processes]


def card_problem(card: dict) -> None:
    problem = problem_from_dict(card["problem"])
    item = card.get("bank_item")
    with st.container(border=True):
        if item:
            st.markdown(f"**📄 {item.get('paper', item.get('source', ''))} · {item.get('question', '')}**"
                        + (f" · {item['marks']} marks" if item.get("marks") else ""))
            if item.get("text"):
                st.markdown(item["text"])
        kind = problem.kind
        if kind == "scheduling":
            q = f" · q = {problem.quantum}" if problem.algorithm == "RR" else ""
            st.markdown(f"**{ALGORITHMS[problem.algorithm]}**{q}")
            st.dataframe(ui.process_table(problem), width="stretch")
            conv = "Ties go to the earlier arrival."
            if problem.algorithm in scheduling.USES_PRIORITY:
                conv += " Lower number = higher priority."
            if problem.algorithm in ("SRTF", "PRIORITY_P"):
                conv += " Preempt only if strictly better."
            if problem.algorithm == "RR":
                conv += " A process arriving when a slice ends joins the queue before the preempted one."
            st.caption(conv)
        elif kind == "advanced":
            if not item:
                st.markdown(problem.statement())
            st.dataframe(pd.DataFrame([{"Process": j.pid, "AT": j.arrival, "Priority": j.priority,
                                        "Bursts": " → ".join(f"{k} {v:g}" for k, v in j.bursts)} for j in problem.jobs])
                         .set_index("Process"), width="stretch")
            st.caption(problem.label)
        elif kind == "bankers":
            idx = [f"P{i}" for i in range(len(problem.allocation))]
            c = st.columns([1, 1, 1])
            c[0].markdown("**Allocation**")
            c[0].dataframe(pd.DataFrame(problem.allocation, columns=problem.resources, index=idx))
            c[1].markdown("**Max**")
            c[1].dataframe(pd.DataFrame(problem.maximum, columns=problem.resources, index=idx))
            c[2].markdown("**Available**")
            c[2].dataframe(pd.DataFrame([problem.available], columns=problem.resources, index=[""]))
            st.caption("Is the system in a safe state? If so, give a safe sequence.")
        else:
            st.markdown(problem.statement())


def card_solution(card: dict) -> None:
    problem = problem_from_dict(card["problem"])
    with st.container(border=True):
        st.markdown("**Solution from the OS Engine**")
        if problem.kind == "scheduling":
            res = problem.solve()
            st.html(ui.gantt_html(res.gantt, _pids(problem)))
            st.dataframe(ui.results_table(res), width="stretch")
            pf = performance(res.gantt, len(problem.processes))
            st.caption(f"Average TAT **{res.avg_tat:.2f}** · Average WT **{res.avg_wt:.2f}** · Average RT {res.avg_rt:.2f} · "
                       f"CPU utilisation {pf['cpu_utilization']:g}% · Context switches {pf['context_switches']}")
            with st.expander("Every decision, step by step"):
                st.dataframe(ui.decisions_table(res), hide_index=True, width="stretch")
        elif problem.kind == "advanced":
            res = problem.solve()
            st.html(ui.gantt_html(res.gantt, _pids(problem)))
            st.dataframe(pd.DataFrame([{"Process": r.pid, "AT": r.arrival, "CPU": r.cpu, "I/O": r.io, "CT": r.completion,
                                        "TAT": r.turnaround, "WT": r.waiting, "WT (I/O as waiting)": r.waiting_incl_io,
                                        "RT": r.response} for r in res.results.values()]).set_index("Process"),
                         width="stretch")
            st.caption(f"Average TAT {res.avg('turnaround'):.2f} · Average WT {res.avg('waiting'):.2f}"
                       + (f" (or {res.avg('waiting_incl_io'):.2f} counting I/O as waiting, as the Module 3 notes do)"
                          if problem.has_io() else ""))
        elif problem.kind == "bankers":
            eng = problem.solve()
            st.markdown("**Need = Max − Allocation**")
            st.dataframe(pd.DataFrame(eng["need"], columns=problem.resources,
                                      index=[f"P{i}" for i in range(len(eng["need"]))]))
            st.markdown("✅ **Safe** · sequence " + " → ".join(eng["sequence"]) if eng["safe"]
                        else f"⛔ **Unsafe** · these can never finish: {', '.join(eng['stuck'])}")
            st.dataframe(pd.DataFrame(eng["steps"]), hide_index=True, width="stretch")
        else:
            eng = problem.solve()
            st.dataframe(pd.DataFrame([{k: v for k, v in s.items() if k != "queues"} for s in eng["steps"]]),
                         hide_index=True, width="stretch")
            busy = {k: max(0, v) for k, v in eng["final_values"].items()}
            st.caption(f"Final values {eng['final_values']} (blocking definition)"
                       + (f", {busy} with the busy-waiting P/V from the Module 4 notes" if busy != eng["final_values"] else "")
                       + f" · Blocked: {', '.join(eng['blocked']) or 'none'}")
        item = card.get("bank_item")
        if item:
            chk = question_bank.check(item)
            off = item.get("official", {})
            st.caption("**Official answer key:** " + " · ".join(f"{k.replace('_', ' ')}: {v}" for k, v in off.items()))
            st.caption({True: "✅ The engine agrees with the key.", False: "⚠️ The engine disagrees with part of the key.",
                        None: ""}[chk["match"]] + (f" {item['notes']}" if item.get("notes") else ""))


def card_marked(card: dict) -> None:
    problem = problem_from_dict(card["problem"])
    a = card["analysis"]
    ans = card.get("answer") or {}
    with st.container(border=True):
        if a.get("correct"):
            st.markdown("✅ **Verified by the OS Engine**")
        else:
            root = a.get("root_cause")
            st.markdown(f"🔎 **First thing to fix:** {root['label']}" if root else "🔎 **Your answer isn't complete yet**")
        if problem.kind == "scheduling":
            if a.get("student_gantt"):
                hl = a["divergence"]["time"] if a.get("divergence") and not a.get("gantt_correct") else None
                st.html(ui.gantt_html(a["student_gantt"], _pids(problem), hl, "Your Gantt chart"))
            if a.get("metrics_given"):
                st.dataframe(ui.cells_table(problem, a.get("cells") or {}, ans.get("metrics") or {}),
                             width="stretch")
                st.caption("✅ right · ❌ wrong · ↪️ follows from an earlier value (your formula is fine) · — missing")
        elif problem.kind == "advanced" and a.get("cells"):
            st.dataframe(ui.cells_table(problem, a["cells"], ans.get("metrics") or {}, pids=_pids(problem)),
                         width="stretch")
        elif problem.kind == "bankers":
            if ans.get("safe") is not None:
                st.markdown(f"You said: **{'safe' if ans['safe'] else 'unsafe'}**"
                            + (f", sequence {' → '.join(ans['sequence'])}" if ans.get("sequence") else ""))
            sc = a.get("sequence_check")
            if sc:
                st.caption(("✅ " if sc["valid"] else "❌ ") + sc["message"])
        elif problem.kind == "semaphore":
            st.markdown("You said: " + ", ".join(f"{k} = {v}" for k, v in (ans.get("final") or {}).items())
                        + f" · blocked: {', '.join(ans.get('blocked') or []) or 'none'}")
        others = [e for e in a.get("errors", []) if e.get("type") != "missing_value"]
        if others and not a.get("correct"):
            st.caption("Mistakes found: " + "; ".join(f"{e['label']}" + (f" ×{e['count']}" if (e.get("count") or 1) > 1 else "")
                                                      for e in others))
        if card.get("changes"):
            st.caption("Mastery: " + " · ".join(f"{k} {b0:.0%} → {b1:.0%}" for k, (b0, b1) in card["changes"].items()))


def card_example(card: dict) -> None:
    lesson = LESSON[card["lesson"]]
    w = lesson["watch"]
    with st.container(border=True):
        st.markdown("**Worked example, solved by the OS Engine**")
        if card.get("intro"):
            st.caption(card["intro"])
        if w["kind"] == "scheduling":
            res = scheduling.run(w["algorithm"], w["processes"], w.get("quantum"))
            st.html(ui.gantt_html(res.gantt, [p.pid for p in w["processes"]]))
            st.dataframe(ui.results_table(res), width="stretch")
            st.caption(f"Average TAT {res.avg_tat:.2f} · Average WT {res.avg_wt:.2f}")
        elif w["kind"] == "bankers":
            from engine import bankers
            eng = bankers.safety(w["available"], w["maximum"], w["allocation"])
            idx = [f"P{i}" for i in range(len(w["allocation"]))]
            c = st.columns(3)
            for col, title, data in ((c[0], "Allocation", w["allocation"]), (c[1], "Max", w["maximum"]),
                                     (c[2], "Need", eng["need"])):
                col.markdown(f"**{title}**")
                col.dataframe(pd.DataFrame(data, columns=w["resources"], index=idx))
            st.caption(f"Available {w['available']} · " + ("safe sequence " + " → ".join(eng["sequence"]) if eng["safe"] else "unsafe"))
        elif w["kind"] == "semaphore":
            from engine import semaphore
            eng = semaphore.trace(w["initial"], w["ops"])
            st.dataframe(pd.DataFrame([{k: v for k, v in s.items() if k != "queues"} for s in eng["steps"]]),
                         hide_index=True, width="stretch")


def card_progress(card: dict) -> None:
    df = pd.DataFrame([{"Skill": s["name"], "Mastery": s["p"], "Problems": s["n"]} for s in card["skills"]])
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"Mastery": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent")})
    st.caption("Mastery is estimated with Bayesian Knowledge Tracing from your first attempts.")


def card_sources(card: dict) -> None:
    with st.expander(f"📒 {card.get('title', 'Sources')} ({len(card['items'])})"):
        for it in card["items"]:
            st.markdown(f"**[{it['n']}] {it['label']}**")
            st.caption(it["text"])


def card_quiz(card: dict, active: bool, idx: int) -> None:
    if not active:
        st.markdown("  \n".join(f"**{'ABCD'[k]}.** {o}" for k, o in enumerate(card["options"])))
        return
    for k, opt in enumerate(card["options"]):
        if st.button(f"{'ABCD'[k]}.  {opt}", key=f"quiz-{card['key']}-{k}", width="stretch"):
            send("ABCD"[k])
            st.rerun()


CARDS = {"problem": card_problem, "solution": card_solution, "marked": card_marked, "example": card_example,
         "progress": card_progress, "sources": card_sources}


def meta_details(m: dict) -> None:
    meta = m.get("meta") or {}
    bits = [meta.get("action", ""), f"routed by {meta['routed_by']}" if meta.get("routed_by") else "",
            meta.get("source", ""), f"{meta['latency']}s" if meta.get("latency") else ""]
    st.html(f"<div class='os-meta'>{' · '.join(b for b in bits if b)}</div>")
    if meta.get("facts") or meta.get("issues") or meta.get("blocked_text") or meta.get("error"):
        with st.expander("Behind the scenes"):
            if meta.get("strategy"):
                st.markdown(f"**Strategy:** {meta['strategy']} · reveal answer: {'yes' if meta.get('reveal') else 'no'}  \n"
                            f"{meta.get('rationale', '')}")
            if meta.get("facts"):
                st.markdown("**Facts given to the model (from the OS Engine)**")
                st.code("\n".join(meta["facts"]), language=None)
            for i in meta.get("issues") or []:
                st.markdown(f"- guard: `{i['type']}` {i['detail']}")
            if meta.get("blocked_text"):
                st.markdown("**Model reply that the guard replaced**")
                st.code(meta["blocked_text"], language=None)
            if meta.get("error"):
                st.caption(f"Error: {meta['error']}")


# ============================================================================ conversation
def render_message(i: int, m: dict, last: bool) -> None:
    if m["role"] == "user":
        with st.chat_message("user"):
            st.markdown(m["content"].replace("\n", "  \n"))
        return
    with st.chat_message("assistant", avatar=AVATAR):
        st.markdown(m["content"])
        for card in m.get("cards") or []:
            if card["type"] == "quiz":
                card_quiz(card, last and bool(state.get("quiz")), i)
            elif card["type"] in CARDS:
                CARDS[card["type"]](card)
        if show_meta and m.get("meta"):
            meta_details(m)
    if last and m.get("suggestions"):
        key = f"sugg-{i}"
        st.pills("Suggestions", m["suggestions"], key=key, on_change=_pick, args=(key,), label_visibility="collapsed")


def answer_form() -> None:
    ps = state.get("problem")
    if not ps or ps.get("solved") or ps.get("revealed") or state.get("quiz") or state.get("teachback"):
        return
    problem = problem_from_dict(ps["problem"])
    prev = ps.get("answer") or {}
    with st.expander("✏️ Answer sheet (or just type your answer in the chat)"):
        with st.form(f"form-{ps['pid']}-{len(state['messages'])}", border=False):
            if problem.kind == "scheduling":
                pids = _pids(problem)
                rows = prev.get("gantt") or [[None, None, None]] * (len(pids) + (2 if problem.algorithm in scheduling.PREEMPTIVE else 0))
                g = st.data_editor(pd.DataFrame(rows, columns=["Process", "Start", "End"]).astype({"Process": "object"}),
                                   num_rows="dynamic", hide_index=True, width="stretch",
                                   column_config={"Process": st.column_config.SelectboxColumn(options=pids + [IDLE]),
                                                  "Start": st.column_config.NumberColumn(step=1, format="%d"),
                                                  "End": st.column_config.NumberColumn(step=1, format="%d")})
                pm = prev.get("metrics") or {}
                mdf = st.data_editor(pd.DataFrame([{"Process": p, **{k: pm.get(p, {}).get(k) for k in ("CT", "TAT", "WT")}}
                                                   for p in pids]).set_index("Process").astype("float"),
                                     width="stretch")
                if st.form_submit_button("Check my answer", type="primary"):
                    gantt = [(r["Process"], r["Start"], r["End"]) for r in g.to_dict("records")
                             if r["Process"] and pd.notna(r["Start"]) and pd.notna(r["End"])]
                    metrics = {pid: {k: int(v) for k, v in row.items() if pd.notna(v)} for pid, row in mdf.to_dict("index").items()}
                    metrics = {k: v for k, v in metrics.items() if v}
                    parts = []
                    if gantt:
                        parts.append(", ".join(f"{p} {int(s)}-{int(e)}" for p, s, e in gantt))
                    if metrics:
                        parts.append("; ".join(f"{p}: " + ", ".join(f"{k} {v}" for k, v in row.items()) for p, row in metrics.items()))
                    send("My answer: " + ("\n".join(parts) or "(empty)"),
                         {"gantt": [(p, int(s), int(e)) for p, s, e in gantt], "metrics": metrics})
                    st.rerun()
            elif problem.kind == "bankers":
                safe = st.radio("Is the state safe?", ["Safe", "Unsafe"], horizontal=True)
                seq = st.text_input("Safe sequence", placeholder="P1, P3, P4, P0, P2")
                if st.form_submit_button("Check my answer", type="primary"):
                    pids = re.findall(r"(?i)P\s?\d+", seq)
                    send(f"My answer: {safe.lower()}" + (f", {seq}" if seq else ""),
                         {"safe": safe == "Safe", "sequence": [p.upper().replace(" ", "") for p in pids] or None, "need": None})
                    st.rerun()
            elif problem.kind == "semaphore":
                cols = st.columns(len(problem.initial))
                final = {s: cols[k].number_input(f"Final {s}", value=0, step=1) for k, s in enumerate(problem.initial)}
                procs = sorted({o["pid"] for o in problem.ops})
                blocked = st.multiselect("Blocked at the end", procs)
                if st.form_submit_button("Check my answer", type="primary"):
                    send("My answer: " + ", ".join(f"{k} = {v}" for k, v in final.items())
                         + f"; blocked: {', '.join(blocked) or 'none'}", {"final": final, "blocked": blocked})
                    st.rerun()
            else:
                pids = _pids(problem)
                pm = prev.get("metrics") or {}
                mdf = st.data_editor(pd.DataFrame([{"Process": p, **{k: pm.get(p, {}).get(k) for k in ("CT", "TAT", "WT")}}
                                                   for p in pids]).set_index("Process").astype("float"),
                                     width="stretch")
                if st.form_submit_button("Check my answer", type="primary"):
                    metrics = {pid: {k: float(v) for k, v in row.items() if pd.notna(v)} for pid, row in mdf.to_dict("index").items()}
                    send("My answer: " + "; ".join(f"{p}: " + ", ".join(f"{k} {v:g}" for k, v in row.items())
                                                   for p, row in metrics.items() if row), {"metrics": metrics})
                    st.rerun()


msgs = state["messages"]
if len(msgs) <= 1:
    st.html("<div class='os-hero'>What shall we work on?</div>"
            "<div class='os-sub'>Ask anything about CPU scheduling or process synchronization, paste a question "
            "from a paper, or pick a suggestion.</div>")
pending = ss.pop("pending", None)
for i, m in enumerate(msgs):
    render_message(i, m, last=(i == len(msgs) - 1) and pending is None)

prompt = st.chat_input("Ask anything, paste a question, or type your answer…")
if prompt:
    pending = (prompt, None)

if pending:
    text, structured = pending
    with st.chat_message("user"):
        st.markdown(text.replace("\n", "  \n"))
    with st.chat_message("assistant", avatar=AVATAR):
        with st.spinner("Thinking…"):
            reply = agent.respond(state, text, structured)
        if reply.stream is not None:
            st.write_stream(reply.chunks())
        else:
            st.markdown(reply.text)
    agent.commit(state, reply)
    save_chat(state)
    st.rerun()
else:
    answer_form()
