// Semaphore lab: build a sequence of wait/signal operations and see a timeline of every process and semaphore,
// in the blocking convention (OSTEP, theory slides) or the busy-waiting one (Module 4 notes).
import { useEffect, useState } from "react";
import { getJSON } from "../../api.js";
import { post } from "./Labs.jsx";

export default function SemaphoreLab({ presets }) {
  const first = presets[0] || { initial: { S: 1 }, ops: [["P1", "wait", "S"]] };
  const [sems, setSems] = useState(() => Object.entries(first.initial));
  const [ops, setOps] = useState(() => first.ops.map((o) => [...o]));
  const [style, setStyle] = useState("blocking");
  const [res, setRes] = useState(null);
  const [error, setError] = useState(null);

  const run = async (s = sems, o = ops) => {
    setError(null);
    try { setRes(await post("/api/labs/semaphores", { initial: Object.fromEntries(s), ops: o })); }
    catch (e) { setError(e.message); setRes(null); }
  };
  useEffect(() => { run(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const load = (p) => { const s = Object.entries(p.initial); const o = p.ops.map((x) => [...x]); setSems(s); setOps(o); run(s, o); };
  const setOp = (i, k, v) => setOps(ops.map((o, j) => (j === i ? o.map((x, c) => (c === k ? v : x)) : o)));
  const names = sems.map(([k]) => k).filter(Boolean);
  const t = res?.[style];

  return (
    <div className="lab">
      <div className="lab__input">
        <div className="presets">
          <span className="muted small">Start from:</span>
          {presets.map((p) => <button key={p.name} className="chip" onClick={() => load(p)}>{p.name}</button>)}
          <button className="chip" onClick={() => getJSON("/api/labs/random?kind=semaphores").then(load)}>Random</button>
        </div>
        <div className="sem-editor">
          <div>
            <p className="table-label">Semaphores and their starting values</p>
            {sems.map(([k, v], i) => (
              <div key={i} className="sheet-row">
                <input value={k} aria-label="Semaphore name" onChange={(e) => setSems(sems.map((s, j) => (j === i ? [e.target.value, s[1]] : s)))} />
                <span>=</span>
                <input type="number" value={v} aria-label={`Starting value of ${k}`} onChange={(e) => setSems(sems.map((s, j) => (j === i ? [s[0], e.target.value] : s)))} />
                <button className="icon-btn" aria-label={`Remove ${k}`} disabled={sems.length <= 1} onClick={() => setSems(sems.filter((_, j) => j !== i))}>×</button>
              </div>
            ))}
            <button className="link-btn" disabled={sems.length >= 4} onClick={() => setSems([...sems, [["T", "Q", "R", "U"].find((x) => !names.includes(x)) || "X", 1]])}>+ Add a semaphore</button>
          </div>
          <div>
            <p className="table-label">Operations, in the order they run</p>
            <ol className="ops">
              {ops.map((o, i) => (
                <li key={i} className="sheet-row">
                  <input className="ops__pid" value={o[0]} aria-label={`Process of step ${i + 1}`} onChange={(e) => setOp(i, 0, e.target.value)} />
                  <select value={o[1]} aria-label={`Operation of step ${i + 1}`} onChange={(e) => setOp(i, 1, e.target.value)}>
                    <option value="wait">wait</option><option value="signal">signal</option>
                  </select>
                  <select value={o[2]} aria-label={`Semaphore of step ${i + 1}`} onChange={(e) => setOp(i, 2, e.target.value)}>
                    {(names.includes(o[2]) ? names : [o[2], ...names]).map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                  <button className="icon-btn" aria-label={`Remove step ${i + 1}`} onClick={() => setOps(ops.filter((_, j) => j !== i))}>×</button>
                </li>
              ))}
            </ol>
            <button className="link-btn" disabled={ops.length >= 30}
                    onClick={() => setOps([...ops, [ops.length ? ops[ops.length - 1][0] : "P1", "wait", names[0] || "S"]])}>+ Add an operation</button>
          </div>
        </div>
        <button className="primary" onClick={() => run()}>Run the trace</button>
        {error && <p className="error-text">{error}</p>}
      </div>

      {t && (
        <>
          <div className="segmented-btns" role="radiogroup" aria-label="Which definition of wait and signal">
            <button role="radio" aria-checked={style === "blocking"} className={style === "blocking" ? "is-on" : ""} onClick={() => setStyle("blocking")}>
              Blocking (value can go negative)</button>
            <button role="radio" aria-checked={style === "busy_wait"} className={style === "busy_wait" ? "is-on" : ""} onClick={() => setStyle("busy_wait")}>
              Busy waiting (Module 4 notes)</button>
          </div>
          <h2 className="h-small">Timeline</h2>
          <div className="table-wrap">
            <table className="timeline">
              <thead><tr><th>Step</th>{t.steps.map((s) => <th key={s.n}>{s.n}</th>)}</tr></thead>
              <tbody>
                {res.pids.map((p) => (
                  <tr key={p}>
                    <th scope="row">{p}</th>
                    {t.lanes[p].map((state, k) => (
                      <td key={k} className={`tl tl--${state || "idle"}`}
                          title={state === "acts" ? `${p}: ${t.steps[k].op}(${t.steps[k].sem})` : state ? `${p} is ${state}` : ""}>
                        {state === "acts" ? `${t.steps[k].op === "wait" ? "wait" : "signal"}(${t.steps[k].sem})`
                          : state === "blocked" ? "blocked" : state === "spinning" ? "spins" : state === "invalid" ? "can't run" : ""}
                      </td>
                    ))}
                  </tr>
                ))}
                {res.sems.map((sem) => (
                  <tr key={sem} className="timeline__sem">
                    <th scope="row">{sem} =</th>
                    {t.steps.map((s, k) => {
                      const v = [...t.steps.slice(0, k + 1)].reverse().find((x) => x.sem === sem);
                      const val = v ? v.after : Object.fromEntries(sems)[sem];
                      return <td key={k} className={Number(val) < 0 ? "neg" : ""}>{val}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="legend">
            <li><span className="tl-key tl--acts" /> runs this step</li>
            <li><span className="tl-key tl--blocked" /> {style === "blocking" ? "blocked in the waiting queue" : "spinning (busy waiting)"}</li>
          </ul>
          <h2 className="h-small">Step by step</h2>
          <table className="data trace">
            <thead><tr><th>#</th><th>Operation</th><th className="num">Before</th><th className="num">After</th><th>What happens</th>{style === "blocking" && <th>Waiting</th>}</tr></thead>
            <tbody>
              {t.steps.map((s) => (
                <tr key={s.n}>
                  <td>{s.n}</td><td className="rowhead">{s.pid}: {s.op}({s.sem})</td><td className="num">{s.before}</td>
                  <td className="num">{s.after}</td><td>{s.effect}</td>{style === "blocking" && <td>{s.queue.join(", ") || "—"}</td>}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="card__note">
            Final values: {Object.entries(t.final).map(([k, v]) => `${k} = ${v}`).join(", ")}.
            {" "}{style === "blocking" ? `Still blocked: ${t.blocked.join(", ") || "none"}.` : "With busy waiting a value never goes below 0; waiting processes spin instead of queueing."}
          </p>
        </>
      )}
    </div>
  );
}
