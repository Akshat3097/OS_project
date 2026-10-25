// Theory as an archival document: a grainy sheet with punch holes, a ruled margin with a typed note, a stamped file
// number, an italic serif title, a vertical serial number and folder tabs on the edge (the look the student picked
// for theory text). The sheets stay light in dark mode, like real paper on a dark desk.
export default function Paper({ title, kicker, note, file, serial, tabs = [], tone = "white", holes = true,
                                className = "", children }) {
  const cls = ["paper", `paper--${tone}`, note ? "" : "paper--nonote", holes ? "" : "paper--noholes",
               tabs.length ? "paper--tabbed" : "", className].filter(Boolean).join(" ");
  return (
    <section className={cls}>
      {holes && <div className="paper__holes" aria-hidden="true"><i /><i /><i /></div>}
      {note && <aside className="paper__note">{note}</aside>}
      <div className="paper__main">
        {file && <span className="paper__stamp">{file}</span>}
        {kicker && <p className="paper__kicker">{kicker}</p>}
        {title && <h2 className="paper__title">{title}</h2>}
        <div className="paper__body">{children}</div>
      </div>
      {serial && <span className="paper__serial" aria-hidden="true">{serial}</span>}
      {tabs.length > 0 && (
        <div className="paper__tabs" aria-hidden="true">
          {tabs.map((t) => <span key={t.label} className={`paper__tab paper__tab--${t.tone || "red"}`}>{t.label}</span>)}
        </div>
      )}
    </section>
  );
}

// A yellow slip like a receipt, with a torn top edge and a paperclip, for short lists (real-life examples).
export function Slip({ heading, sub, children }) {
  return (
    <div className="slip-wrap">
      <svg className="slip__clip" viewBox="0 0 24 64" width="20" height="54" aria-hidden="true">
        <path d="M8 22V9a4 4 0 0 1 8 0v39a7 7 0 0 1-14 0V15" fill="none" stroke="currentColor" strokeWidth="2.2"
              strokeLinecap="round" />
      </svg>
      <section className="slip">
        <p className="slip__heading">{heading}</p>
        {sub && <p className="slip__sub">{sub}</p>}
        <div className="slip__body">{children}</div>
      </section>
    </div>
  );
}

// The cobalt folder the sheets sit in, with a labelled tab on top.
export function Folder({ label, children }) {
  return (
    <div className="folder">
      {label && <span className="folder__label">{label}</span>}
      {children}
    </div>
  );
}
