import { useEffect, useRef, useState } from "react";

export default function Composer({ onSend, busy, inputRef }) {
  const [text, setText] = useState("");
  const local = useRef(null);
  const ref = inputRef || local;
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 240) + "px";
  }, [text, ref]);
  const send = () => {
    if (!text.trim() || busy) return;
    onSend(text.trim());
    setText("");
  };
  return (
    <form className="composer" onSubmit={(e) => { e.preventDefault(); send(); }}>
      <textarea ref={ref} rows={1} value={text} placeholder="Ask a question, paste a problem, or type your answer"
                aria-label="Message" onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }} />
      <button className="send" disabled={busy || !text.trim()} aria-label="Send">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </form>
  );
}
