// A Gantt chart: one block per CPU burst, time marks underneath. The block where the student's chart first
// differs from the engine's is marked with a highlighter stroke. With `span`, the time axis is fixed from 0 to span,
// so a chart that is still being built grows from left to right (Learn mode's step-through).

// pastel (the Core palette and a few more), with dark labels: easy to read in the light and the dark theme
export const PROCESS_COLORS = ["#B1E5FC", "#FFBC99", "#B5E4CA", "#CABDFF", "#FFD88D", "#F9C6D9", "#A8E6E0", "#E5D3B3"];

export function colorFor(pid, order) {
  if (pid === "IDLE") return null;
  const i = order.indexOf(pid);
  if (i >= 0) return PROCESS_COLORS[i % PROCESS_COLORS.length];
  let h = 0;
  for (const ch of pid) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PROCESS_COLORS[h % PROCESS_COLORS.length];
}

export default function Gantt({ segments = [], order = [], highlight = null, title = null, compact = false, span = null }) {
  if (!segments.length && !span) return null;
  const start = span ? 0 : segments[0][1];
  const end = segments.length ? segments[segments.length - 1][2] : 0;
  const total = Math.max((span || end) - start, 1);
  // time marks: every boundary, skipping ones that would collide with their neighbour
  const times = [start, ...segments.map((sg) => sg[2])];
  const marks = [];
  times.forEach((t, i) => {
    const pct = ((t - start) / total) * 100;
    const prev = marks.length ? marks[marks.length - 1].pct : -100;
    if (i === times.length - 1) {
      if (pct - prev < 3.2 && marks.length > 1) marks.pop();
      marks.push({ t, pct });
    } else if (pct - prev >= 3.2 && 100 - pct >= 3.2) {
      marks.push({ t, pct });
    }
  });
  const rest = span ? Math.max(span - end, 0) : 0;
  return (
    <figure className={`gantt${compact ? " gantt--compact" : ""}${span ? " gantt--growing" : ""}`}>
      {title && <figcaption className="gantt__title">{title}</figcaption>}
      <div className="gantt__track" role="img"
           aria-label={segments.length ? segments.map(([p, s, e]) => `${p === "IDLE" ? "idle" : p} ${s} to ${e}`).join(", ") : "empty chart"}>
        {segments.map(([pid, s, e], k) => {
          const color = colorFor(pid, order);
          const hl = highlight !== null && highlight !== undefined && s <= highlight && highlight < e;
          return (
            <div key={k}
                 className={`gantt__block${pid === "IDLE" ? " gantt__block--idle" : ""}${hl ? " gantt__block--hl" : ""}`}
                 style={{ flexGrow: e - s, flexBasis: 0, background: color || undefined }}
                 title={`${pid === "IDLE" ? "CPU idle" : pid}: ${s} to ${e}`}>
              {hl && <span className="gantt__flag">first difference</span>}
              <span className="gantt__label">{pid === "IDLE" ? "idle" : pid}</span>
            </div>
          );
        })}
        {rest > 0 && <div className="gantt__rest" style={{ flexGrow: rest, flexBasis: 0 }} aria-hidden="true" />}
      </div>
      <div className="gantt__ticks" aria-hidden="true">
        {marks.map((m) => (
          <span key={`${m.t}-${m.pct}`} style={{ left: `${m.pct}%` }}>{m.t}</span>
        ))}
      </div>
    </figure>
  );
}
