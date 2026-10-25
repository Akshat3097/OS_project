// One lesson: a stage bar the student can click through, the current stage, and Back / Next.
import { useEffect, useState } from "react";
import { learnApi } from "../../api.js";
import ExplainBack from "./ExplainBack.jsx";
import Pointers from "./Pointers.jsx";
import Understand from "./Understand.jsx";
import Watch from "./Watch.jsx";
import YourQuestion from "./YourQuestion.jsx";

function StageBar({ stages, stage, reached, onGo }) {
  return (
    <nav className="stagebar" aria-label="Lesson stages">
      {stages.map((name, i) => (
        <button key={name} onClick={() => onGo(i)} aria-current={i === stage ? "step" : undefined}
                className={`stagebar__step${i === stage ? " is-current" : ""}${i < stage || i <= reached ? " is-seen" : ""}`}>
          <span className="stagebar__n">{i + 1}</span>
          <span className="stagebar__name">{name}</span>
        </button>
      ))}
    </nav>
  );
}

export default function Lesson({ sid, id, model, onHome, onOpen, onPractice, onProgress, scrollTop }) {
  const [lesson, setLesson] = useState(null);
  const [error, setError] = useState(null);
  const [stage, setStage] = useState(0);
  const [reached, setReached] = useState(0);
  const [assessment, setAssessment] = useState(null);   // the result of "Explain it back"
  const [round, setRound] = useState(0);                // bumps when the student explains again

  useEffect(() => {
    learnApi.lesson(sid, id).then((l) => { setLesson(l); setReached(l.stage); })
      .catch(() => setError("This lesson couldn't be loaded."));
  }, [sid, id]);

  const go = (i) => {
    setStage(i);
    if (i > reached) {
      setReached(i);
      learnApi.stage(sid, id, i).then(onProgress).catch(() => {});
    }
    scrollTop?.();
  };

  if (error) return <p className="banner">{error}</p>;
  if (!lesson) return <p className="loading">Loading the lesson…</p>;
  const last = lesson.stages.length - 1;
  const name = lesson.stages[stage];
  const following = lesson.stages[stage + 1];
  const nextLabel = name === "Explain it back" && !assessment ? `Skip to: ${following}` : `Next: ${following}`;

  return (
    <article className="lesson">
      <button className="link-btn crumb" onClick={onHome}>← All lessons</button>
      <p className="lesson__group">{lesson.group} · about {lesson.minutes} minutes</p>
      <h1 className="lesson__title">{lesson.title}</h1>
      <StageBar stages={lesson.stages} stage={stage} reached={reached} onGo={go} />

      <div className="stage" key={`${stage}-${round}`}>
        {name === "Understand" && <Understand lesson={lesson} sid={sid} model={model} />}
        {name === "Watch" && <Watch watch={lesson.watch} />}
        {name === "Explain it back" && (
          <ExplainBack lesson={lesson} sid={sid} model={model} assessment={assessment} onAssessed={setAssessment} />
        )}
        {name === "Your question" && <YourQuestion lesson={lesson} sid={sid} onExplain={() => go(2)} />}
        {name === "Pointers" && (
          <Pointers lesson={lesson} sid={sid} onProgress={onProgress} onPractice={onPractice}
                    onRewatch={() => go(1)} onNextLesson={() => lesson.next && onOpen(lesson.next)}
                    onExplainAgain={() => { setAssessment(null); setRound((r) => r + 1); go(2); }} />
        )}
      </div>

      <div className="stage-nav">
        {stage > 0 && <button className="secondary" onClick={() => go(stage - 1)}>← {lesson.stages[stage - 1]}</button>}
        {stage < last && <button className="primary stage-nav__next" onClick={() => go(stage + 1)}>{nextLabel} →</button>}
        {stage === last && lesson.next && <button className="primary" onClick={() => onOpen(lesson.next)}>Next lesson →</button>}
      </div>
    </article>
  );
}
