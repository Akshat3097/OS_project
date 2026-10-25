import { useState } from "react";
import Card from "./Cards.jsx";
import Icon from "./Icon.jsx";
import Markdown from "./Markdown.jsx";
import Paper from "./Paper.jsx";
import Thinking from "./Thinking.jsx";

function Meta({ meta }) {
  if (!meta || !meta.action) return null;
  const facts = meta.facts || [];
  return (
    <div className="meta">
      <p className="meta__line">
        <span>Action: {meta.action}</span>
        {meta.routed_by && <span>Chosen by: {meta.routed_by}</span>}
        {meta.source && <span>Reply: {meta.source}</span>}
        {meta.latency && <span>{meta.latency} s</span>}
      </p>
      {(facts.length > 0 || meta.issues?.length > 0 || meta.blocked_text || meta.error) && (
        <details className="more">
          <summary>Behind the scenes</summary>
          {meta.strategy && (
            <p>Strategy {meta.strategy}, {meta.reveal ? "may give the answer" : "must not give the answer"}. {meta.rationale}</p>
          )}
          {facts.length > 0 && (<><p>Facts the model was given, from the OS Engine:</p><pre>{facts.join("\n")}</pre></>)}
          {meta.issues?.map((i, k) => <p key={k}>Guard: {i.type}. {i.detail}</p>)}
          {meta.blocked_text && (<><p>Model reply the guard replaced:</p><pre>{meta.blocked_text}</pre></>)}
          {meta.error && <p>Error: {meta.error}</p>}
        </details>
      )}
    </div>
  );
}

function SaveNote({ onSave }) {
  const [state, setState] = useState("idle");          // idle | saving | saved | failed
  const save = async () => {
    setState("saving");
    try { await onSave(); setState("saved"); } catch { setState("failed"); }
  };
  return (
    <button className={`save-note${state === "saved" ? " is-done" : ""}`} onClick={save} disabled={state === "saving" || state === "saved"}>
      <Icon name="bookmark" size={15} />
      {state === "saved" ? "Saved to notes" : state === "failed" ? "Couldn't save, try again" : "Save to notes"}
    </button>
  );
}

// Theory replies are drawn as a paper (the archival look); worked solutions and other replies stay as they are.
const THEORY = { faq: "Verified", explain: "Explained", ask: "Answered", code: "Pseudocode", need_matrices: "Missing data" };

function provenance(meta) {
  const s = meta.source || "";
  if (s.startsWith("checked answer")) return "Checked answer, written and verified by hand. Not generated.";
  if (s.startsWith("LLM")) return "Phrased by the language model from the lesson notes.";
  return "From the course notes.";
}

export default function Message({ message, isLast, onSend, busy, showMeta, onSaveNote }) {
  if (message.role === "user") {
    return <div className="msg msg--user"><div className="bubble">{message.content}</div></div>;
  }
  const pending = message.pending && !message.content;
  const meta = message.meta || {};
  const kind = THEORY[meta.kind || meta.action];
  // a quiz question is drawn on its question paper, so the text keeps only the lead-in or the feedback
  const onPaper = (message.cards || []).some((c) => c.type === "quiz" && c.q) ||
    (message.pending && ["quiz", "quiz_answer"].includes(meta.kind));
  const content = onPaper ? (message.content || "").replace(/\*\*Question \d+ of \d+\.\*\*[\s\S]*$/, "").trim() : message.content;
  const body = (
    <>
      {pending ? <Thinking /> : <Markdown text={content} />}
      {message.pending && message.content && <span className="caret" aria-hidden="true" />}
    </>
  );
  return (
    <div className="msg msg--tutor">
      {kind ? (
        <Paper className="paper--chat" title={kind} file={`File · ${meta.topic_name || "General"}`} note={provenance(meta)}>
          {body}
        </Paper>
      ) : body}
      {(message.cards || []).map((c, i) => <Card key={i} card={c} onSend={onSend} busy={busy} />)}
      {onSaveNote && !message.pending && message.content && <SaveNote onSave={onSaveNote} />}
      {showMeta && <Meta meta={message.meta} />}
      {isLast && !busy && message.suggestions?.length > 0 && (
        <div className="chips" role="group" aria-label="Suggestions">
          {message.suggestions.map((s) => <button key={s} className="chip" onClick={() => onSend(s)}>{s}</button>)}
        </div>
      )}
    </div>
  );
}
