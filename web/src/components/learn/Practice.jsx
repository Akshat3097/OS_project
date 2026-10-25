// Guided practice ("Try it"): a fresh engine-generated problem solved one decision at a time by the student.
// Scheduling: pick who gets the CPU at each decision. Basics: fill CT/TAT/WT for a finished chart.
// Semaphores: predict each value and outcome. Banker's: build a safe sequence (any valid one is accepted).
import { useEffect, useState } from "react";
import { learnApi } from "../../api.js";
import { Tables } from "../Cards.jsx";
import Gantt from "../Gantt.jsx";
import Markdown from "../Markdown.jsx";
import Table from "../Table.jsx";
import Thinking from "../Thinking.jsx";
import { Options } from "./YourQuestion.jsx";

function Score({ results, unit }) {
  const right = results.filter(Boolean).length;
  const good = !results.length || right / results.length >= 0.8;
  return <p className={`verdict ${good ? "verdict--ok" : "verdict--no"}`}>You got <b>{right} of {results.length}</b> {unit} right.</p>;
}

function Predict({ t, again }) {
  const [i, setI] = useState(0);
  const [picked, setPicked] = useState(null);
  const [results, setResults] = useState([]);
  const n = t.steps.length;
  const s = t.steps[i];
  const choose = (o) => { setPicked(o); setResults((r) => [...r, o === s.answer]); };
  return (
    <>
      <Table {...t.processes} small />
      <p className="muted small">{t.title}</p>
      {i < n ? (
        <>
          <Gantt {...s.gantt} span={t.span} title={`Your chart so far · question ${i + 1} of ${n}`} />
          <div className="decision">
            <p className="decision__event">{s.event} {s.question}</p>
            <Table {...s.ready} small label="Ready to run" />
            {s.queue && <details className="more"><summary>Peek at the ready queue (track it yourself first)</summary>{s.queue.join(" → ")}</details>}
            <Options options={s.options} value={picked} onChange={choose} disabled={picked !== null} />
            {picked !== null && (
              <>
                <p className={`verdict ${picked === s.answer ? "verdict--ok" : "verdict--no"}`}>
                  {picked === s.answer ? <><b>Correct: {s.answer}.</b> </> : <>You chose {picked}, but <b>{s.answer}</b> should have the CPU. </>}{s.reason}
                </p>
                <button className="primary" onClick={() => { setI(i + 1); setPicked(null); }}>Continue →</button>
              </>
            )}
          </div>
        </>
      ) : (
        <>
          <Gantt {...t.final} span={t.span} title="Completed Gantt chart" />
          <Score results={results} unit="decisions" />
          <ul className="breakdown">{t.breakdown.map((l, k) => <li key={k}><Markdown text={l} /></li>)}</ul>
          <button className="secondary" onClick={again}>Try another problem</button>
        </>
      )}
    </>
  );
}

const MARK = { correct: "✅", consistent: "↪️", wrong: "❌", missing: "—" };

