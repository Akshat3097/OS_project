// Stage 5: what went well, what to add, misconceptions, the question results, then what to do next
// (practise in the chat, guided practice step by step, a quick quiz, re-watch, explain again, next lesson).
import { useEffect, useState } from "react";
import { learnApi } from "../../api.js";
import Markdown from "../Markdown.jsx";
import Thinking from "../Thinking.jsx";
import Practice from "./Practice.jsx";
import Quiz from "./Quiz.jsx";

const ICON = { "Strong understanding": "🌟", "Good start, a few gaps": "👍", "Needs another look": "🔁" };

export default function Pointers({ lesson, sid, onProgress, onPractice, onRewatch, onExplainAgain, onNextLesson }) {
  const [p, setP] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    learnApi.pointers(sid, lesson.id).then((x) => { setP(x); onProgress?.(); }).catch((e) => setError(e.message));
  }, [sid, lesson.id]);   // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <p className="banner">{error}</p>;
  if (!p) return <Thinking />;
  return (
    <div className="pointers">
      <h2 className="verdict-title">{ICON[p.verdict]} {p.verdict}</h2>
      {!p.explained && (
        <p className="callout callout--target">You skipped <b>Explain it back</b>, so these pointers only use your answers.
          <button className="link-btn" onClick={onExplainAgain}>Explain it now</button></p>
      )}
      <div className="two-col">
        <section>
          <h3 className="h-small">You explained well</h3>
          <ul className="ticks ticks--ok">{(p.clear.length ? p.clear : ["Next time, try to state the rule in your own words."]).map((x) => <li key={x}>{x}</li>)}</ul>
        </section>
        <section>
          <h3 className="h-small">Add this to your explanation</h3>
          <ul className="ticks ticks--add">{(p.add.length ? p.add : ["Nothing missing. Well done!"]).map((x) => <li key={x}>{x}</li>)}</ul>
        </section>
      </div>
      {p.misconceptions.length > 0 && <p className="verdict verdict--no"><b>Misconception to fix:</b> {p.misconceptions.join("; ")}</p>}
      {p.questions.length > 0 && (
        <section>
          <h3 className="h-small">Your question{p.questions.length > 1 ? "s" : ""}</h3>
          <ul className="ticks ticks--plain">{p.questions.map((q, k) => <li key={k} className={q.ok ? "ok" : "no"}>{q.ok ? "✅" : "❌"} {q.text}</li>)}</ul>
        </section>
      )}
      <section className="remember">
        <h3 className="h-small">Remember</h3>
        <div className="remember__chips">{p.summary.map((s) => <span key={s} className="pill">{s}</span>)}</div>
      </section>

      <h3 className="h-small">What next?</h3>
      <div className="row-actions">
        {p.practice_topic && (
          <button className={p.next === "practice" ? "primary" : "secondary"} onClick={() => onPractice(p.practice_topic)}>Practise in the chat</button>
        )}
        <button className={p.next === "rewatch" ? "primary" : "secondary"} onClick={onRewatch}>Re-watch the example</button>
        <button className="secondary" onClick={onExplainAgain}>Explain it again</button>
        {lesson.next && <button className="secondary" onClick={onNextLesson}>Next lesson →</button>}
      </div>
      {lesson.has_try && (
        <details className="more panel" open={p.next === "guided"}>
          <summary>Guided practice: solve a new problem step by step</summary>
          <Practice lesson={lesson} />
        </details>
      )}
      <details className="more panel">
        <summary>Quick quiz on this lesson</summary>
        <Quiz mcq={lesson.mcq} title={lesson.title} />
      </details>
      {!p.practice_topic && <p className="muted small"><Markdown text="This topic has no numeric problems yet; the quiz and the chat (“quiz me on …”) cover it." /></p>}
    </div>
  );
}
