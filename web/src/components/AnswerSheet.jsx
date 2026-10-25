// The answer sheet under an open problem: an alternative to typing the answer in the chat.
import { useMemo, useState } from "react";
import Gantt from "./Gantt.jsx";

const toInt = (v) => (v === "" || v === null || v === undefined || Number.isNaN(Number(v)) ? null : Number(v));

function MetricsGrid({ pids, values, setValues }) {
  return (
    <table className="sheet-grid">
      <thead><tr><th>Process</th><th>CT</th><th>TAT</th><th>WT</th></tr></thead>
      <tbody>
        {pids.map((pid) => (
          <tr key={pid}>
            <th scope="row">{pid}</th>
            {["CT", "TAT", "WT"].map((k) => (
              <td key={k}>
                <input inputMode="decimal" aria-label={`${k} of ${pid}`} value={values[pid]?.[k] ?? ""}
                       onChange={(e) => setValues({ ...values, [pid]: { ...values[pid], [k]: e.target.value } })} />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function metricsOut(values) {
  const out = {};
  for (const [pid, row] of Object.entries(values)) {
    const r = {};
    for (const [k, v] of Object.entries(row || {})) if (toInt(v) !== null) r[k] = toInt(v);
    if (Object.keys(r).length) out[pid] = r;
  }
  return out;
}

const metricsText = (m) =>
  Object.entries(m).map(([pid, r]) => `${pid}: ` + Object.entries(r).map(([k, v]) => `${k} ${v}`).join(", ")).join("; ");

function SchedulingSheet({ form, onSubmit, busy }) {
  const prev = form.prev || {};
  const [rows, setRows] = useState(() =>
    prev.gantt?.length ? prev.gantt.map(([p, s, e]) => ({ p, s: String(s), e: String(e) }))
                       : Array.from({ length: form.rows }, () => ({ p: "", s: "", e: "" })));
  const [values, setValues] = useState(() => {
    const v = {};
    for (const [pid, r] of Object.entries(prev.metrics || {})) v[pid] = Object.fromEntries(Object.entries(r).map(([k, x]) => [k, String(x)]));
    return v;
  });
  const segs = useMemo(() => rows
    .filter((r) => r.p && toInt(r.s) !== null && toInt(r.e) !== null && toInt(r.e) > toInt(r.s))
    .map((r) => [r.p, toInt(r.s), toInt(r.e)])
    .sort((a, b) => a[1] - b[1]), [rows]);
  const set = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const submit = (e) => {
    e.preventDefault();
    const metrics = metricsOut(values);
    const parts = [];
    if (segs.length) parts.push(segs.map(([p, s, x]) => `${p} ${s}-${x}`).join(", "));
    if (Object.keys(metrics).length) parts.push(metricsText(metrics));
    if (!parts.length) return;
    onSubmit("My answer: " + parts.join("\n"), { gantt: segs, metrics });
  };
  return (
    <form onSubmit={submit} className="sheet">
      <fieldset>
        <legend>Gantt chart</legend>
        <div className="sheet-rows">
          {rows.map((r, i) => (
            <div className="sheet-row" key={i}>
              <select aria-label={`Process in block ${i + 1}`} value={r.p} onChange={(e) => set(i, "p", e.target.value)}>
                <option value="">Process</option>
                {[...form.pids, "IDLE"].map((p) => <option key={p} value={p}>{p === "IDLE" ? "idle" : p}</option>)}
              </select>
              <input inputMode="numeric" placeholder="from" aria-label={`Start of block ${i + 1}`} value={r.s}
                     onChange={(e) => set(i, "s", e.target.value)} />
              <span aria-hidden="true">to</span>
              <input inputMode="numeric" placeholder="to" aria-label={`End of block ${i + 1}`} value={r.e}
                     onChange={(e) => set(i, "e", e.target.value)} />
              <button type="button" className="icon-btn" aria-label={`Remove block ${i + 1}`}
                      onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button>
            </div>
          ))}
        </div>
        <button type="button" className="link-btn" onClick={() => setRows([...rows, { p: "", s: "", e: "" }])}>Add a block</button>
        {segs.length > 0 && <Gantt segments={segs} order={form.pids} compact />}
      </fieldset>
      <fieldset>
        <legend>Completion, turnaround and waiting times</legend>
        <MetricsGrid pids={form.pids} values={values} setValues={setValues} />
      </fieldset>
      <button className="primary" disabled={busy}>Check my answer</button>
    </form>
  );
}

function BankersSheet({ form, onSubmit, busy }) {
  const [safe, setSafe] = useState(form.prev?.safe ?? null);
  const [seq, setSeq] = useState(form.prev?.sequence?.join(", ") ?? "");
  const submit = (e) => {
    e.preventDefault();
    if (safe === null) return;
    const pids = (seq.match(/P\s?\d+/gi) || []).map((p) => p.toUpperCase().replace(/\s/g, ""));
    onSubmit(`My answer: ${safe ? "safe" : "unsafe"}${safe && seq ? `, ${seq}` : ""}`,
             { safe, sequence: safe && pids.length ? pids : null, need: null });
  };
  return (
    <form onSubmit={submit} className="sheet">
      <fieldset>
        <legend>Is the system in a safe state?</legend>
        <div className="segmented">
          <label><input type="radio" name="safe" checked={safe === true} onChange={() => setSafe(true)} /> Safe</label>
          <label><input type="radio" name="safe" checked={safe === false} onChange={() => setSafe(false)} /> Unsafe</label>
        </div>
      </fieldset>
      {safe && (
        <label className="field">Safe sequence
          <input value={seq} placeholder={form.pids.join(", ")} onChange={(e) => setSeq(e.target.value)} />
        </label>
      )}
      <button className="primary" disabled={busy || safe === null}>Check my answer</button>
    </form>
  );
}

function SemaphoreSheet({ form, onSubmit, busy }) {
  const [vals, setVals] = useState({});
  const [blocked, setBlocked] = useState([]);
  const submit = (e) => {
    e.preventDefault();
    const final = Object.fromEntries(Object.entries(vals).filter(([, v]) => toInt(v) !== null).map(([k, v]) => [k, toInt(v)]));
    onSubmit("My answer: " + Object.entries(final).map(([k, v]) => `${k} = ${v}`).join(", ") +
             `; blocked: ${blocked.join(", ") || "none"}`, { final, blocked });
  };
  return (
    <form onSubmit={submit} className="sheet">
      <fieldset>
        <legend>Final values</legend>
        <div className="sheet-inline">
          {form.sems.map((s) => (
            <label key={s} className="field field--short">{s}
              <input inputMode="numeric" value={vals[s] ?? ""} onChange={(e) => setVals({ ...vals, [s]: e.target.value })} />
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>Blocked at the end</legend>
        <div className="sheet-inline">
          {form.procs.map((p) => (
            <label key={p} className="check">
              <input type="checkbox" checked={blocked.includes(p)}
                     onChange={(e) => setBlocked(e.target.checked ? [...blocked, p] : blocked.filter((x) => x !== p))} /> {p}
            </label>
          ))}
        </div>
      </fieldset>
      <button className="primary" disabled={busy}>Check my answer</button>
    </form>
  );
}

function MetricsSheet({ form, onSubmit, busy }) {
  const [values, setValues] = useState({});
  const submit = (e) => {
    e.preventDefault();
    const metrics = metricsOut(values);
    if (Object.keys(metrics).length) onSubmit("My answer: " + metricsText(metrics), { metrics });
  };
  return (
    <form onSubmit={submit} className="sheet">
      <fieldset>
        <legend>Completion, turnaround and waiting times</legend>
        <MetricsGrid pids={form.pids} values={values} setValues={setValues} />
      </fieldset>
      <button className="primary" disabled={busy}>Check my answer</button>
    </form>
  );
}

export default function AnswerSheet({ form, onSubmit, busy }) {
  if (!form) return null;
  const Sheet = { scheduling: SchedulingSheet, bankers: BankersSheet, semaphore: SemaphoreSheet, advanced: MetricsSheet }[form.kind];
  if (!Sheet) return null;
  return (
    <details className="answer-sheet">
      <summary>Answer sheet <span>or type your answer in the chat</span></summary>
      <Sheet form={form} onSubmit={onSubmit} busy={busy} />
    </details>
  );
}