function Metrics({ t }) {
  const [vals, setVals] = useState(() => Object.fromEntries(t.pids.map((p) => [p, { CT: "", TAT: "", WT: "" }])));
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (p, k, v) => { setVals((cur) => ({ ...cur, [p]: { ...cur[p], [k]: v } })); setRes(null); };
  const check = async () => {
    setBusy(true);
    const metrics = Object.fromEntries(t.pids.map((p) => [p, Object.fromEntries(
      ["CT", "TAT", "WT"].map((k) => [k, vals[p][k] === "" ? null : Number(vals[p][k])]))]));
    try { setRes(await learnApi.checkMetrics(t.problem, metrics)); } catch (e) { setRes({ errors: [e.message], cells: {} }); }
    setBusy(false);
  };
  return (
    <>
      <Table {...t.processes} small />
      <Gantt {...t.final} title="Finished Gantt chart" />
      <table className="sheet-grid">
        <thead><tr><th>Process</th><th>CT</th><th>TAT</th><th>WT</th></tr></thead>
        <tbody>
          {t.pids.map((p) => (
            <tr key={p}>
              <th scope="row">{p}</th>
              {["CT", "TAT", "WT"].map((k) => (
                <td key={k}>
                  <input type="number" step="1" value={vals[p][k]} aria-label={`${k} of ${p}`} onChange={(e) => set(p, k, e.target.value)} />
                  {res?.cells?.[p]?.[k] && <span className="cell-mark" title={res.cells[p][k]}>{MARK[res.cells[p][k]]}</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <button className="primary" disabled={busy} onClick={check}>Check my numbers</button>
      {res?.correct && <p className="verdict verdict--ok"><b>All correct.</b> You can read a Gantt chart and use both formulas.</p>}
      {res && !res.correct && res.errors.map((e, k) => <div key={k} className="verdict verdict--no"><Markdown text={e} /></div>)}
    </>
  );
}

function Semaphore({ t, again }) {
  const [i, setI] = useState(0);
  const [v, setV] = useState(null);
  const [o, setO] = useState(null);
  const [checked, setChecked] = useState(null);
  const [results, setResults] = useState([]);
  const n = t.steps.length;
  const s = t.steps[i];
  const check = () => { const ok = v === s.after && o === s.outcome; setChecked(ok); setResults((r) => [...r, ok]); };
  const next = () => { setI(i + 1); setV(null); setO(null); setChecked(null); };
  return (
    <>
      <p>Initial value: <b>{t.initial.map(([k, x]) => `${k} = ${x}`).join(", ")}</b></p>
      {i > 0 && (
        <Table small columns={["#", "Operation", "Value after", "What happened"]}
               rows={t.steps.slice(0, i).map((x, k) => [k + 1, `${x.pid}: ${x.op}(${x.sem})`, x.after, x.effect])} />
      )}
      {i < n ? (
        <div className="decision">
          <p className="decision__event">Step {i + 1}: {s.pid} calls {s.op}({s.sem}). {s.sem} is now {s.before}
            {i > 0 && t.steps[i - 1].queue.length ? `; waiting: ${t.steps[i - 1].queue.join(", ")}` : ""}.</p>
          <div className="two-col">
            <div><p className="muted small">New value of {s.sem}</p><Options options={s.value_options} value={v} onChange={setV} disabled={checked !== null} /></div>
            <div><p className="muted small">What happens?</p><Options options={s.outcomes} value={o} onChange={setO} disabled={checked !== null} /></div>
          </div>
          {checked === null
            ? <button className="primary" disabled={v === null || o === null} onClick={check}>Check</button>
            : (
              <>
                <p className={`verdict ${checked ? "verdict--ok" : "verdict--no"}`}>
                  {checked ? "Correct. " : `Not quite (you said ${v}, ${o}). `}
                  {s.sem} = {s.before} {s.op === "wait" ? "−" : "+"} 1 = {s.after}; {s.outcome}.
                </p>
                <button className="primary" onClick={next}>Continue →</button>
              </>
            )}
        </div>
      ) : (
        <>
          <Score results={results} unit="steps" />
          <button className="secondary" onClick={again}>Try another sequence</button>
        </>
      )}
    </>
  );
}

const add = (a, b) => a.map((x, k) => x + b[k]);
const vec = (a) => a.join(" ");

function Bankers({ t, again }) {
  const [seq, setSeq] = useState([]);
  const [msg, setMsg] = useState(null);
  const [mistakes, setMistakes] = useState(0);
  const work = seq.reduce((w, p) => add(w, t.allocation[t.procs.indexOf(p)]), t.available);
  const left = t.procs.filter((p) => !seq.includes(p));
  const pick = (p) => {
    const k = t.procs.indexOf(p);
    const short = t.resources.filter((_, r) => t.need[k][r] > work[r]);
    if (short.length) {
      setMistakes((m) => m + 1);
      setMsg({ ok: false, text: `${p} needs ${vec(t.need[k])} but Work is only ${vec(work)} (not enough ${short.join(", ")}). Pick a process whose Need fits in Work.` });
    } else {
      setSeq([...seq, p]);
      setMsg({ ok: true, text: `${p} can finish: Need ${vec(t.need[k])} ≤ Work ${vec(work)}. It returns ${vec(t.allocation[k])}, so Work = ${vec(add(work, t.allocation[k]))}.` });
    }
  };
  const stuck = left.length > 0 && left.every((p) => t.need[t.procs.indexOf(p)].some((x, r) => x > work[r]));
  return (
    <>
      <Tables tables={t.tables} />
      <p className="work-line">Work = <b>{vec(work)}</b> · sequence so far: {seq.join(" → ") || "—"}</p>
      {msg && <p className={`verdict ${msg.ok ? "verdict--ok" : "verdict--no"}`}>{msg.text}</p>}
      {left.length > 0 && !stuck && (
        <>
          <p className="question__prompt">Which process can finish next? (any valid choice is accepted)</p>
          <Options options={left} value={null} onChange={pick} />
        </>
      )}
      {stuck && <p className="verdict verdict--no">No remaining process fits in Work: this state is <b>unsafe</b>.</p>}
      {(left.length === 0 || stuck) && (
        <>
          {left.length === 0 && <p className="verdict verdict--ok">Safe sequence found: <b>{seq.join(" → ")}</b> ({mistakes} wrong pick{mistakes === 1 ? "" : "s"}).</p>}
          <button className="secondary" onClick={again}>Try another state</button>
        </>
      )}
    </>
  );
}

export default function Practice({ lesson }) {
  const [t, setT] = useState(null);
  const [error, setError] = useState(null);
  const [round, setRound] = useState(0);
  useEffect(() => {
    setT(null);
    learnApi.tryIt(lesson.id).then(setT).catch((e) => setError(e.message));
  }, [lesson.id, round]);
  const again = () => setRound((r) => r + 1);
  if (error) return <p className="banner">{error}</p>;
  if (!t) return <Thinking />;
  return (
    <div className="practice" key={round}>
      {t.intro && <p className="muted">{t.intro}</p>}
      {t.kind === "predict" && <Predict t={t} again={again} />}
      {t.kind === "metrics" && <Metrics t={t} />}
      {t.kind === "semaphore" && <Semaphore t={t} again={again} />}
      {t.kind === "bankers" && <Bankers t={t} again={again} />}
    </div>
  );
}
