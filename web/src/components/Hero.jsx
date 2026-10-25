// The empty conversation: the starting suggestions laid out as a Gantt chart, one block per idea.
import { PROCESS_COLORS } from "./Gantt.jsx";

// worded as a question, not "find ...", so the tutor offers to let the student try first (asking it to find or
// solve something gets the full solution straight away)
const EXAMPLE = "Round robin with q = 2: P1(0,5), P2(1,3), P3(2,1). What is the average waiting time?";

const EXPLORE = [
  ["learn", "Learn a topic", "13 lessons: real-life picture, animated example, explain it back by voice"],
  ["labs", "Labs", "Your own numbers: six schedulers side by side, Banker's, semaphores, deadlock graphs"],
  ["exam", "Mock exam", "A fresh 30-mark CAT paper, timed and marked automatically"],
  ["progress", "Progress", "Mastery per skill, common mistakes, what to practise next"],
];

export default function Hero({ name, suggestions, onSend, welcome, onGo }) {
  const items = suggestions.length ? suggestions : ["Explain Round Robin", "Give me a problem", "Quiz me on deadlocks", "How am I doing?"];
  const lengths = items.map((s) => Math.max(8, s.length));
  return (
    <div className="hero">
      <h1>{welcome ? `Welcome back, ${name}.` : `Hi ${name}, where shall we start?`}</h1>
      <p className="hero__sub">
        I teach CPU scheduling and process synchronization. Ask me anything, paste a question from a paper,
        or start with one of these.
      </p>
      <div className="hero__gantt" role="group" aria-label="Starting points">
        <div className="hero__track">
          {items.map((s, i) => (
            <button key={s} className="hero__block" style={{ flexGrow: lengths[i], background: PROCESS_COLORS[i % PROCESS_COLORS.length] }}
                    onClick={() => onSend(s)}>{s}</button>
          ))}
        </div>
      </div>
      <button className="hero__example" onClick={() => onSend(EXAMPLE)}>
        <span>Try a pasted question</span>
        <code>{EXAMPLE}</code>
      </button>
      {onGo && (
        <nav className="explore" aria-label="More than chat">
          <p className="explore__label">Or explore</p>
          <div className="explore__grid">
            {EXPLORE.map(([v, title, what]) => (
              <button key={v} className="explore__item" onClick={() => onGo(v)}>
                <span className="explore__title">{title} →</span>
                <span className="explore__what">{what}</span>
              </button>
            ))}
          </div>
        </nav>
      )}
    </div>
  );
}
