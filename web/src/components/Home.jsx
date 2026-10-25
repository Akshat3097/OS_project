// Home: where the student stands and where to go next, as a dashboard (layout after Core 2.0 by UI8).
// Every number comes from the server: /api/progress (student model) and /api/learn/lessons.
import { useEffect, useState } from "react";
import { getJSON, learnApi } from "../api.js";
import Icon from "./Icon.jsx";

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
};

function Stat({ icon, tone, label, hint, value, sub }) {
  return (
    <div className="ov__item">
      <span className={`ov__icon tone--${tone}`}><Icon name={icon} size={26} /></span>
      <span className="ov__label">{label}<span className="ov__hint" title={hint} aria-label={hint}><Icon name="info" size={16} /></span></span>
      <span className="ov__value">{value}</span>
      {sub && <span className="ov__pill">{sub}</span>}
    </div>
  );
}

function Tile({ icon, tone, title, text, onClick }) {
  return (
    <button className="tile-btn" onClick={onClick}>
      <span className={`tile-btn__icon tone--${tone}`}><Icon name={icon} size={22} /></span>
      <span className="tile-btn__title">{title}</span>
      <span className="tile-btn__text">{text}</span>
    </button>
  );
}

export default function Home({ sid, chats, onLesson, onChat, onOpenChat, onPractice, onExam, onLabs, onLearn, onProgress }) {
  const [p, setP] = useState(null);
  const [lessons, setLessons] = useState(null);
  useEffect(() => {
    getJSON(`/api/progress?sid=${encodeURIComponent(sid)}`).then(setP).catch(() => setP(null));
    learnApi.lessons(sid).then(setLessons).catch(() => setLessons(null));
  }, [sid]);

  const s = p?.summary;
  const tried = p ? p.groups.flatMap((g) => g.skills).filter((k) => k.tried > 0) : [];
  const mastery = tried.length ? `${Math.round(100 * tried.reduce((a, k) => a + k.p, 0) / tried.length)}%` : "–";
  const rec = lessons?.lessons.find((l) => l.id === lessons.recommended);
  const groups = lessons ? [...new Set(lessons.lessons.map((l) => l.group))].map((g) => {
    const ls = lessons.lessons.filter((l) => l.group === g);
    return { name: g, done: ls.filter((l) => l.completed).length, total: ls.length };
  }) : [];
  const stages = lessons?.stages?.length || 5;

  return (
    <div className="home">
      <header className="page-head">
        <h1>{greeting()}, {sid}</h1>
        <p className="page-head__sub">Here's where you are in CPU scheduling and process synchronization.</p>
      </header>

      <section className="hcard" aria-label="Overview">
        <h2 className="hcard__title tone--peach">Overview</h2>
        <div className="ov">
          <Stat icon="target" tone="lilac" label="Mastery" value={mastery}
                hint="Average mastery of the skills you have practised (Bayesian knowledge tracing)"
                sub={tried.length ? `${tried.length} of 12 skills practised` : "Solve a problem to start"} />
          <Stat icon="learn" tone="sky" label="Lessons" value={s ? `${s.lessons_done}/${s.lessons_total}` : "–"}
                hint="Lessons finished in Learn" sub={rec ? `Next: ${rec.short}` : null} />
          <Stat icon="check" tone="mint" label="Problems solved" value={s ? s.solved : "–"}
                hint="Problems you solved in the chat" sub={s ? `of ${s.problems} tried` : null} />
          <Stat icon="mic" tone="butter" label="Explained back" value={s ? s.teachbacks : "–"}
                hint="Times you explained a topic in your own words" sub="by voice or typing" />
        </div>
      </section>

      <div className="home__grid">
        <section className="hcard" aria-label="Continue">
          <h2 className="hcard__title tone--lilac">Continue</h2>
          {rec ? (
            <div className="next-lesson">
              <span className="next-lesson__group">{rec.group} · about {rec.minutes} minutes</span>
              <span className="next-lesson__title">{rec.title}</span>
              <span className="next-lesson__goal">{rec.goal}</span>
              <span className="bar-meter" aria-label={`step ${rec.stage + 1} of ${stages}`}>
                <i style={{ width: `${(100 * (rec.started ? rec.stage + 1 : 0)) / stages}%` }} />
              </span>
              <button className="primary" onClick={() => onLesson(rec.id)}>
                {rec.started ? "Resume lesson" : "Start lesson"} <Icon name="arrow" size={18} />
              </button>
            </div>
          ) : <p className="muted">Loading…</p>}
          {p?.next && (
            <div className="next-practice">
              <span className="muted small">{p.next.reason}</span>
              <button className="secondary" onClick={() => onPractice(p.next.request)}>Practise {p.next.name}</button>
            </div>
          )}
        </section>

        <section className="hcard" aria-label="Quick start">
          <h2 className="hcard__title tone--sky">Quick start</h2>
          <div className="tiles-grid">
            <Tile icon="chat" tone="sky" title="Ask the tutor" text="Explanations, hints, your answers checked" onClick={onChat} />
            <Tile icon="paste" tone="mint" title="Paste a question" text="From a paper: solved and checked by the engine" onClick={onChat} />
            <Tile icon="quiz" tone="butter" title="Quick quiz" text={`Three questions on ${rec ? rec.short : "Round Robin"}`}
                  onClick={() => onPractice(`Quiz me on ${rec ? rec.short : "Round Robin"}`)} />
            <Tile icon="exam" tone="peach" title="Mock exam" text="30 marks, 30 minutes, marked for you" onClick={onExam} />
          </div>
        </section>
      </div>

      <div className="home__grid">
        <section className="hcard" aria-label="Topics">
          <h2 className="hcard__title tone--mint">Topics</h2>
          <ul className="topic-list">
            {groups.map((g) => (
              <li key={g.name}>
                <button className="topic-row" onClick={() => onLearn(g.name)}>
                  <span className="topic-row__name">{g.name}</span>
                  <span className="topic-row__count">{g.done} of {g.total} lessons</span>
                  <span className="bar-meter"><i style={{ width: `${(100 * g.done) / g.total}%` }} /></span>
                </button>
              </li>
            ))}
            <li>
              <button className="topic-row" onClick={onLabs}>
                <span className="topic-row__name">Labs</span>
                <span className="topic-row__count">Your own numbers: schedulers, Banker's, semaphores, deadlocks</span>
              </button>
            </li>
          </ul>
          <button className="link-btn" onClick={onProgress}>See full progress →</button>
        </section>

        <section className="hcard" aria-label="Recent chats">
          <h2 className="hcard__title tone--butter">Recent chats</h2>
          {chats.length ? (
            <ul className="home-recent">
              {chats.slice(0, 5).map((c) => (
                <li key={c.id}>
                  <button className="home-recent__row" onClick={() => onOpenChat(c.id)}>
                    <span className="home-recent__icon"><Icon name="chat" size={18} /></span>
                    <span className="home-recent__title">{c.title}</span>
                    <Icon name="arrow" size={16} />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="home-empty">
              <p className="muted">No conversations yet.</p>
              <button className="secondary" onClick={onChat}>Start one</button>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
