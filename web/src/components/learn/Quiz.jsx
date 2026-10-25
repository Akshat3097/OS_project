// The lesson's three multiple-choice questions on a question paper, marked in red pen with the reason for the
// option picked.
import { useState } from "react";
import { PaperQuestion, QuestionPaper } from "../QuestionPaper.jsx";

export default function Quiz({ mcq, title }) {
  const [answers, setAnswers] = useState(() => mcq.map(() => null));     // the index of the option picked
  const [checked, setChecked] = useState(false);
  const right = mcq.filter((q, k) => q.options[answers[k]]?.ok).length;
  return (
    <div className="quiz-block">
      <QuestionPaper title={`Quick quiz${title ? ` · ${title}` : ""}`} grade={checked ? [right, mcq.length] : null}
                     meta={[`${mcq.length} questions`, `${mcq.length} marks`, "No time limit"]}
                     rules="Answer all questions. Tick one option in each." foot="End of paper">
        {mcq.map((q, k) => {
          const answer = q.options.findIndex((o) => o.ok);
          const picked = q.options[answers[k]];
          return (
            <PaperQuestion key={k} n={k + 1} text={q.q} options={q.options.map((o) => o.text)} picked={answers[k]}
                           answer={answer} marked={checked}
                           why={picked && <>{picked.why}{!picked.ok && <> The answer is ({"abcd"[answer]}).</>}</>}
                           onPick={(i) => setAnswers((a) => a.map((x, j) => (j === k ? i : x)))} />
          );
        })}
      </QuestionPaper>
      {checked ? (
        <div className="row-actions">
          <p><b>{right} of {mcq.length}</b> right.</p>
          <button className="secondary" onClick={() => { setAnswers(mcq.map(() => null)); setChecked(false); }}>Try again</button>
        </div>
      ) : (
        <button className="primary" disabled={answers.some((a) => a === null)} onClick={() => setChecked(true)}>Check answers</button>
      )}
    </div>
  );
}
