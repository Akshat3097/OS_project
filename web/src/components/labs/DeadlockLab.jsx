// Deadlock lab: build a resource-allocation graph, see it drawn with its cycles, the wait-for graph, and the
// detection algorithm's verdict (server/labs.py → engine/deadlock.py).
import { useEffect, useState } from "react";
import { Tables } from "../Cards.jsx";
import Table from "../Table.jsx";
import { post } from "./Labs.jsx";

const W = 640;

function xs(n, w = W, pad = 70) {
  return Array.from({ length: n }, (_, i) => (n === 1 ? w / 2 : pad + (i * (w - 2 * pad)) / (n - 1)));
}

// Processes in a row on top, resources in a row below; holds edges R → P, request edges P → R.
function RagSvg({ g, cycle }) {
  const px = Object.fromEntries(g.processes.map((p, i) => [p, xs(g.processes.length)[i]]));
  const rx = Object.fromEntries(g.resources.map(([r], i) => [r, xs(g.resources.length)[i]]));
  const PY = 52, RY = 210, RH = 44;
  const pairs = new Set(g.edges.map((e) => [e.from, e.to].sort().join("|")));
  const both = (e) => pairs.has([e.from, e.to].sort().join("|")) &&
    g.edges.some((o) => o !== e && o.from === e.to && o.to === e.from);
  const dead = new Set(g.deadlocked);
  const lit = new Set((cycle || []).map((v, k, c) => `${v}>${c[(k + 1) % c.length]}`));
  return (
    <svg className="rag" viewBox={`0 0 ${W} 270`} role="img"
         aria-label={`Resource-allocation graph: ${g.edges.map((e) => `${e.from} to ${e.to}`).join(", ")}`}>
      <defs>
        {["plain", "cycle"].map((k) => (
          <marker key={k} id={`arrow-${k}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10z" className={`rag__head rag__head--${k}`} />
          </marker>
        ))}
      </defs>
      {g.edges.map((e, k) => {
        const isHold = e.kind === "holds";
        const p = isHold ? e.to : e.from, r = isHold ? e.from : e.to;
        const off = both(e) ? (isHold ? 7 : -7) : 0;
        const x1 = (isHold ? rx[r] : px[p]) + off, x2 = (isHold ? px[p] : rx[r]) + off;
        const y1 = isHold ? RY : PY + 22, y2 = isHold ? PY + 24 : RY - 2;
        const cls = lit.has(`${e.from}>${e.to}`) ? "cycle" : "plain";
        return (
          <g key={k}>
            <line x1={x1} y1={y1} x2={x2} y2={y2} className={`rag__edge rag__edge--${cls}${isHold ? "" : " rag__edge--req"}`}
                  markerEnd={`url(#arrow-${cls})`} />
            {e.count > 1 && <text x={(x1 + x2) / 2 + (off >= 0 ? 8 : -8)} y={(y1 + y2) / 2} className="rag__count"
                                  textAnchor={off >= 0 ? "start" : "end"}>×{e.count}</text>}
          </g>
        );
      })}
      {g.processes.map((p) => (
        <g key={p}>
          <circle cx={px[p]} cy={PY} r={22} className={`rag__proc${dead.has(p) ? " is-dead" : ""}`} />
          <text x={px[p]} y={PY + 5} textAnchor="middle" className="rag__label">{p}</text>
        </g>
      ))}
      {g.resources.map(([r, n]) => {
        const w = Math.max(56, n * 12 + 20);
        return (
          <g key={r}>
            <rect x={rx[r] - w / 2} y={RY} width={w} height={RH} rx={5} className="rag__res" />
            <text x={rx[r]} y={RY + RH + 16} textAnchor="middle" className="rag__label">{r}</text>
            {Array.from({ length: n }, (_, i) => (
              <circle key={i} cx={rx[r] - ((n - 1) * 12) / 2 + i * 12} cy={RY + RH / 2} r={3.5} className="rag__dot" />
            ))}
          </g>
        );
      })}
    </svg>
  );
}

function WaitForSvg({ g }) {
  const n = g.processes.length, R = 70, C = 100;
  const pos = Object.fromEntries(g.processes.map((p, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / n;
    return [p, [C + R * Math.cos(a), C + R * Math.sin(a)]];
  }));
  const inCycle = new Set(g.wait_for_cycles.flatMap((c) => c.map((v, k) => `${v}>${c[(k + 1) % c.length]}`)));
  return (
    <svg className="rag rag--wfg" viewBox="0 0 200 200" role="img" aria-label={`Wait-for graph: ${g.wait_for.map(([a, b]) => `${a} waits for ${b}`).join(", ") || "no edges"}`}>
      {g.wait_for.map(([a, b], k) => {
        const [x1, y1] = pos[a], [x2, y2] = pos[b];
        const d = Math.hypot(x2 - x1, y2 - y1) || 1, ux = (x2 - x1) / d, uy = (y2 - y1) / d;
        const nx = -uy * 5, ny = ux * 5;           // a small sideways offset, so A→B and B→A don't overlap
        const cls = inCycle.has(`${a}>${b}`) ? "cycle" : "plain";
        return <line key={k} x1={x1 + ux * 18 + nx} y1={y1 + uy * 18 + ny} x2={x2 - ux * 20 + nx} y2={y2 - uy * 20 + ny}
                     className={`rag__edge rag__edge--${cls}`} markerEnd={`url(#arrow-${cls})`} />;
      })}
      {g.processes.map((p) => (
        <g key={p}>
          <circle cx={pos[p][0]} cy={pos[p][1]} r={16} className={`rag__proc${g.deadlocked.includes(p) ? " is-dead" : ""}`} />
          <text x={pos[p][0]} y={pos[p][1] + 4} textAnchor="middle" className="rag__label rag__label--small">{p}</text>
        </g>
      ))}
    </svg>
  );
}

export default function DeadlockLab({ presets }) {
  const first = presets[0] || { processes: ["P1", "P2"], resources: [["R1", 1]], edges: [] };
  const [procs, setProcs] = useState(first.processes.join(", "));
  const [res, setRes] = useState(first.resources.map((r) => [...r]));
  const [edges, setEdges] = useState(first.edges.map((e) => [...e]));
  const [g, setG] = useState(null);
  const [error, setError] = useState(null);
  const [sel, setSel] = useState(0);
  const plist = procs.split(/[\s,]+/).map((p) => p.trim().toUpperCase()).filter(Boolean);
  const rlist = res.map(([r]) => String(r).trim().toUpperCase()).filter(Boolean);

  const run = async (p = plist, r = res, e = edges) => {
    setError(null);
    try { setG(await post("/api/labs/deadlocks", { processes: p, resources: r, edges: e })); setSel(0); }
    catch (err) { setError(err.message); setG(null); }
  };
  useEffect(() => { run(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const load = (p) => {
    setProcs(p.processes.join(", ")); setRes(p.resources.map((r) => [...r])); setEdges(p.edges.map((e) => [...e]));
    run(p.processes, p.resources, p.edges);
  };
  const setEdge = (i, k, v) => setEdges(edges.map((e, j) => (j === i ? e.map((x, c) => (c === k ? v : x)) : e)));

  return (
    <div className="lab">
      <div className="lab__input">
        <div className="presets">
          <span className="muted small">Start from:</span>
          {presets.map((p) => <button key={p.name} className="chip" onClick={() => load(p)}>{p.name}</button>)}
        </div>
        <div className="sem-editor">
          <div>
            <label className="field">Processes (comma-separated)
              <input value={procs} onChange={(e) => setProcs(e.target.value)} />
            </label>
            <p className="table-label" style={{ marginTop: 12 }}>Resources and how many instances each has</p>
            {res.map(([r, n], i) => (
              <div key={i} className="sheet-row">
                <input value={r} aria-label="Resource name" onChange={(e) => setRes(res.map((x, j) => (j === i ? [e.target.value, x[1]] : x)))} />
                <span>×</span>
                <input type="number" min={1} value={n} aria-label={`Instances of ${r}`} onChange={(e) => setRes(res.map((x, j) => (j === i ? [x[0], e.target.value] : x)))} />
                <button className="icon-btn" aria-label={`Remove ${r}`} disabled={res.length <= 1} onClick={() => setRes(res.filter((_, j) => j !== i))}>×</button>
              </div>
            ))}
            <button className="link-btn" disabled={res.length >= 6} onClick={() => setRes([...res, [`R${res.length + 1}`, 1]])}>+ Add a resource</button>
          </div>
          <div>
            <p className="table-label">Edges: who holds and who is waiting for what</p>
            <ol className="ops">
              {edges.map((e, i) => (
                <li key={i} className="sheet-row">
                  <select value={e[0]} aria-label={`Process of edge ${i + 1}`} onChange={(ev) => setEdge(i, 0, ev.target.value)}>
                    {(plist.includes(e[0]) ? plist : [e[0], ...plist]).map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                  <select value={e[1]} aria-label={`Kind of edge ${i + 1}`} onChange={(ev) => setEdge(i, 1, ev.target.value)}>
                    <option value="holds">holds</option><option value="wants">is waiting for</option>
                  </select>
                  <input type="number" min={1} value={e[3]} className="ops__pid" aria-label={`Count of edge ${i + 1}`} onChange={(ev) => setEdge(i, 3, ev.target.value)} />
                  <select value={e[2]} aria-label={`Resource of edge ${i + 1}`} onChange={(ev) => setEdge(i, 2, ev.target.value)}>
                    {(rlist.includes(e[2]) ? rlist : [e[2], ...rlist]).map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                  <button className="icon-btn" aria-label={`Remove edge ${i + 1}`} onClick={() => setEdges(edges.filter((_, j) => j !== i))}>×</button>
                </li>
              ))}
            </ol>
            <button className="link-btn" disabled={edges.length >= 30} onClick={() => setEdges([...edges, [plist[0] || "P1", "wants", rlist[0] || "R1", 1]])}>+ Add an edge</button>
          </div>
        </div>
        <button className="primary" onClick={() => run()}>Check for deadlock</button>
        {error && <p className="error-text">{error}</p>}
      </div>

      {g && (
        <>
          <div className={`verdict ${g.deadlock ? "verdict--no" : "verdict--ok"}`} aria-live="polite">
            <p><b>{g.deadlock ? `Deadlock: ${g.deadlocked.join(", ")}` : "No deadlock"}</b>. {g.why}</p>
            {!g.deadlock && g.sequence.length > 0 && <p className="small">The processes can finish in the order {g.sequence.join(" → ")}
              {g.skipped.length ? ` (${g.skipped.join(", ")} hold nothing, so they cannot be part of a deadlock)` : ""}. Other orders can work too.</p>}
          </div>
          <h2 className="h-small">Resource-allocation graph</h2>
          <figure className="rag-figure">
            <RagSvg g={g} cycle={g.cycles[sel]} />
            <figcaption className="legend">
              <span><svg width="26" height="8" aria-hidden="true"><line x1="0" y1="4" x2="26" y2="4" className="rag__edge rag__edge--plain" /></svg> holds (resource → process)</span>
              <span><svg width="26" height="8" aria-hidden="true"><line x1="0" y1="4" x2="26" y2="4" className="rag__edge rag__edge--plain rag__edge--req" /></svg> waiting for (process → resource)</span>
              {g.cycles.length > 0 && <span><svg width="26" height="8" aria-hidden="true"><line x1="0" y1="4" x2="26" y2="4" className="rag__edge rag__edge--cycle" /></svg> the selected cycle</span>}
              <span>• = one instance</span>
            </figcaption>
          </figure>
          {g.cycles.length > 0 ? (
            <div className="presets cycles" role="radiogroup" aria-label="Cycles in the graph">
              <span className="muted small">{g.cycles.length === 1 ? "1 cycle:" : `${g.cycles.length}${g.cycles.length >= 12 ? "+" : ""} cycles, pick one:`}</span>
              {g.cycles.map((c, k) => (
                <button key={k} role="radio" aria-checked={k === sel} className={`chip${k === sel ? " is-on" : ""}`} onClick={() => setSel(k)}>
                  {[...c, c[0]].join(" → ")}
                </button>
              ))}
            </div>
          ) : <p className="small">No cycles.</p>}
          <div className="dash__two">
            <section>
              <h2 className="h-small">Wait-for graph</h2>
              <WaitForSvg g={g} />
              <p className="muted small">{g.single_instance
                ? "Every resource has one instance, so a cycle here means deadlock."
                : "Some resources have several instances, so a cycle here is only a warning; the detection algorithm decides."}</p>
            </section>
            <section>
              <h2 className="h-small">Detection algorithm</h2>
              <Tables tables={g.tables} />
              {g.steps.rows.length > 0 && <Table {...g.steps} small />}
              <p className="muted small">Work starts as Available. A process may finish if its Request ≤ Work; it then releases what it holds.
                A process holding nothing starts as finished. Whoever is left at the end is deadlocked.</p>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
