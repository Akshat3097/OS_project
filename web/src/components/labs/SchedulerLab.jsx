// Scheduler lab: edit or paste a set of processes, run all six algorithms, compare the averages and the charts.
import { useEffect, useState } from "react";
import { getJSON } from "../../api.js";
import Gantt from "../Gantt.jsx";
import Table from "../Table.jsx";
import { post } from "./Labs.jsx";

function ProcessEditor({ rows, setRows }) {
  const set = (i, k, v) => setRows(rows.map((r, j) => (j === i ? r.map((x, c) => (c === k ? v : x)) : r)));
  const add = () => {
    const used = new Set(rows.map((r) => String(r[0]).toUpperCase()));
    let n = rows.length + 1;
    while (used.has(`P${n}`)) n += 1;
    setRows([...rows, [`P${n}`, rows.length ? Number(rows[rows.length - 1][1]) + 1 : 0, 3, 1]]);
  };
  return (
    <table className="sheet-grid editor">
      <thead><tr><th>Process</th><th>Arrival</th><th>Burst</th><th>Priority</th><th /></tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td><input value={r[0]} aria-label={`Name of process ${i + 1}`} onChange={(e) => set(i, 0, e.target.value)} /></td>
            {[1, 2, 3].map((k) => (
              <td key={k}><input type="number" min={k === 2 ? 1 : 0} value={r[k]} aria-label={`${["", "Arrival", "Burst", "Priority"][k]} of ${r[0]}`}
                                 onChange={(e) => set(i, k, e.target.value)} /></td>
            ))}
            <td><button className="icon-btn" aria-label={`Remove ${r[0]}`} disabled={rows.length <= 1}
                        onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button></td>
          </tr>
        ))}
      </tbody>
      <tfoot><tr><td colSpan={5}><button className="link-btn" onClick={add} disabled={rows.length >= 10}>+ Add a process</button></td></tr></tfoot>
    </table>
  );
}

export default function SchedulerLab({ presets }) {
  const [rows, setRows] = useState(() => (presets[0]?.processes || [["P1", 0, 5, 1], ["P2", 1, 3, 2]]).map((r) => [...r]));
  const [quantum, setQuantum] = useState(presets[0]?.quantum || 2);
  const [lower, setLower] = useState(true);
  const [res, setRes] = useState(null);
  const [open, setOpen] = useState(null);
  const [error, setError] = useState(null);
  const [paste, setPaste] = useState("");
  const [busy, setBusy] = useState(false);

  const run = async (r = rows, q = quantum) => {
    setBusy(true); setError(null);
    try { setRes(await post("/api/labs/scheduler", { processes: r, quantum: Number(q), lower_is_higher: lower })); }
    catch (e) { setError(e.message); setRes(null); }
    setBusy(false);
  };
  useEffect(() => { run(); }, [lower]);   // eslint-disable-line react-hooks/exhaustive-deps
  const load = (r, q) => { const copy = r.map((x) => [...x]); setRows(copy); if (q) setQuantum(q); run(copy, q || quantum); };
  const readPaste = async () => {
    setError(null);
    try {
      const p = await post("/api/labs/parse", { text: paste });
      if (p.kind !== "scheduler") { setError("That looks like a Banker's problem: open the Banker's tab."); return; }
      load(p.processes, p.quantum);
    } catch (e) { setError(e.message); }
  };
  const best = res ? Math.min(...res.runs.map((r) => r.avg_wt)) : 0;
  const worst = res ? Math.max(...res.runs.map((r) => r.avg_wt), 0.01) : 1;

  return (
    <div className="lab">
      <div className="lab__input">
        <div className="presets">
          <span className="muted small">Start from:</span>
          {presets.map((p) => <button key={p.name} className="chip" onClick={() => load(p.processes, p.quantum)}>{p.name}</button>)}
          <button className="chip" onClick={() => getJSON("/api/labs/random?kind=scheduler").then((p) => load(p.processes, p.quantum))}>Random</button>
        </div>
        <ProcessEditor rows={rows} setRows={setRows} />
        <div className="lab__opts">
          <label className="field field--short">Time quantum (RR)
            <input type="number" min={1} value={quantum} onChange={(e) => setQuantum(e.target.value)} />
          </label>
          <label className="check"><input type="checkbox" checked={!lower} onChange={(e) => setLower(!e.target.checked)} />
            Higher number = higher priority</label>
          <button className="primary" disabled={busy} onClick={() => run()}>Run all six</button>
        </div>
        <details className="more">
          <summary>Or paste a question from a paper</summary>
          <textarea className="paste" rows={3} value={paste} onChange={(e) => setPaste(e.target.value)}
                    placeholder="e.g. P1(0,5), P2(1,3), P3(2,1), q = 2   or a table with Process, Arrival, Burst" />
          <button className="secondary" disabled={!paste.trim()} onClick={readPaste}>Read it</button>
        </details>
        {error && <p className="error-text">{error}</p>}
      </div>

      {res && (
        <>
          <h2 className="h-small">Average waiting time (lower is better)</h2>
          <ul className="compare" aria-label="Average waiting time per algorithm">
            {res.runs.map((r) => (
              <li key={r.algorithm} className={r.avg_wt === best ? "is-best" : ""}>
                <span className="compare__name">{r.short}</span>
                <span className="bar" title={`${r.name}: average WT ${r.avg_wt}`}><i style={{ width: `${(r.avg_wt / worst) * 100}%` }} /></span>
                <span className="compare__val">{r.avg_wt}{r.avg_wt === best ? " · lowest" : ""}</span>
              </li>
            ))}
          </ul>
          <Table columns={["Algorithm", "Avg WT", "Avg TAT", "Avg RT", "Context switches", "CPU use"]}
                 rows={res.runs.map((r) => [r.name, r.avg_wt, r.avg_tat, r.avg_rt, r.switches, `${r.utilisation}%`])} />
          <p className="card__note">{res.note}</p>

          <h2 className="h-small">The six schedules on one time axis</h2>
          <div className="multiples">
            {res.runs.map((r) => (
              <div key={r.algorithm} className="multiple">
                <button className="multiple__head" aria-expanded={open === r.algorithm}
                        onClick={() => setOpen(open === r.algorithm ? null : r.algorithm)}>
                  <span>{r.name}</span><span className="muted small">avg WT {r.avg_wt} · {open === r.algorithm ? "hide" : "details"}</span>
                </button>
                <Gantt {...r.gantt} span={res.span} compact />
                {open === r.algorithm && (
                  <div className="multiple__body">
                    <Table {...r.results} small />
                    <details className="more"><summary>Every decision, step by step</summary><Table {...r.decisions} small /></details>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
