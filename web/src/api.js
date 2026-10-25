// Talking to the Python server (server/api.py).

export async function getJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail || ""; } catch { /* not JSON */ }
    throw new Error(detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

const post = (url, body) =>
  getJSON(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

const q = (params) =>
  Object.entries(params).filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");

export const api = {
  status: () => getJSON("/api/status"),
  chats: (sid) => getJSON(`/api/chats?sid=${encodeURIComponent(sid)}`),
  chat: (sid, id) =>
    getJSON(`/api/chat?sid=${encodeURIComponent(sid)}` + (id ? `&id=${encodeURIComponent(id)}` : "")),
  newChat: (sid) => post("/api/chat/new", { sid }),
  deleteChat: (sid, id) =>
    getJSON(`/api/chat?sid=${encodeURIComponent(sid)}&id=${encodeURIComponent(id)}`, { method: "DELETE" }),
};

// Learn mode (server/learn.py)
export const learnApi = {
  lessons: (sid) => getJSON(`/api/learn/lessons?${q({ sid })}`),
  lesson: (sid, id) => getJSON(`/api/learn/lesson?${q({ sid, id })}`),
  stage: (sid, lesson, stage) => post("/api/learn/stage", { sid, lesson, stage }),
  notes: (id, model) => getJSON(`/api/learn/notes?${q({ id, model })}`),
  tryIt: (id) => getJSON(`/api/learn/try?${q({ id })}`),
  checkMetrics: (problem, metrics) => post("/api/learn/try/check", { problem, metrics }),
  teachback: (body) => post("/api/learn/teachback", body),
  question: (sid, lesson) => post("/api/learn/question", { sid, lesson }),
  answer: (sid, lesson, answer) => post("/api/learn/answer", { sid, lesson, answer }),
  pointers: (sid, lesson) => post("/api/learn/pointers", { sid, lesson }),
  speech: () => getJSON("/api/speech"),
  transcribe: async (blob, lesson) => {
    const res = await fetch(`/api/transcribe${lesson ? `?lesson=${encodeURIComponent(lesson)}` : ""}`, { method: "POST", headers: { "Content-Type": blob.type || "audio/webm" }, body: blob });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `The server answered ${res.status}.`);
    return { text: data.text || "", unsure: !!data.unsure, reason: data.reason || "" };
  },
};

// The student's own notes (tutor/note_store.py)
const send = (url, method, body) =>
  getJSON(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const notesApi = {
  list: (sid) => getJSON(`/api/notes?${q({ sid })}`),
  add: (sid, note) => send("/api/notes", "POST", { sid, ...note }),
  update: (sid, id, changes) => send(`/api/notes/${encodeURIComponent(id)}`, "PUT", { sid, ...changes }),
  remove: (sid, id) => getJSON(`/api/notes/${encodeURIComponent(id)}?${q({ sid })}`, { method: "DELETE" }),
};

// POST and read the answer as one JSON object per line, calling onEvent for each.
export async function streamNDJSON(url, body, onEvent) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) throw new Error(`The server answered ${res.status}.`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let i;
    while ((i = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, i);
      buffer = buffer.slice(i + 1);
      if (line.trim()) onEvent(JSON.parse(line));
    }
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer));
}

// Send a chat message. The server answers with one JSON object per line:
// {"type":"start"}, then {"type":"delta","text":...} pieces, then {"type":"done","message":...}.
export const streamMessage = (body, onEvent) => streamNDJSON("/api/message", body, onEvent);

export function storage(key, fallback) {
  try {
    const v = window.localStorage.getItem(key);
    return v === null ? fallback : JSON.parse(v);
  } catch {
    return fallback;
  }
}

export function store(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* private window or blocked storage: settings just aren't remembered */
  }
}
