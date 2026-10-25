// A lecture clip: the YouTube player starts and stops at the part about this topic. Browsers only let a page start a
// video with sound after a click, so it is cued, not autoplayed. Offline, the transcript excerpt and the link remain.
// A whole video (no transcript to cue it) can have chapters: section times from notes on the lecture, approximate,
// so they are offered as buttons to jump to rather than used as the starting point.
import { useEffect, useState } from "react";

function embed(c, jump) {
  if (jump != null) return `https://www.youtube-nocookie.com/embed/${c.video}?start=${jump}&autoplay=1&rel=0&modestbranding=1`;
  const end = c.end == null ? "" : `&end=${c.end}`;        // no end: the whole video (no transcript to cue it)
  return `https://www.youtube-nocookie.com/embed/${c.video}?start=${c.start}${end}&rel=0&modestbranding=1`;
}

const mmss = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

export default function VideoClips({ clips }) {
  const [i, setI] = useState(0);
  const [jump, setJump] = useState(null);               // seconds, after a chapter button is clicked
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true), down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => { window.removeEventListener("online", up); window.removeEventListener("offline", down); };
  }, []);
  if (!clips?.length) return null;
  const c = clips[Math.min(i, clips.length - 1)];
  const chapters = c.chapters || [];
  return (
    <section className="clip" aria-label="Lecture clip">
      <p className="clip__label">Watch it explained · {c.title} · {c.when}</p>
      {online ? (
        <div className="clip__frame">
          <iframe key={`${c.video}-${c.start}-${jump}`} src={embed(c, jump)} title={`${c.title}, ${c.when}`} loading="lazy"
                  allow="accelerometer; autoplay; encrypted-media; picture-in-picture; fullscreen" allowFullScreen />
        </div>
      ) : (
        <p className="muted small">You're offline, so the video can't play here. What the lecture says in this part:</p>
      )}
      {online && chapters.length > 1 && (
        <div className="clip__chapters">
          <span className="muted small">Jump to (times are approximate):</span>
          {chapters.map((ch) => (
            <button key={ch.start} className={`chip${jump === ch.start ? " is-on" : ""}`} onClick={() => setJump(ch.start)}>
              {mmss(ch.start)} · {ch.label}
            </button>
          ))}
        </div>
      )}
      <div className="clip__foot">
        <a href={`https://youtu.be/${c.video}?t=${jump ?? c.start}`} target="_blank" rel="noreferrer">
          Open on YouTube{(jump ?? c.start) ? ` at ${mmss(jump ?? c.start)}` : ""}</a>
        {clips.length > 1 && clips.map((x, k) => k !== i && (
          <button key={k} className="link-btn" onClick={() => { setI(k); setJump(null); }}>Another clip: {x.title} · {x.when}</button>
        ))}
      </div>
      <details className="more" open={!online}>
        <summary>{chapters.length ? "What this lecture covers" : "What is said in this part"}</summary>
        <p className="sources__text">{c.excerpt || (chapters.length
          ? chapters.map((ch) => `${mmss(ch.start)} ${ch.label}`).join(" · ")
          : "There is no transcript for this video yet.")}</p>
      </details>
    </section>
  );
}
