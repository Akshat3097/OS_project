// The sidebar: brand, modes (with chats, lesson groups and labs as a tree under them), and the settings card.
// Layout after Core 2.0 (UI8): thin-line icons, collapsible sections, the active item as a white pill.
import { useState } from "react";
import { storage, store } from "../api.js";
import Icon from "./Icon.jsx";

function Logo() {
  return (
    <span className="logo" aria-hidden="true"><i /><i /><i /></span>
  );
}

// what each installed model is, for the model picker (matched on the name before ":")
const MODEL_NOTES = { "os-tutor": "fine-tuned", "os-tutor-v2": "fine-tuned, 2nd round", "os-tutor-prompt": "prompt only, not trained",
                      "llama3.1": "base model" };
const short = (m) => m.replace(/:latest$/, "");
const modelNote = (m) => MODEL_NOTES[m.split(":")[0]] || "other";

export const LAB_TABS = [["scheduler", "Scheduler"], ["bankers", "Banker's algorithm"], ["semaphores", "Semaphores"],
                         ["deadlocks", "Deadlocks"]];
const THEMES = [["system", "Auto", "monitor"], ["light", "Light", "sun"], ["dark", "Dark", "moon"]];

function NavItem({ icon, label, on, onClick, open, onToggle, children, count, tone = "lilac" }) {
  return (
    <>
      <div className={`nav__item${on ? " is-on" : ""}`}>
        <button className="nav__link" aria-current={on ? "page" : undefined} onClick={onClick}>
          <Icon name={icon} /><span>{label}</span>
          {count != null && <span className={`nbadge nbadge--${tone}`}>{count}</span>}
        </button>
        {onToggle && (
          <button className="nav__toggle" aria-expanded={open} aria-label={`${open ? "Hide" : "Show"} ${label}`} onClick={onToggle}>
            <Icon name="chevron" size={18} />
          </button>
        )}
      </div>
      {onToggle && open && <div className="nav__children">{children}</div>}
    </>
  );
}

function Child({ label, on, onClick, count, tone = "mint", title }) {
  return (
    <button className={`nav__child${on ? " is-on" : ""}`} onClick={onClick} title={title}>
      <span className="nav__child-label">{label}</span>
      {count != null && <span className={`nbadge nbadge--${tone}`}>{count}</span>}
    </button>
  );
}

