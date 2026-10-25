// Stage 3: the student explains the topic for about a minute. Speech is recorded in the browser and turned into
// text on the laptop by Whisper (nothing leaves the machine); the student can correct the text before it is checked.
import { useEffect, useRef, useState } from "react";
import { learnApi, storage } from "../../api.js";
import Thinking from "../Thinking.jsx";

const TARGET_WORDS = 120;   // about one minute of speaking
const MAX_SECONDS = 90;
const RATING = { clear: "Clear", partial: "Partly there", missing: "Missing" };

function useMics() {
  const [mics, setMics] = useState([]);
  const refresh = () => navigator.mediaDevices?.enumerateDevices?.()
    .then((ds) => setMics(ds.filter((d) => d.kind === "audioinput" && !["default", "communications"].includes(d.deviceId))))
    .catch(() => setMics([]));
  useEffect(() => {
    refresh();
    navigator.mediaDevices?.addEventListener?.("devicechange", refresh);
    return () => navigator.mediaDevices?.removeEventListener?.("devicechange", refresh);
  }, []);
  return [mics, refresh];
}

// A live input level while recording, so a muted or wrong microphone shows at once.
function startMeter(stream, onLevel) {
  try {
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    let raf = 0, last = 0;
    const tick = (t) => {
      analyser.getFloatTimeDomainData(buf);
      if (t - last > 80) {
        last = t;
        onLevel(Math.min(1, Math.sqrt(buf.reduce((s, x) => s + x * x, 0) / buf.length) * 8));
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); ctx.close().catch(() => {}); };
  } catch {
    return () => {};
  }
}

