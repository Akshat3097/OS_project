// Cards that come with a reply. Every number in them was computed by the OS Engine on the server.
import { useState } from "react";
import Markdown from "./Markdown.jsx";
import { PaperQuestion, QuestionPaper } from "./QuestionPaper.jsx";
import Gantt from "./Gantt.jsx";
import Table from "./Table.jsx";
import VideoClips from "./VideoClips.jsx";

export function Stats({ stats }) {
  if (!stats?.length) return null;
  return (
    <dl className="stats">
      {stats.map(([label, value]) => (
        <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
      ))}
    </dl>
  );
}

export function Tables({ tables }) {
  if (!tables?.length) return null;
  const side = tables.length > 1 && tables.every((t) => t.label);
  return (
    <div className={side ? "tables tables--side" : "tables"}>
      {tables.map((t, i) => <Table key={i} {...t} small={side} />)}
    </div>
  );
}

function ProblemCard({ card }) {
  return (
    <section className="card card--task" aria-label="Problem">
      {card.bank && (
        <p className="card__source">
          From {card.bank.source}, {card.bank.question}{card.bank.marks ? ` (${card.bank.marks} marks)` : ""}
        </p>
      )}
      <h3 className="card__title">{card.title}</h3>
      {card.bank?.text && <p className="card__text">{card.bank.text}</p>}
      {card.statement && <p className="card__text">{card.statement}</p>}
      <Tables tables={card.tables} />
      {card.caption && <p className="card__note">{card.caption}</p>}
    </section>
  );
}

function SolutionCard({ card }) {
  return (
    <section className="card" aria-label="Solution">
      <h3 className="card__title">Solution from the OS Engine</h3>
      {card.gantt && <Gantt {...card.gantt} />}
      {card.verdict && <div className="card__verdict"><Markdown text={card.verdict} /></div>}
      <Tables tables={card.tables} />
      <Stats stats={card.stats} />
      {card.caption && <p className="card__note">{card.caption}</p>}
      {card.details && (
        <details className="more">
          <summary>{card.details.label}</summary>
          <Table columns={card.details.columns} rows={card.details.rows} small />
        </details>
      )}
      {card.key && (
        <div className="key">
          <p className="key__title">
            Official answer key{card.key.match === true ? ": the engine agrees" : card.key.match === false ? ": the engine disagrees with part of it" : ""}
          </p>
          <dl className="stats stats--small">
            {card.key.items.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
          </dl>
          {card.key.notes && <p className="card__note">{card.key.notes}</p>}
        </div>
      )}
    </section>
  );
}

function MarkedCard({ card }) {
  return (
    <section className={`card ${card.correct ? "card--right" : "card--fix"}`} aria-label="Your answer, checked">
      <h3 className="card__title">{card.correct ? "Verified by the OS Engine" : card.headline}</h3>
      {card.gantt && <Gantt {...card.gantt} />}
      {card.said && <p className="card__text">{card.said}</p>}
      <Tables tables={card.tables} />
      {card.legend && <ul className="legend">{card.legend.map((l) => <li key={l}>{l}</li>)}</ul>}
      {card.mistakes && (
        <p className="card__note">Mistakes found: {card.mistakes.join("; ")}</p>
      )}
      {card.mastery && (
        <div className="mastery">
          {card.mastery.map((m) => (
            <span key={m.skill} className={m.after >= m.before ? "up" : "down"}>
              {m.skill} {Math.round(m.before * 100)}% → {Math.round(m.after * 100)}%
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function ExampleCard({ card }) {
  return (
    <section className="card" aria-label="Worked example">
      <h3 className="card__title">Worked example: {card.title}</h3>
      {card.intro && <p className="card__note">{card.intro}</p>}
      {card.gantt && <Gantt {...card.gantt} />}
      <Tables tables={card.tables} />
      <Stats stats={card.stats} />
      {card.caption && <p className="card__note">{card.caption}</p>}
    </section>
  );
}

function ProgressCard({ card }) {
  const skills = [...card.skills].sort((a, b) => b.n - a.n || a.p - b.p);
  return (
    <section className="card" aria-label="Your progress">
      <h3 className="card__title">Mastery by skill</h3>
      <ul className="meters">
        {skills.map((s) => (
          <li key={s.name}>
            <span className="meters__name">{s.name}</span>
            <span className="meters__bar"><i style={{ width: `${Math.round(s.p * 100)}%` }} /></span>
            <span className="meters__val">{Math.round(s.p * 100)}%</span>
            <span className="meters__n">{s.n ? `${s.n} tried` : "not tried"}</span>
          </li>
        ))}
      </ul>
      <p className="card__note">Estimated with Bayesian Knowledge Tracing from your first attempts at each problem.</p>
    </section>
  );
}

function SourcesCard({ card }) {
  return (
    <details className="sources">
      <summary>{card.title} ({card.items.length})</summary>
      <ol>
        {card.items.map((it) => (
          <li key={it.n}>
            <p className="sources__label">{it.label}</p>
            <p className="sources__text">{it.text}</p>
            {it.full && it.full !== it.text && (
              <details className="sources__full"><summary>Show the whole passage</summary><p className="sources__text">{it.full}</p></details>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}

function QuizCard({ card, onSend, busy }) {
  const [mine, setMine] = useState(null);          // ticked here, before the reply comes back
  if (card.q) {
    const marked = card.picked !== undefined && card.picked !== null;
    return (
      <QuestionPaper className="qpaper--chat" title={`Quiz · ${card.title}`} grade={card.grade}
                     meta={[`Question ${card.number} of ${card.of}`, "1 mark each"]}
                     rules={card.number === 1 ? "Answer all questions. Tick one option, or reply with its letter." : null}
                     foot={card.number < card.of ? "Turn over" : "End of quiz"}>
        <PaperQuestion n={card.number} text={card.q} options={card.options} picked={marked ? card.picked : mine}
                       answer={card.answer} marked={marked} disabled={!card.active || busy || mine !== null}
                       onPick={(k) => { setMine(k); onSend("ABCD"[k]); }} />
      </QuestionPaper>
    );
  }
  if (!card.active) {
    return (
      <ol className="quiz-list">
        {card.options.map((opt, k) => <li key={k}><span className="quiz__letter">{"ABCD"[k]}</span> {opt}</li>)}
      </ol>
    );
  }
  return (
    <div className="quiz" role="group" aria-label={`Question ${card.number} options`}>
      {card.options.map((opt, k) => (
        <button key={k} className="quiz__opt" disabled={busy} onClick={() => onSend("ABCD"[k])}>
          <span className="quiz__letter">{"ABCD"[k]}</span>
          <span>{opt}</span>
        </button>
      ))}
    </div>
  );
}

export default function Card({ card, onSend, busy }) {
  switch (card.type) {
    case "problem": return <ProblemCard card={card} />;
    case "solution": return <SolutionCard card={card} />;
    case "marked": return <MarkedCard card={card} />;
    case "example": return <ExampleCard card={card} />;
    case "progress": return <ProgressCard card={card} />;
    case "sources": return <SourcesCard card={card} />;
    case "quiz": return <QuizCard card={card} onSend={onSend} busy={busy} />;
    case "video": return <VideoClips clips={card.clips} />;
    case "error": return <p className="card__note">{card.text}</p>;
    default: return null;
  }
}
