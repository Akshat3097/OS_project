// Stage 2: a worked example, one decision at a time. The page only reveals steps the OS Engine already worked out.
import { useEffect, useState } from "react";
import { Stats, Tables } from "../Cards.jsx";
import Gantt from "../Gantt.jsx";
import Markdown from "../Markdown.jsx";
import Table from "../Table.jsx";

// Step controls with autoplay. `i` runs from 0 to n (n = everything shown).
function useStepper(n, first = 0) {
  const [i, setI] = useState(first);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing) return undefined;
    if (i >= n) { setPlaying(false); return undefined; }
    const t = setTimeout(() => setI((k) => Math.min(k + 1, n)), 1800);
    return () => clearTimeout(t);
  }, [playing, i, n]);
  return { i, setI, playing, setPlaying };
}

function Controls({ st, n, unit = "Step", allLabel = "Show all" }) {
  const { i, setI, playing, setPlaying } = st;
  return (
    <div className="controls" role="group" aria-label="Step through the example">
      <button className="secondary" disabled={i === 0} onClick={() => { setPlaying(false); setI(i - 1); }}>← {unit}</button>
      <button className="primary" disabled={i >= n} onClick={() => { setPlaying(false); setI(i + 1); }}>{unit} →</button>
      <button className="secondary" disabled={i >= n} onClick={() => setPlaying(!playing)}>{playing ? "Pause" : "Play"}</button>
      {i < n ? <button className="link-btn" onClick={() => { setPlaying(false); setI(n); }}>{allLabel}</button>
             : <button className="link-btn" onClick={() => { setPlaying(false); setI(0); }}>Start again</button>}
    </div>
  );
}

function SchedulingWatch({ w }) {
  const n = w.steps.length;
  const st = useStepper(n);
  const { i } = st;
  const s = w.steps[i];
  return (
    <>
      <Table {...w.processes} />
      {i < n ? (
        <>
          <Gantt {...s.gantt} span={w.span} title={`Gantt chart so far · decision ${i + 1} of ${n}`} />
          <div className="decision" aria-live="polite">
            <p className="decision__event">{s.event}</p>
            <Table {...s.ready} small label="Ready to run" />
            {s.queue && <p className="decision__queue">Ready queue, front → back: <b>{s.queue.join(" → ")}</b></p>}
            <p className="decision__choice"><b>{s.answer}</b> gets the CPU. {s.reason}</p>
          </div>
        </>
      ) : (
        <>
          <Gantt {...w.final} span={w.span} title="Finished Gantt chart" />
          <div className="decision decision--done">
            <p className="decision__event">Now the numbers (TAT = CT − AT, WT = TAT − BT)</p>
            <ul className="breakdown">{w.breakdown.map((l, k) => <li key={k}><Markdown text={l} /></li>)}</ul>
            <Stats stats={w.stats} />
          </div>
        </>
      )}
      <Controls st={st} n={n} />
    </>
  );
}

