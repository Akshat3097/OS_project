// Notes: the student's own notes as pastel sticky notes, saved from tutor replies or written by hand.
// They are stored on the laptop per student (tutor/note_store.py).
import { useCallback, useEffect, useMemo, useState } from "react";
import { notesApi } from "../api.js";
import Icon from "./Icon.jsx";
import Markdown from "./Markdown.jsx";

export const NOTE_COLORS = ["butter", "peach", "lilac", "sky", "mint"];
const NAMES = { butter: "Yellow", peach: "Peach", lilac: "Lilac", sky: "Blue", mint: "Green" };
const TILTS = [-1.4, 1.1, -0.6, 1.5, -1, 0.6];

const when = (t) => new Date(t * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short" });

function Editor({ note, onSave, onCancel }) {
  const [title, setTitle] = useState(note?.title || "");
  const [text, setText] = useState(note?.text || "");
  const [color, setColor] = useState(note?.color || "butter");
  return (
    <form className={`sticky sticky--edit sticky--${color}`}
          onSubmit={(e) => { e.preventDefault(); if (text.trim()) onSave({ title, text, color }); }}>
      <input className="sticky__title-in" placeholder="Title (optional)" value={title} aria-label="Note title"
             onChange={(e) => setTitle(e.target.value)} />
      <textarea className="sticky__text-in" placeholder="Write your note…" rows={6} value={text} aria-label="Note text"
                autoFocus onChange={(e) => setText(e.target.value)} />
      <div className="sticky__row">
        <div className="sticky__colors" role="radiogroup" aria-label="Colour">
          {NOTE_COLORS.map((c) => (
            <button type="button" key={c} role="radio" aria-checked={color === c} aria-label={NAMES[c]} title={NAMES[c]}
                    className={`dot dot--${c}${color === c ? " is-on" : ""}`} onClick={() => setColor(c)} />
          ))}
        </div>
        <div className="sticky__actions">
          <button type="button" className="link-btn" onClick={onCancel}>Cancel</button>
          <button className="primary" disabled={!text.trim()}>Save note</button>
        </div>
      </div>
    </form>
  );
}

function Sticky({ note, i, onEdit, onDelete, onPin }) {
  return (
    <article className={`sticky sticky--${note.color}${note.pinned ? " is-pinned" : ""}`}
             style={{ "--tilt": `${TILTS[i % TILTS.length]}deg` }}>
      <header className="sticky__head">
        <h3 className="sticky__title">{note.title || "Note"}</h3>
        <div className="sticky__tools">
          <button className={`icon-btn${note.pinned ? " is-on" : ""}`} aria-pressed={note.pinned}
                  aria-label={note.pinned ? "Unpin" : "Pin to the top"} title={note.pinned ? "Unpin" : "Pin to the top"}
                  onClick={onPin}><Icon name="pin" size={16} /></button>
          <button className="icon-btn" aria-label="Edit note" title="Edit" onClick={onEdit}><Icon name="edit" size={16} /></button>
          <button className="icon-btn" aria-label="Delete note" title="Delete" onClick={onDelete}><Icon name="trash" size={16} /></button>
        </div>
      </header>
      <div className="sticky__body"><Markdown text={note.text} /></div>
      <footer className="sticky__foot">
        <span>{note.source || "Written by you"}</span>
        <span>{when(note.updated)}</span>
      </footer>
    </article>
  );
}

export default function Notes({ sid, onCount }) {
  const [notes, setNotes] = useState(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [editing, setEditing] = useState(null);         // "new" or the id of the note being edited
  const [error, setError] = useState(null);

  const load = useCallback(() => notesApi.list(sid).then((d) => { setNotes(d.notes); onCount?.(d.notes.length); })
    .catch((e) => setError(e.message)), [sid, onCount]);
  useEffect(() => { load(); }, [load]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (notes || []).filter((n) => (filter === "all" || n.color === filter) &&
      (!q || `${n.title} ${n.text} ${n.source}`.toLowerCase().includes(q)));
  }, [notes, query, filter]);

  const act = async (fn) => {
    setError(null);
    try { await fn(); setEditing(null); await load(); } catch (e) { setError(e.message); }
  };
  const save = (data, id) => act(() => (id ? notesApi.update(sid, id, data) : notesApi.add(sid, data)));

  return (
    <div className="notes">
      <header className="page-head notes__head">
        <div>
          <h1>My notes</h1>
          <p className="page-head__sub">Save any tutor reply with “Save to notes”, or write your own. They stay on this laptop.</p>
        </div>
        <button className="primary notes__new" onClick={() => setEditing("new")}><Icon name="plus" size={18} />New note</button>
      </header>

      <div className="notes__bar">
        <label className="notes__search">
          <Icon name="search" size={18} />
          <input type="search" placeholder="Search your notes" value={query} aria-label="Search notes"
                 onChange={(e) => setQuery(e.target.value)} />
        </label>
        <div className="notes__filters" role="group" aria-label="Filter by colour">
          <button className={`chip${filter === "all" ? " is-on" : ""}`} onClick={() => setFilter("all")}>All</button>
          {NOTE_COLORS.map((c) => (
            <button key={c} className={`chip chip--dot${filter === c ? " is-on" : ""}`} onClick={() => setFilter(c)}>
              <span className={`dot dot--${c}`} aria-hidden="true" />{NAMES[c]}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="error-text">{error}</p>}

      {notes && notes.length === 0 && editing !== "new" ? (
        <div className="notes__empty">
          <div className="notes__empty-stack" aria-hidden="true"><i /><i /><i /></div>
          <h2>No notes yet</h2>
          <p className="muted">In the chat, press <b>Save to notes</b> under any reply to keep it here, or write your own.</p>
          <button className="secondary" onClick={() => setEditing("new")}>Write a note</button>
        </div>
      ) : (
        <div className="board">
          {editing === "new" && <Editor onSave={(d) => save(d)} onCancel={() => setEditing(null)} />}
          {shown.map((n, i) => (editing === n.id
            ? <Editor key={n.id} note={n} onSave={(d) => save(d, n.id)} onCancel={() => setEditing(null)} />
            : <Sticky key={n.id} note={n} i={i} onEdit={() => setEditing(n.id)}
                      onPin={() => act(() => notesApi.update(sid, n.id, { pinned: !n.pinned }))}
                      onDelete={() => { if (window.confirm("Delete this note?")) act(() => notesApi.remove(sid, n.id)); }} />))}
          {notes && notes.length > 0 && shown.length === 0 && <p className="muted">No notes match.</p>}
        </div>
      )}
    </div>
  );
}