export default function Sidebar({ sid, setSid, chats, current, onOpen, onNew, onDelete, status, model, setModel,
                                  useLLM, setUseLLM, showMeta, setShowMeta, open, onClose, view, setView, theme, setTheme,
                                  groups = [], onLearnGroup, labTab, onLabTab, noteCount }) {
  const [name, setName] = useState(sid);
  const [expanded, setExpanded] = useState(() => storage("navOpen", { chat: true, learn: false, labs: false }));
  const toggle = (k) => { const n = { ...expanded, [k]: !expanded[k] }; setExpanded(n); store("navOpen", n); };
  const commit = () => { const n = name.trim() || "demo"; setName(n); if (n !== sid) setSid(n); };
  const initials = (sid || "?").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  return (
    <aside className={`sidebar${open ? " sidebar--open" : ""}`} aria-label="Navigation and settings">
      <div className="brand"><Logo /><span className="brand__name">OS Tutor<small>BCSE303 · Operating Systems</small></span>
        <button className="icon-btn sidebar__close" aria-label="Close menu" onClick={onClose}>×</button>
      </div>
      <button className="new-chat" onClick={onNew}><Icon name="plus" size={20} /><span>New chat</span></button>
      <nav className="side-nav" aria-label="Mode">
        <NavItem icon="home" label="Home" on={view === "home"} onClick={() => setView("home")} />
        <NavItem icon="chat" label="Chat" on={view === "chat"} onClick={() => setView("chat")}
                 open={expanded.chat} onToggle={() => toggle("chat")}>
          {chats.length === 0 && <p className="history__empty">Your conversations will appear here.</p>}
          {chats.map((c) => (
            <div key={c.id} className={`history__item${c.id === current && view === "chat" ? " is-current" : ""}`}>
              <button className="history__open" onClick={() => onOpen(c.id)} title={c.title}>{c.title}</button>
              <button className="icon-btn history__del" aria-label={`Delete “${c.title}”`}
                      onClick={() => { if (window.confirm("Delete this conversation?")) onDelete(c.id); }}>×</button>
            </div>
          ))}
        </NavItem>
        <NavItem icon="learn" label="Learn" on={view === "learn"} onClick={() => setView("learn")}
                 open={expanded.learn} onToggle={() => toggle("learn")}>
          {groups.map((g) => (
            <Child key={g.name} label={g.name.replace(/^Process synchroni[sz]ation$/, "Synchronization")} onClick={() => onLearnGroup(g.name)} count={`${g.done}/${g.total}`}
                   tone={g.done === g.total && g.total ? "mint" : g.done ? "butter" : "peach"}
                   title={`${g.done} of ${g.total} lessons done`} />
          ))}
        </NavItem>
        <NavItem icon="labs" label="Labs" on={view === "labs"} onClick={() => setView("labs")}
                 open={expanded.labs} onToggle={() => toggle("labs")}>
          {LAB_TABS.map(([id, label]) => (
            <Child key={id} label={label} on={view === "labs" && labTab === id} onClick={() => onLabTab(id)} />
          ))}
        </NavItem>
        <NavItem icon="notes" label="Notes" on={view === "notes"} onClick={() => setView("notes")}
                 count={noteCount || null} tone="butter" />
        <NavItem icon="exam" label="Exam" on={view === "exam"} onClick={() => setView("exam")} />
        <NavItem icon="progress" label="Progress" on={view === "progress"} onClick={() => setView("progress")} />
      </nav>
      <div className="settings">
        <div className="side-profile">
          <span className="avatar" aria-hidden="true">{initials}</span>
          <label className="side-profile__name"><span className="side-profile__label">Your name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} onBlur={commit}
                   onKeyDown={(e) => e.key === "Enter" && commit()} />
          </label>
        </div>
        {status?.online ? (
          <>
            <details className="model-pick">
              <summary>
                <span className="model-pick__label">Model</span>
                <span className={`model-pick__name${model && model !== status.default_model ? " is-off" : ""}`}>
                  {short(model || "")} · {model === status.default_model ? "recommended" : modelNote(model || "")}
                </span>
              </summary>
              <select aria-label="Language model" value={model || ""} onChange={(e) => setModel(e.target.value)}>
                {status.models.map((m) => (
                  <option key={m} value={m}>{short(m)} ({m === status.default_model ? "recommended" : modelNote(m)})</option>
                ))}
              </select>
              <p className="settings__foot">The fine-tuned os-tutor is the tested one; the others are here to compare.</p>
              <label className="check"><input type="checkbox" checked={showMeta} onChange={(e) => setShowMeta(e.target.checked)} />
                Show how each reply was made</label>
            </details>
            {model && status.default_model && model !== status.default_model && (
              <p className="model-warn">Not the recommended model, so replies may wander.{" "}
                <button className="link-btn" onClick={() => setModel(status.default_model)}>Use {short(status.default_model)}</button>
              </p>
            )}
            <label className="check"><input type="checkbox" checked={useLLM} onChange={(e) => setUseLLM(e.target.checked)} />
              Use the language model</label>
          </>
        ) : (
          <p className="offline">
            {status ? "Ollama isn't running, so replies use templates. Every answer is still checked by the engine. Start Ollama to get full replies."
                    : "Connecting…"}
          </p>
        )}
        <div className="seg" role="radiogroup" aria-label="Theme">
          {THEMES.map(([id, label, icon]) => (
            <button key={id} role="radio" aria-checked={theme === id} className={theme === id ? "is-on" : ""}
                    onClick={() => setTheme(id)}><Icon name={icon} size={16} />{label}</button>
          ))}
        </div>
      </div>
    </aside>
  );
}
