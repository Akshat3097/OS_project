// Stage 1: the everyday picture, real-life examples, the exact rule, the class notes, and the language model
// for "explain it differently" and questions about the lesson. The theory is drawn as papers in a folder (Paper.jsx).
import { useEffect, useState } from "react";
import { getJSON, learnApi, streamNDJSON } from "../../api.js";
import Markdown from "../Markdown.jsx";
import Paper, { Folder, Slip } from "../Paper.jsx";
import Thinking from "../Thinking.jsx";
import VideoClips from "../VideoClips.jsx";

const pad = (n) => String(n).padStart(2, "0");

function useExplainer(lesson, sid, model) {
  const [busy, setBusy] = useState(false);
  const ask = async (question, history, onText) => {
    setBusy(true);
    let text = "";
    let source = "";
    try {
      await streamNDJSON("/api/learn/explain", { sid, lesson: lesson.id, question, history, model, use_llm: !!model },
        (ev) => {
          if (ev.type === "delta") { text += ev.text; onText(text, null); }
          else if (ev.type === "done") source = ev.source;
          else if (ev.type === "error") { text = ev.fallback || text; source = "prepared explanation (the model stopped)"; onText(text, null); }
        });
    } catch {
      text = text || "I couldn't reach the tutor's server just now. Try again in a moment.";
    }
    onText(text, source || "offline");
    setBusy(false);
    return text;
  };
  return [busy, ask];
}

function ClassNotes({ lesson, model }) {
  const [notes, setNotes] = useState(null);
  const load = (e) => {
    if (e.currentTarget.open && notes === null) {
      learnApi.notes(lesson.id, model).then(setNotes).catch(() => setNotes([]));
    }
  };
  return (
    <details className="more notes" onToggle={load}>
      <summary>What your class notes say</summary>
      {notes === null && <Thinking />}
      {notes?.length === 0 && <p className="muted">Nothing in the notes for this topic.</p>}
      {notes?.map((n, i) => (
        <Paper key={i} className="paper--mini notes__item" holes={false} file={`Excerpt ${pad(i + 1)}`}
               kicker={`${n.section}${n.source ? ` · ${n.source}` : ""}`}>
          <Markdown text={n.text} />
        </Paper>
      ))}
    </details>
  );
}

export default function Understand({ lesson, sid, model }) {
  const [alt, setAlt] = useState(null);           // {text, source}
  const [qa, setQa] = useState([]);               // [{role, content}]
  const [draft, setDraft] = useState("");
  const [busy, ask] = useExplainer(lesson, sid, model);
  const [clips, setClips] = useState([]);
  useEffect(() => {
    getJSON(`/api/videos?lesson=${encodeURIComponent(lesson.id)}`).then((d) => setClips(d.clips || [])).catch(() => setClips([]));
  }, [lesson.id]);

  const explainDifferently = () => ask(null, [], (text, source) => setAlt({ text, source }));
  const askQuestion = async (e) => {
    e.preventDefault();
    const question = draft.trim();
    if (!question || busy) return;
    setDraft("");
    const history = qa.slice();
    setQa([...history, { role: "user", content: question }, { role: "assistant", content: "" }]);
    await ask(question, history, (text) =>
      setQa((cur) => { const out = cur.slice(); out[out.length - 1] = { role: "assistant", content: text }; return out; }));
  };

  const no = lesson.number ? pad(lesson.number) : null;      // an older server sends no lesson number
  const real = lesson.real_life || [];
  return (
    <div className="understand">
      <Folder label={`BCSE303P · Lesson${no ? ` ${no}` : ""}${lesson.of ? ` of ${lesson.of}` : ""}`}>
        <p className="folder__goal"><b>Goal</b>{lesson.goal}</p>
        <div className={`folder__grid${real.length ? "" : " folder__grid--single"}`}>
          <Paper tone="pink" holes={false} kicker="Excerpt A" title="Everyday picture" className="paper--excerpt">
            <Markdown text={lesson.analogy} />
          </Paper>
          {real.length > 0 && (
            <Slip heading="Real life" sub="Where you see it">
              <ol className="slip__list">
                {real.map((x, i) => <li key={i}><span className="slip__n">{pad(i + 1)}</span><Markdown text={x} /></li>)}
              </ol>
              <p className="slip__total"><span>Entries</span><span>{pad(real.length)}</span></p>
            </Slip>
          )}
          <Paper className="paper--rule" file={no ? `File No. ${no}` : "File"} title="The exact rule"
                 note={<><p>Filed under {lesson.group}.</p><p>About {lesson.minutes} min to read.</p>
                         <p>Read the everyday picture first, then this.</p></>}
                 serial={`BCSE303P-${lesson.id.toUpperCase()}${no ? `-${no}` : ""}`}
                 tabs={[{ label: lesson.group, tone: "red" }, { label: "Understand", tone: "blue" }]}>
            <Markdown text={lesson.concept} />
          </Paper>
        </div>
      </Folder>
      <VideoClips clips={clips} />
      <ClassNotes lesson={lesson} model={model} />

      <div className="understand__actions">
        <button className="secondary" disabled={busy} onClick={explainDifferently}>Explain it differently</button>
      </div>
      {alt && (
        <Paper tone="pink" holes={false} className="paper--mini paper--alt" title="Another way to see it"
               kicker={`Excerpt B${alt.source ? ` · ${alt.source}` : ""}`}>
          {alt.text ? <Markdown text={alt.text} /> : <Thinking />}
        </Paper>
      )}

      <section className="lesson-qa">
        <h2 className="h-small">Ask a question about this lesson</h2>
        {qa.map((m, i) => (
          m.role === "user"
            ? <div key={i} className="msg msg--user"><div className="bubble">{m.content}</div></div>
            : <Paper key={i} className="paper--mini lesson-qa__answer" holes={false} file="Answered">
                {m.content ? <Markdown text={m.content} /> : <Thinking />}
              </Paper>
        ))}
        <form className="inline-ask" onSubmit={askQuestion}>
          <input value={draft} onChange={(e) => setDraft(e.target.value)} disabled={busy}
                 placeholder={lesson.id === "sjf" ? "e.g. Why isn't SJF used directly in real systems?" : "e.g. Why does this rule matter?"} />
          <button className="primary" disabled={busy || !draft.trim()}>Ask</button>
        </form>
        {!model && <p className="muted small">The language model is off, so answers come from the course notes.</p>}
      </section>
    </div>
  );
}
