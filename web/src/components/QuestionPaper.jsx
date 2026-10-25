// MCQs and lesson questions as an exam question paper, on the same archival sheet as the theory (Paper.jsx): a course
// header with instructions, numbered questions with marks, options ticked in pencil, and red-pen marking once checked.
const LETTERS = "abcd";

export function PenMark({ ok, size = 30 }) {
  return (
    <svg className="pen-mark" viewBox="0 0 24 24" width={size} height={size} aria-label={ok ? "right" : "wrong"} role="img"
         fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
      {ok ? <path d="M3.5 13.5 9 19 21 5" /> : <path d="M5.5 5.5l13 13M18.5 5.5l-13 13" />}
    </svg>
  );
}

export function QuestionPaper({ title, meta = [], rules, grade, foot, className = "", children }) {
  return (
    <section className={`qpaper ${className}`}>
      <div className="paper__holes" aria-hidden="true"><i /><i /><i /></div>
      <header className="qpaper__head">
        <p className="qpaper__course">BCSE303P · Operating Systems</p>
        <h2 className="qpaper__title">{title}</h2>
        {meta.length > 0 && <p className="qpaper__meta">{meta.map((m) => <span key={m}>{m}</span>)}</p>}
        {rules && <p className="qpaper__rules">{rules}</p>}
        {grade && <span className={`qpaper__grade${grade[0] === grade[1] ? " qpaper__grade--full" : ""}`} role="img" aria-label={`Score ${grade[0]} out of ${grade[1]}`}>{grade[0]}/{grade[1]}</span>}
      </header>
      {children}
      {foot && <p className="qpaper__foot">{foot}</p>}
    </section>
  );
}

// One question: the number in the margin, the marks on the right, options with a circle to tick.
// picked and answer are option indexes; once marked, the tick and the right option are drawn in red pen.
export function PaperQuestion({ n, text, options, picked = null, answer = null, marked = false, why, onPick, disabled,
                                marks = 1, ok: given, children }) {
  const ok = marked && (given ?? picked === answer);           // given: the server's verdict for non-option answers
  const answered = marked && (given !== undefined || picked !== null);
  return (
    <div className={`qq${marked ? " is-marked" : ""}${answered ? (ok ? " is-right" : " is-wrong") : ""}`}>
      <div className="qq__n">Q{n}.{answered && <PenMark ok={ok} />}</div>
      <div className="qq__main">
        {text && <p className="qq__text">{text}</p>}
        {children}
        {options && (
          <div className="qq__opts" role="radiogroup" aria-label={`Question ${n} options`}>
            {options.map((o, k) => (
              <button key={k} type="button" role="radio" aria-checked={picked === k} disabled={disabled || marked}
                      className={`qq__opt${picked === k ? " is-picked" : ""}${marked && answer === k ? " is-answer" : ""}`}
                      onClick={() => onPick?.(k)}>
                <span className="qq__letter">({LETTERS[k]})</span>
                <span className="qq__box" aria-hidden="true" />
                <span className="qq__label">{String(o)}</span>
              </button>
            ))}
          </div>
        )}
        {marked && why && <div className="qq__why">{why}</div>}
      </div>
      <span className="qq__marks">
        {answered ? <b className="qq__score">{ok ? marks : 0}/{marks}</b> : `[${marks} mark${marks > 1 ? "s" : ""}]`}
      </span>
    </div>
  );
}