function SemaphoreWatch({ w }) {
  const n = w.steps.length;
  const st = useStepper(n);
  const { i } = st;
  const single = w.initial.length === 1;
  // the value and waiting queue of every semaphore after the first i steps
  const state = Object.fromEntries(w.initial.map(([name, v]) => [name, { value: v, queue: [] }]));
  w.steps.slice(0, i).forEach((s) => { state[s.sem] = { value: s.after, queue: s.queue }; });
  const cur = i ? w.steps[i - 1] : null;
  return (
    <>
      <div className="sem-state" aria-live="polite">
        {w.initial.map(([name]) => (
          <div key={name} className="sem-box">
            <div className={`sem-value${state[name].value < 0 ? " is-neg" : ""}${cur?.sem === name ? " is-now" : ""}`}>
              <span>{name}</span><b>{state[name].value}</b>
            </div>
            <div className="sem-queue__items">
              {state[name].queue.length ? state[name].queue.map((p) => <span key={p} className="pill">{p} waiting</span>)
                : single && <span className="muted small">nobody waiting</span>}
            </div>
          </div>
        ))}
      </div>
      {cur ? (
        <p className="decision__choice">
          Step {i}: {cur.pid} calls {cur.op}({cur.sem}). {cur.sem} = {cur.before} {cur.op === "wait" ? "−" : "+"} 1 = <b>{cur.after}</b>. {cur.effect}.
          {cur.note && <><br /><span className="small">{cur.note}</span></>}
        </p>
      ) : <p className="muted small">Press Step or Play to run the operations in order.</p>}
      <table className="data trace">
        <thead><tr><th>#</th><th>Operation</th><th className="num">Value after</th><th>What happens</th><th>Waiting</th></tr></thead>
        <tbody>
          {w.steps.map((s, k) => (
            <tr key={k} className={k < i ? (k === i - 1 ? "is-now" : "") : "is-later"}>
              <td>{k + 1}</td><td className="rowhead">{s.pid}: {s.op}({s.sem})</td>
              <td className="num">{k < i ? (single ? s.after : `${s.sem} = ${s.after}`) : ""}</td><td>{k < i ? s.effect : ""}</td>
              <td>{k < i ? (s.queue.join(", ") || "—") : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {i >= n && single && (
        <p className="card__note">Check: final {w.initial[0][0]} = {w.initial[0][1]} − {w.steps.filter((s) => s.op === "wait").length} waits
          + {w.steps.filter((s) => s.op === "signal").length} signals = {w.steps[n - 1].after}.</p>
      )}
      <Controls st={st} n={n} />
    </>
  );
}

export function BankersWatch({ w }) {
  const n = w.steps.length;
  const st = useStepper(n);
  const { i } = st;
  const s = w.steps[i];
  return (
    <>
      <Tables tables={w.tables} />
      <p className="work-line">Available: <b>{w.available}</b> (resources {w.resources.join(", ")})</p>
      {i < n ? (
        <div className="decision" aria-live="polite">
          <p className="decision__event">Work = {s.work} · finished so far: {s.finished.join(", ") || "none"}</p>
          <p className="muted small">Which unfinished process can finish now? It can if its Need ≤ Work for every resource.</p>
          <ul className="checks">
            {s.checks.map((c) => (
              <li key={c.pid} className={c.ok ? "ok" : "no"}>
                <b>{c.pid}</b> Need {c.need} ≤ Work {s.work}? {c.ok ? "yes" : "no"}
              </li>
            ))}
          </ul>
          <p className="decision__choice">
            Choose <b>{s.chosen}</b>. It finishes and returns its allocation {s.released}: Work = {s.work} + {s.released} = <b>{s.work_after}</b>.
          </p>
        </div>
      ) : w.safe ? (
        <div className="decision decision--done">
          <p className="decision__choice">
            Every process can finish, so the state is <b>safe</b>. Safe sequence: <b>{w.sequence.join(" → ")}</b>.
            Other orders can be safe too, as long as each pick has Need ≤ Work.
          </p>
        </div>
      ) : (
        <div className="decision decision--done">
          <p className="decision__event">Work = {w.final_work} · finished: {w.steps.map((x) => x.chosen).join(", ") || "none"}</p>
          <p className="verdict verdict--no">
            No unfinished process has Need ≤ Work, so <b>{w.stuck.join(", ")}</b> can never finish: the state is <b>unsafe</b>.
            Unsafe does not mean deadlocked yet, only that the OS can no longer guarantee avoiding one.
          </p>
        </div>
      )}
      <Controls st={st} n={n} />
    </>
  );
}

function Slides({ w }) {
  const n = w.slides.length - 1;
  const st = useStepper(0);
  const i = Math.min(st.i, n);
  const s = w.slides[i];
  return (
    <>
      <section className="slide" aria-live="polite">
        <p className="muted small">Slide {i + 1} of {n + 1}</p>
        <h3>{s.title}</h3>
        <Markdown text={s.body} />
      </section>
      <div className="controls">
        <button className="secondary" disabled={i === 0} onClick={() => st.setI(i - 1)}>← Slide</button>
        <button className="primary" disabled={i >= n} onClick={() => st.setI(i + 1)}>Slide →</button>
      </div>
    </>
  );
}

export default function Watch({ watch }) {
  return (
    <div className="watch">
      {watch.title && <h2 className="h-small">Worked example: {watch.title}</h2>}
      {watch.intro && <p className="muted">{watch.intro}</p>}
      {watch.kind === "scheduling" && <SchedulingWatch w={watch} />}
      {watch.kind === "semaphore" && <SemaphoreWatch w={watch} />}
      {watch.kind === "bankers" && <BankersWatch w={watch} />}
      {watch.kind === "slides" && <Slides w={watch} />}
    </div>
  );
}
