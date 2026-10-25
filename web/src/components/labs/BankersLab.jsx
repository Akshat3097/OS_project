// Banker's lab: edit Allocation, Max and Available, step through the safety algorithm, and test a request.
import { useEffect, useState } from "react";
import { getJSON } from "../../api.js";
import { BankersWatch } from "../learn/Watch.jsx";
import { post } from "./Labs.jsx";

const RES = ["A", "B", "C", "D", "E"];
const resize = (m, n, r) => Array.from({ length: n }, (_, i) => Array.from({ length: r }, (_, j) => m[i]?.[j] ?? 0));

function Matrix({ label, m, setM, procs }) {
  return (
    <div className="matrix">
      <p className="table-label">{label}</p>
      <table className="sheet-grid">
        <thead><tr><th />{m[0].map((_, j) => <th key={j}>{RES[j]}</th>)}</tr></thead>
        <tbody>
          {m.map((row, i) => (
            <tr key={i}>
              <th scope="row">{procs ? `P${i}` : ""}</th>
              {row.map((v, j) => (
                <td key={j}><input type="number" min={0} value={v} aria-label={`${label} ${procs ? `P${i} ` : ""}${RES[j]}`}
                                   onChange={(e) => setM(m.map((r, a) => (a === i ? r.map((x, b) => (b === j ? e.target.value : x)) : r)))} /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function BankersLab({ presets }) {
  const first = presets[0] || { allocation: [[0, 0], [0, 0]], maximum: [[1, 1], [1, 1]], available: [1, 1] };
  const [alloc, setAlloc] = useState(first.allocation);
  const [max, setMax] = useState(first.maximum);
  const [avail, setAvail] = useState([first.available]);
  const [req, setReq] = useState({ pid: 1, vector: first.available.map(() => 0) });
  const [res, setRes] = useState(null);
  const [error, setError] = useState(null);
  const [runId, setRunId] = useState(0);
  const n = alloc.length, r = avail[0].length;

  const run = async (state = { alloc, max, avail }, request = null) => {
    setError(null);
    try {
      setRes(await post("/api/labs/bankers", { allocation: state.alloc, maximum: state.max, available: state.avail[0],
                                                resources: RES.slice(0, state.avail[0].length), request }));
      setRunId((k) => k + 1);
    } catch (e) { setError(e.message); setRes(null); }
  };
  useEffect(() => { run(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const load = (p) => {
    const s = { alloc: p.allocation, max: p.maximum, avail: [p.available] };
    setAlloc(s.alloc); setMax(s.max); setAvail(s.avail); setReq({ pid: 1, vector: p.available.map(() => 0) });
    run(s);
  };
  const size = (nn, rr) => {
    setAlloc(resize(alloc, nn, rr)); setMax(resize(max, nn, rr)); setAvail(resize(avail, 1, rr));
    setReq({ pid: Math.min(req.pid, nn - 1), vector: resize([req.vector], 1, rr)[0] });
  };

  return (
    <div className="lab">
      <div className="lab__input">
        <div className="presets">
          <span className="muted small">Start from:</span>
          {presets.map((p) => <button key={p.name} className="chip" onClick={() => load(p)}>{p.name}</button>)}
          <button className="chip" onClick={() => getJSON("/api/labs/random?kind=bankers").then(load)}>Random</button>
        </div>
        <div className="lab__opts">
          <label className="field field--short">Processes
            <input type="number" min={2} max={8} value={n} onChange={(e) => size(Math.max(2, Math.min(8, +e.target.value || 2)), r)} />
          </label>
          <label className="field field--short">Resource types
            <input type="number" min={1} max={5} value={r} onChange={(e) => size(n, Math.max(1, Math.min(5, +e.target.value || 1)))} />
          </label>
        </div>
        <div className="matrices">
          <Matrix label="Allocation" m={alloc} setM={setAlloc} procs />
          <Matrix label="Max" m={max} setM={setMax} procs />
          <Matrix label="Available" m={avail} setM={setAvail} />
        </div>
        <button className="primary" onClick={() => run()}>Check safety</button>
        {error && <p className="error-text">{error}</p>}
      </div>

      {res && (
        <>
          <h2 className="h-small">Safety algorithm, step by step</h2>
          <BankersWatch key={runId} w={res.walk} />

          <h2 className="h-small">Resource request</h2>
          <div className="request">
            <label className="field field--short">Process
              <select value={req.pid} onChange={(e) => setReq({ ...req, pid: +e.target.value })}>
                {alloc.map((_, i) => <option key={i} value={i}>P{i}</option>)}
              </select>
            </label>
            {req.vector.map((v, j) => (
              <label key={j} className="field field--short">{RES[j]}
                <input type="number" min={0} value={v}
                       onChange={(e) => setReq({ ...req, vector: req.vector.map((x, k) => (k === j ? e.target.value : x)) })} />
              </label>
            ))}
            <button className="secondary" onClick={() => run({ alloc, max, avail }, { pid: req.pid, vector: req.vector })}>Can it be granted?</button>
          </div>
          {res.request && (
            <div className={`verdict ${res.request.granted ? "verdict--ok" : "verdict--no"}`}>
              <p><b>{res.request.granted ? "Granted." : "Not granted."}</b> {res.request.message}</p>
              {res.request.walk && <p className="small">Checked by pretending to grant it: the safety algorithm below runs on the new state.</p>}
            </div>
          )}
          {res.request?.walk && <BankersWatch key={`r${runId}`} w={res.request.walk} />}
        </>
      )}
    </div>
  );
}
