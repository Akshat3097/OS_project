// Learn mode: the 10 lessons. Home lists them with the student's progress; a lesson runs through five stages
// (Understand → Watch → Explain it back → Your question → Pointers). Everything is computed on the server.
import { useCallback, useEffect, useState } from "react";
import { learnApi } from "../../api.js";
import Lesson from "./Lesson.jsx";

const STEPS = [
  ["Understand", "real-life examples first, then the exact rule"],
  ["Watch", "a worked example, one decision at a time, with the reason"],
  ["Explain it back", "you explain the topic for a minute, by voice or typing"],
  ["Your question", "one question on the idea you need most"],
  ["Pointers", "what you got right, what to add, what to practise"],
];

function Status({ l }) {
  if (l.completed) return <span className="badge badge--done">Done</span>;
  if (l.started) return <span className="badge">In progress</span>;
  return <span className="badge badge--new">{l.minutes} min</span>;
}

function Home({ data, onOpen }) {
  const rec = data.lessons.find((l) => l.id === data.recommended);
  const done = data.lessons.filter((l) => l.completed).length;
  const groups = [...new Set(data.lessons.map((l) => l.group))];
  return (
    <div className="learn-home">
      <h1>Learn a topic from scratch</h1>
      <p className="hero__sub">Each lesson takes about ten minutes. The tutor teaches, shows, then asks <em>you</em> to explain it back.</p>
      <ol className="steps-explainer">
        {STEPS.map(([name, what], i) => (
          <li key={name}><span className="steps-explainer__n">{i + 1}</span><b>{name}</b> <span>{what}</span></li>
        ))}
      </ol>
      {rec && (
        <button className="suggested" onClick={() => onOpen(rec.id)}>
          <span className="suggested__label">{done ? "Suggested next" : "Start here"}</span>
          <span className="suggested__title">{rec.title}</span>
          <span className="suggested__goal">{rec.goal}</span>
          <span className="suggested__go">Start lesson →</span>
        </button>
      )}
      <p className="learn-count">{done} of {data.lessons.length} lessons done</p>
      {groups.map((g) => (
        <section key={g} className="lesson-group" id={groupId(g)}>
          <h2>{g}</h2>
          <ul className="lesson-list">
            {data.lessons.filter((l) => l.group === g).map((l) => (
              <li key={l.id}>
                <button className={`lesson-row${l.id === data.recommended ? " is-rec" : ""}`} onClick={() => onOpen(l.id)}>
                  <span className="lesson-row__text">
                    <span className="lesson-row__title">{l.title}</span>
                    <span className="lesson-row__goal">{l.goal}</span>
                  </span>
                  <Status l={l} />
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

// the anchor of a lesson group, for the sidebar's links into Learn
export const groupId = (name) => "group-" + name.toLowerCase().replace(/[^a-z]+/g, "-");

export default function Learn({ sid, model, useLLM, online, lessonId, setLessonId, onPractice, scrollTop }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const refresh = useCallback(() => {
    learnApi.lessons(sid).then((d) => { setData(d); setError(null); })
      .catch(() => setError("The lessons couldn't be loaded. Is the tutor's server still running?"));
  }, [sid]);
  useEffect(() => { refresh(); }, [refresh, lessonId]);

  if (error) return <p className="banner">{error}</p>;
  if (lessonId) {
    return (
      <Lesson key={`${sid}/${lessonId}`} sid={sid} id={lessonId} model={online && useLLM ? model : null}
              onHome={() => setLessonId(null)} onOpen={setLessonId} onPractice={onPractice} onProgress={refresh}
              scrollTop={scrollTop} />
    );
  }
  if (!data) return <p className="loading">Loading the lessons…</p>;
  return <Home data={data} onOpen={setLessonId} />;
}
