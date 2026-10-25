// Exam mode: a timed mock CAT paper from the OS Engine (server/exam.py). The page never sees the answers until it submits;
// the marking, the correct answers and the mastery changes come back together.
import { useCallback, useEffect, useRef, useState } from "react";
import { getJSON, storage, store } from "../api.js";
import { Tables } from "./Cards.jsx";
import Table from "./Table.jsx";
import Thinking from "./Thinking.jsx";

const post = (url, body) =>
  getJSON(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

function Clock({ left }) {
  const m = Math.max(0, Math.floor(left / 60)), s = Math.max(0, Math.floor(left % 60));
  return <span className={`clock${left < 300 ? " clock--low" : ""}`} role="timer" aria-live="off">{m}:{String(s).padStart(2, "0")}</span>;
}

function Grid({ rows, cols, value = {}, onChange, label }) {
  return (
    <table className="sheet-grid">
      <thead><tr><th />{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r}><th scope="row">{r}</th>
            {cols.map((c) => (
              <td key={c}><input type="number" aria-label={`${label} ${r} ${c}`} value={value[r]?.[c] ?? ""}
                                 onChange={(e) => onChange({ ...value, [r]: { ...(value[r] || {}), [c]: e.target.value } })} /></td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Choice({ options, value, onChange, name }) {
  return (
    <div className="options" role="radiogroup" aria-label={name}>
      {options.map(([v, label]) => (
        <button key={String(v)} role="radio" aria-checked={value === v} className={`option${value === v ? " is-picked" : ""}`}
                onClick={() => onChange(v)}>{label}</button>
      ))}
    </div>
  );
}

function Checks({ options, value = [], onChange, name }) {
  return (
    <div className="options" role="group" aria-label={name}>
      {options.map((o) => {
        const on = value.includes(o);
        return <button key={o} aria-pressed={on} className={`option${on ? " is-picked" : ""}`}
                       onClick={() => onChange(on ? value.filter((x) => x !== o) : [...value, o])}>{o}</button>;
      })}
    </div>
  );
}

function Paper({ paper, answers, setAnswers }) {
  const set = (k, v) => setAnswers({ ...answers, [k]: { ...(answers[k] || {}), ...v } });
  const [q1, q2, q3, q4, q5] = paper.questions;
  const a1 = answers.q1 || {}, a2 = answers.q2 || {}, a3 = answers.q3 || {}, a4 = answers.q4 || {}, a5 = answers.q5 || [];
  return (
    <div className="paper">
      <section className="card exam-q">
        <h3 className="card__title">Q1. CPU scheduling: {q1.title} <span className="marks">[{q1.marks} marks]</span></h3>
        <p>{q1.text}</p>
        <Table {...q1.table} small />
        <p className="card__note">{q1.note}</p>
        <label className="field">Gantt chart
          <input value={a1.gantt || ""} placeholder="e.g. P1 0-3, P2 3-5, idle 5-6, P3 6-9" onChange={(e) => set("q1", { gantt: e.target.value })} />
        </label>
        <Grid label="Q1" rows={q1.pids} cols={["CT", "TAT", "WT"]} value={a1.metrics} onChange={(m) => set("q1", { metrics: m })} />
        <label className="field field--short">Average waiting time
          <input type="number" step="0.01" value={a1.avg_wt ?? ""} onChange={(e) => set("q1", { avg_wt: e.target.value })} />
        </label>
      </section>

      <section className="card exam-q">
        <h3 className="card__title">Q2. {q2.title} <span className="marks">[{q2.marks} marks]</span></h3>
        <p>{q2.text}</p>
        <Tables tables={q2.tables} />
        <p>Available: <b>{q2.available}</b></p>
        <p className="table-label">Need</p>
        <Grid label="Need" rows={q2.pids} cols={q2.resources} value={a2.needGrid} onChange={(g) => set("q2", { needGrid: g })} />
        <p className="table-label">Is the system safe?</p>
        <Choice name="Safe or unsafe" options={[[true, "Safe"], [false, "Unsafe"]]} value={a2.safe} onChange={(v) => set("q2", { safe: v })} />
        {a2.safe !== false && (
          <label className="field">Safe sequence
            <input value={a2.sequence || ""} placeholder="e.g. P1, P3, P4, P0, P2" onChange={(e) => set("q2", { sequence: e.target.value })} />
          </label>
        )}
      </section>

      <section className="card exam-q">
        <h3 className="card__title">Q3. {q3.title} <span className="marks">[{q3.marks} marks]</span></h3>
        <p>{q3.text}</p>
        <p>Initial values: <b>{q3.initial.map(([k, v]) => `${k} = ${v}`).join(", ")}</b></p>
        <ol className="exam-ops">{q3.ops.map((o, k) => <li key={k}><code>{o}</code></li>)}</ol>
        <div className="sheet-inline">
          {q3.sems.map((s) => (
            <label key={s} className="field field--short">Final {s}
              <input type="number" value={a3.final?.[s] ?? ""} onChange={(e) => set("q3", { final: { ...(a3.final || {}), [s]: e.target.value } })} />
            </label>
          ))}
        </div>
        <p className="table-label">Blocked at the end (leave all off if nobody is blocked)</p>
        <Checks name="Blocked processes" options={q3.pids} value={a3.blocked} onChange={(v) => set("q3", { blocked: v })} />
      </section>

      <section className="card exam-q">
        <h3 className="card__title">Q4. {q4.title} <span className="marks">[{q4.marks} marks]</span></h3>
        <p>{q4.text}</p>
        <Tables tables={q4.tables} />
        <p>Available: <b>{q4.available}</b></p>
        <Choice name="Deadlocked or not" options={[[true, "Deadlocked"], [false, "No deadlock"]]} value={a4.deadlock} onChange={(v) => set("q4", { deadlock: v })} />
        {a4.deadlock === true && (
          <>
            <p className="table-label">Which processes are deadlocked?</p>
            <Checks name="Deadlocked processes" options={q4.pids} value={a4.deadlocked} onChange={(v) => set("q4", { deadlocked: v })} />
          </>
        )}
      </section>

      <section className="card exam-q">
        <h3 className="card__title">Q5. {q5.title} <span className="marks">[{q5.marks} marks]</span></h3>
        {q5.items.map((q, k) => (
          <div key={k} className="quiz-q">
            <p className="question__prompt">{String.fromCharCode(97 + k)}) {q.q}</p>
            <Choice name={`Question 5${String.fromCharCode(97 + k)}`} options={q.options.map((o) => [o, o])} value={a5[k]}
                    onChange={(v) => setAnswers({ ...answers, q5: q5.items.map((_, j) => (j === k ? v : a5[j] ?? null)) })} />
          </div>
        ))}
      </section>
    </div>
  );
}

function Results({ r, onAgain, onProgress }) {
  const pct = Math.round((r.total / r.out_of) * 100);
  return (
    <div className="results">
      <div className="score">
        <span className="score__big">{r.total}<small> / {r.out_of}</small></span>
        <span className="muted">{pct}% · {r.minutes_taken} minutes{r.late ? " (time ran out)" : ""}</span>
      </div>
      {r.mastery.length > 0 && (
        <div className="mastery">
          {r.mastery.map((m) => (
            <span key={m.skill} className={m.after >= m.before ? "up" : "down"}>{m.skill} {Math.round(m.before * 100)}% → {Math.round(m.after * 100)}%</span>
          ))}
        </div>
      )}
      {r.questions.map((q) => (
        <section key={q.n} className="card exam-q">
          <h3 className="card__title">Q{q.n}. {q.title} <span className="marks">{q.marks} / {q.parts.reduce((s, p) => s + p[2], 0)}</span></h3>
          <ul className="parts">
            {q.parts.map(([name, got, max]) => (
              <li key={name}><span>{name}</span><span className="bar" title={`${got} of ${max}`}><i style={{ width: `${(got / max) * 100}%` }} /></span><span>{got} / {max}</span></li>
            ))}
          </ul>
          {q.mistakes.length > 0 && <p className="verdict verdict--no">Mistakes found: {q.mistakes.join("; ")}</p>}
          {q.answer?.gantt && <p className="small"><b>Gantt chart:</b> {q.answer.gantt}</p>}
          {q.answer?.table && <Table {...q.answer.table} small />}
          {q.answer?.avg_wt && <p className="small"><b>Average WT:</b> {q.answer.avg_wt}</p>}
          {q.answer?.need && <Table {...q.answer.need} small label="Need" />}
          {q.answer?.verdict && <p className="small"><b>Answer:</b> {q.answer.verdict}</p>}
          {q.answer?.final && <p className="small"><b>Final values:</b> {q.answer.final}. <b>Blocked:</b> {q.answer.blocked}.</p>}
          {q.answer?.steps?.length > 0 && <details className="more"><summary>Detection steps</summary><ul className="breakdown">{q.answer.steps.map((s) => <li key={s}>{s}</li>)}</ul></details>}
          {q.items && (
            <ol className="mcq-results" type="a">
              {q.items.map((it, k) => (
                <li key={k}>
                  <p className="question__prompt">{it.q}</p>
                  <p className={it.ok ? "res-ok" : "res-no"}>{it.ok ? "✓ Right" : `✗ You chose: ${it.chosen ?? "nothing"}`}</p>
                  {!it.ok && <p className="small">Correct: {it.correct}</p>}
                  <p className="muted small">{it.why}</p>
                </li>
              ))}
            </ol>
          )}
        </section>
      ))}
      <div className="row-actions">
        <button className="primary" onClick={onAgain}>Try another paper</button>
        <button className="secondary" onClick={onProgress}>See your progress</button>
      </div>
    </div>
  );
}

export default function Exam({ sid, onProgress, scrollTop }) {
  const [paper, setPaper] = useState(null);
  const [answers, setAnswersState] = useState({});
  const [result, setResult] = useState(null);
  const [left, setLeft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const offset = useRef(0);                         // server clock − page clock
  const examKey = `exam:${sid}`;

  const setAnswers = (a) => { setAnswersState(a); store(`${examKey}:answers`, a); };
  const load = useCallback((p) => {
    offset.current = p.now - Date.now() / 1000;
    setPaper(p); setResult(p.result || null);
  }, []);

  useEffect(() => {                                 // resume a paper after a reload
    const id = storage(examKey, null);
    setPaper(null); setResult(null); setError(null);
    if (id) {
      setAnswersState(storage(`${examKey}:answers`, {}));
      getJSON(`/api/exam?id=${encodeURIComponent(id)}`).then(load).catch(() => store(examKey, null));
    }
  }, [examKey, load]);

  const submit = useCallback(async () => {
    if (!paper || busy) return;
    setBusy(true); setError(null);
    const q2 = answers.q2 || {};
    const need = q2.needGrid ? paper.questions[1].pids.map((p) => paper.questions[1].resources.map((r) => q2.needGrid[p]?.[r] ?? null)) : null;
    try {
      const r = await post("/api/exam/submit", { id: paper.id, answers: { ...answers, q2: { ...q2, need } } });
      setResult(r); scrollTop?.();
    } catch (e) { setError(e.message); }
    setBusy(false);
  }, [paper, answers, busy, scrollTop]);

  useEffect(() => {                                 // the clock; submits by itself when time is up
    if (!paper || result) return undefined;
    const tick = () => {
      const l = paper.started + paper.minutes * 60 - (Date.now() / 1000 + offset.current);
      setLeft(l);
      if (l <= 0) submit();
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [paper, result, submit]);

  const start = async () => {
    setBusy(true); setError(null);
    try {
      const p = await post("/api/exam/start", { sid });
      store(examKey, p.id); setAnswers({}); load(p); scrollTop?.();
    } catch (e) { setError(e.message); }
    setBusy(false);
  };
  const again = () => { store(examKey, null); setPaper(null); setResult(null); setAnswers({}); };

  if (!paper) {
    return (
      <div className="exam">
        <h1>Mock CAT paper</h1>
        <p className="hero__sub">A fresh paper every time, made and marked by the OS Engine. Your marks update your mastery on the Progress page.</p>
        <ol className="steps-explainer">
          {[["CPU scheduling", "Gantt chart and the CT / TAT / WT table", 10], ["Banker's algorithm", "Need, safe or not, a safe sequence", 6],
            ["Semaphores", "trace a sequence of wait and signal", 4], ["Deadlock detection", "who, if anyone, is deadlocked", 5],
            ["Concepts", "five multiple-choice questions", 5]].map(([t, d, m], k) => (
            <li key={t}><span className="steps-explainer__n">{k + 1}</span><b>{t}</b> <span>{d} · {m} marks</span></li>
          ))}
        </ol>
        <p className="muted">30 marks, 30 minutes. The paper is submitted for you when time runs out. Any valid safe sequence and either
          definition of wait/signal earns the marks; a value that follows correctly from an earlier slip gets half marks.</p>
        {error && <p className="error-text">{error}</p>}
        <button className="primary" disabled={busy} onClick={start}>{busy ? "Setting the paper…" : "Start the paper"}</button>
      </div>
    );
  }
  if (result) return <div className="exam"><h1>Your marks</h1><Results r={result} onAgain={again} onProgress={onProgress} /></div>;
  return (
    <div className="exam">
      <div className="exam-bar">
        <span><b>Mock CAT</b> · 30 marks</span>
        {left !== null && <Clock left={left} />}
        <button className="primary" disabled={busy} onClick={() => { if (window.confirm("Submit the paper now?")) submit(); }}>
          {busy ? "Marking…" : "Submit"}</button>
      </div>
      {error && <p className="error-text">{error}</p>}
      <Paper paper={paper} answers={answers} setAnswers={setAnswers} />
      <div className="row-actions"><button className="primary" disabled={busy} onClick={() => { if (window.confirm("Submit the paper now?")) submit(); }}>Submit the paper</button></div>
      {busy && <Thinking label="Marking your paper" />}
    </div>
  );
}