function Recorder({ onText, disabled, lessonId }) {
  const [speech, setSpeech] = useState(null);       // {available} from the server
  const [state, setState] = useState("idle");       // idle | recording | transcribing
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState(null);
  const [note, setNote] = useState(null);           // the recording was unclear: check the text
  const [level, setLevel] = useState(0);
  const [clip, setClip] = useState(null);           // the last recording, to play back
  const [mics, refreshMics] = useMics();
  const [micId, setMicId] = useState(() => storage("micId", ""));
  const rec = useRef(null);
  const timer = useRef(null);
  const meter = useRef(() => {});
  const loudest = useRef(0);

  useEffect(() => {
    learnApi.speech().then(setSpeech).catch(() => setSpeech({ available: false }));
    return () => { clearInterval(timer.current); meter.current(); rec.current?.stream?.getTracks().forEach((t) => t.stop()); };
  }, []);
  useEffect(() => () => clip && URL.revokeObjectURL(clip), [clip]);

  const pickMic = (id) => {
    setMicId(id);
    try { localStorage.setItem("micId", JSON.stringify(id)); } catch { /* private window */ }
  };

  const start = async () => {
    setError(null);
    setNote(null);
    const audio = { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 };
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: micId ? { ...audio, deviceId: { exact: micId } } : audio });
    } catch (e) {
      if (micId && e.name === "OverconstrainedError") {           // the chosen microphone was unplugged
        pickMic("");
        setError("That microphone isn't connected any more, so the default one is selected. Press Record again.");
      } else {
        setError("The browser didn't allow the microphone. Allow it in the address bar, or type below (Win + H also dictates).");
      }
      return;
    }
    refreshMics();                                  // names are only visible once the microphone is allowed
    const chunks = [];
    let mr;
    try {
      // WebM/Opus in Chrome and Edge, Ogg/Opus in Firefox; the server decodes either
      const type = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/webm"].find((t) => MediaRecorder.isTypeSupported(t));
      mr = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    } catch (e) {
      stream.getTracks().forEach((t) => t.stop());
      setError(`This browser can't record audio here (${e.message}). Type below, or use Win + H to dictate.`);
      return;
    }
    loudest.current = 0;
    meter.current = startMeter(stream, (v) => { setLevel(v); loudest.current = Math.max(loudest.current, v); });
    mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mr.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      meter.current();
      setLevel(0);
      clearInterval(timer.current);
      const blob = new Blob(chunks, { type: mr.mimeType || "audio/webm" });
      setClip(URL.createObjectURL(blob));
      setState("transcribing");
      try {
        const r = await learnApi.transcribe(blob, lessonId);
        if (r.reason === "silent") {
          setError("The recording is silent: this microphone didn't hear you. Choose another microphone, then record again.");
        } else if (r.text) {
          onText(r.text);
          if (r.unsure) setNote("Parts of the recording were unclear, so some words may be wrong. Play it back and fix the text on the board.");
        } else {
          setError("I couldn't hear any words. Try again a little closer to the microphone.");
        }
      } catch (e) {
        setError(e.message);
      }
      setState("idle");
    };
    rec.current = mr;
    mr.start(1000);                                 // a chunk every second, so a long recording is never lost
    setSeconds(0);
    setState("recording");
    timer.current = setInterval(() => setSeconds((s) => {
      if (s + 1 >= MAX_SECONDS) mr.state === "recording" && mr.stop();
      return s + 1;
    }), 1000);
  };
  const stop = () => rec.current?.state === "recording" && rec.current.stop();

  if (speech && !speech.available) {
    return (
      <p className="muted small">
        To speak instead of typing, click in the box and press <b>Win + H</b> (Windows voice typing). The in-app microphone
        needs <code>faster-whisper</code> installed on the laptop.
      </p>
    );
  }
  const canRecord = typeof window !== "undefined" && window.MediaRecorder && navigator.mediaDevices;
  const deaf = state === "recording" && seconds >= 4 && loudest.current < 0.05;
  return (
    <div className="recorder">
      <div className="recorder__row">
        {state === "recording" ? (
          <button className="rec-btn is-on" onClick={stop}>
            <span className="rec-dot" aria-hidden="true" /> Stop · {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
          </button>
        ) : (
          <button className="rec-btn" onClick={start} disabled={disabled || !speech || !canRecord || state === "transcribing"}>
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Zm-6 9a6 6 0 0 0 12 0M12 18v3" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            Record your explanation
          </button>
        )}
        {state === "recording" && (
          <span className="level" role="meter" aria-label="Microphone level" aria-valuemin={0} aria-valuemax={100}
                aria-valuenow={Math.round(level * 100)}><i style={{ width: `${Math.round(level * 100)}%` }} /></span>
        )}
        {mics.length > 1 && (
          <label className="recorder__mic">
            <span>Microphone</span>
            <select value={micId} onChange={(e) => pickMic(e.target.value)} disabled={state !== "idle"}>
              <option value="">Windows default</option>
              {mics.map((m, i) => <option key={m.deviceId} value={m.deviceId}>{m.label || `Microphone ${i + 1}`}</option>)}
            </select>
          </label>
        )}
      </div>
      {state === "recording" && !deaf && <span className="muted small">Speak for about a minute, then press Stop.</span>}
      {deaf && <p className="error-text">The microphone isn't picking up your voice. Stop, choose another microphone, and try again.</p>}
      {state === "transcribing" && <Thinking label="Turning your voice into text (the first time takes longer)" />}
      {error && <p className="error-text">{error}</p>}
      {note && <p className="recorder__note">{note}</p>}
      {clip && state === "idle" && (
        <label className="recorder__playback"><span>Play back what was recorded</span><audio controls src={clip} /></label>
      )}
    </div>
  );
}

// The explanation is written in chalk on a blackboard, with the lesson's prompts chalked at the top.
function Chalkboard({ title, prompts, children }) {
  const today = new Date().toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
  return (
    <div className="board-frame">
      <div className="chalkboard">
        <p className="chalk__date" aria-hidden="true">{today}</p>
        <h2 className="chalk__title">{title}</h2>
        {prompts?.length > 0 && <ul className="chalk__prompts">{prompts.map((p) => <li key={p}>{p}</li>)}</ul>}
        {children}
      </div>
      <div className="chalk__tray" aria-hidden="true">
        <i className="chalk__stick" /><i className="chalk__stick chalk__stick--yellow" /><i className="chalk__duster" />
      </div>
    </div>
  );
}

export function AssessmentView({ a }) {
  return (
    <section className="assessment" aria-live="polite">
      <p className="assessment__head">
        {a.clear
          ? <>You clearly covered <b>{a.clear} of {a.total}</b> key ideas.</>
          : <>The key ideas didn't come through clearly yet. That's normal on a first try.</>}
        {" "}Next, one question on the idea that needs the most work.
      </p>
      <ul className="ideas">
        {a.ideas.map((i) => (
          <li key={i.id}>
            <span className={`rating rating--${i.rating}`}>{RATING[i.rating]}</span>
            <span>{i.statement}{i.evidence && <span className="evidence">You said: “{i.evidence}”</span>}</span>
          </li>
        ))}
      </ul>
      {a.did_well && <p className="muted small">What you explained well: {a.did_well}</p>}
      {a.misconceptions.length > 0 && <p className="error-text">Misconception to fix: {a.misconceptions.join("; ")}</p>}
      <p className="muted small">Checked by: {a.source} · {a.words} words</p>
    </section>
  );
}

export default function ExplainBack({ lesson, sid, model, assessment, onAssessed }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;

  const check = async () => {
    setBusy(true);
    setError(null);
    try {
      onAssessed(await learnApi.teachback({ sid, lesson: lesson.id, text, model, use_llm: !!model }));
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };

  if (assessment) {
    return (
      <div className="explain">
        {text.trim() && (
          <Chalkboard title={`Explain: ${lesson.title}`}>
            <p className="chalk__text">{text.trim()}</p>
          </Chalkboard>
        )}
        <AssessmentView a={assessment} />
      </div>
    );
  }
  return (
    <div className="explain">
      <p>Now <b>you</b> teach it. Explain <b>{lesson.title}</b> in your own words for about a minute, as if to a friend who
        missed the class. Try not to look back at the lesson.</p>
      <Recorder lessonId={lesson.id} disabled={busy} onText={(t) => setText((cur) => (cur.trim() ? `${cur.trim()} ${t}` : t))} />
      <Chalkboard title={`Explain: ${lesson.title}`} prompts={lesson.prompts}>
        <label className="explain__box chalk__write">
          <span className="chalk__label">Your explanation (fix anything the speech-to-text misheard)</span>
          <textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} disabled={busy} spellCheck={false}
                    placeholder="Record above, use voice typing (Win + H), or write here…" />
        </label>
      </Chalkboard>
      <div className="wordmeter" aria-label={`${words} words`}>
        <span className="wordmeter__bar"><i style={{ width: `${Math.min(100, (words / TARGET_WORDS) * 100)}%` }} /></span>
        <span className="muted small">{words} words · about {TARGET_WORDS} is one minute of speaking{words < 15 ? " · at least 15 to check" : ""}</span>
      </div>
      {error && <p className="error-text">{error}</p>}
      <button className="primary" disabled={busy || words < 15} onClick={check}>
        {busy ? "Listening for the key ideas…" : "Check my understanding"}
      </button>
    </div>
  );
}
