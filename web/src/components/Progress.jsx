// The progress dashboard: headline numbers, what to practise next, mastery per skill (BKT), the most common mistakes,
// recent attempts and lessons. One ink hue for every bar; every value is also written out as text.
import { useEffect, useState } from "react";
import { getJSON } from "../api.js";
import Thinking from "./Thinking.jsx";

function ago(ts) {
  const s = Date.now() / 1000 - ts;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

function Tile({ label, value, note }) {
  return (
    <div className="tile">
      <span className="tile__label">{label}</span>
      <span className="tile__value">{value}</span>
      {note && <span className="tile__note">{note}</span>}
    </div>
  );
}

function Bar({ frac, title }) {
  return <span className="bar" title={title}><i style={{ width: `${Math.max(0, Math.min(1, frac)) * 100}%` }} /></span>;
}

export default function Progress({ sid, onPractice, onLearn, onChat }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    setD(null);
    getJSON(`/api/progress?sid=${encodeURIComponent(sid)}`).then(setD)
      .catch(() => setError("Your progress couldn't be loaded. Is the tutor's server still running?"));
  }, [sid]);

  if (error) return <p className="banner">{error}</p>;
  if (!d) return <Thinking label="Loading your progress" />;
  const s = d.summary;
  const empty = !s.problems && !s.lessons_done && !s.teachbacks;
  const maxMistake = Math.max(1, ...d.mistakes.map((m) => m.count));

  return (
    <div className="dash">
      <h1>Your progress, {sid}</h1>
      <p className="hero__sub">Mastery is estimated with Bayesian Knowledge Tracing from your first try at each problem, so
        it moves a little with every answer. Change your name in the sidebar to start a fresh profile.</p>

      {empty && (
        <div className="callout callout--target dash__empty">
          <p>Nothing here yet. Solve a problem in the chat or finish a lesson and this page fills in.</p>
          <div className="row-actions">
            <button className="primary" onClick={onLearn}>Start a lesson</button>
            <button className="secondary" onClick={onChat}>Go to the chat</button>
          </div>
        </div>
      )}

      <div className="tiles">
        <Tile label="Problems tried" value={s.problems} note={`${s.solved} solved`} />
        <Tile label="Right first time" value={s.first_try === null ? "–" : `${Math.round(s.first_try * 100)}%`} note="no hints used" />
        <Tile label="Lessons done" value={`${s.lessons_done} / ${s.lessons_total}`} />
        <Tile label="Explained back" value={s.teachbacks} note={s.teachbacks === 1 ? "explanation" : "explanations"} />
      </div>

      <section className="next-card">
        <p className="callout__label">What to practise next</p>
        <p className="next-card__title">{d.next.name}, {d.next.difficulty}</p>
        <p className="muted">{d.next.reason}</p>
        <button className="primary" onClick={() => onPractice(d.next.request)}>Practise this now</button>
      </section>

      <section>
        <h2 className="h-small">Mastery by skill</h2>
        <div className="mastery-groups">
          {d.groups.map((g) => (
            <div key={g.name} className="mgroup">
              <h3>{g.name}</h3>
              <ul className="mrows">
                {g.skills.map((k) => (
                  <li key={k.id}>
                    <span className="mrows__name">{k.name}</span>
                    <Bar frac={k.tried ? k.p : 0}
                         title={k.tried ? `${k.name}: ${Math.round(k.p * 100)}% (${k.right} of ${k.tried} first tries right)` : `${k.name}: not tried yet`} />
                    <span className="mrows__val">{k.tried ? `${Math.round(k.p * 100)}%` : "–"}</span>
                    <span className={`mrows__level lvl-${k.level.replace(" ", "-")}`}>{k.tried ? k.level : "not tried"}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <div className="dash__two">
        <section>
          <h2 className="h-small">Most common mistakes</h2>
          {d.mistakes.length === 0 ? <p className="muted">No mistakes recorded yet.</p> : (
            <ul className="mistakes">
              {d.mistakes.map((m) => (
                <li key={m.type}>
                  <div className="mistakes__head">
                    <span className="mistakes__label">{m.label}</span>
                    {m.recurring && <span className="badge badge--warn">keeps coming back</span>}
                  </div>
                  <div className="mistakes__count">
                    <Bar frac={m.count / maxMistake} title={`${m.count} time${m.count === 1 ? "" : "s"}`} />
                    <span>{m.count}×</span>
                  </div>
                  {m.why && <p className="muted small">{m.why}</p>}
                </li>
              ))}
            </ul>
          )}
        </section>
        <section>
          <h2 className="h-small">Lessons</h2>
          <ul className="lesson-status">
            {d.lessons.map((l) => (
              <li key={l.id}>
                <span>{l.title}</span>
                <span className="muted small">
                  {l.completed ? "done" : l.started ? "started" : "not started"}
                  {l.explained !== null ? ` · explained ${Math.round(l.explained * 100)}%` : ""}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section>
        <h2 className="h-small">Recent attempts</h2>
        {d.recent.length === 0 ? <p className="muted">No attempts yet.</p> : (
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>When</th><th>Topic</th><th>Level</th><th>Result</th><th className="num">Hints</th><th>First thing to fix</th></tr></thead>
              <tbody>
                {d.recent.map((r, i) => (
                  <tr key={i}>
                    <td>{ago(r.ts)}</td>
                    <td className="rowhead">{r.topic}</td>
                    <td>{r.difficulty}</td>
                    <td className={r.correct ? "res-ok" : "res-no"}>
                      {r.correct ? "✓ Right" : r.revealed ? "Solution shown" : "✗ Not yet"}{r.attempt > 1 ? ` (try ${r.attempt})` : ""}
                    </td>
                    <td className="num">{r.hints}</td>
                    <td>{r.mistake || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
