import { useCallback, useEffect, useRef, useState } from "react";
import { api, learnApi, notesApi, storage, store, streamMessage } from "./api.js";
import AnswerSheet from "./components/AnswerSheet.jsx";
import Composer from "./components/Composer.jsx";
import Exam from "./components/Exam.jsx";
import Hero from "./components/Hero.jsx";
import Home from "./components/Home.jsx";
import Labs from "./components/labs/Labs.jsx";
import Learn from "./components/learn/Learn.jsx";
import Message from "./components/Message.jsx";
import Notes from "./components/Notes.jsx";
import Progress from "./components/Progress.jsx";
import Sidebar from "./components/Sidebar.jsx";
import { groupId } from "./components/learn/Learn.jsx";

const PRACTICE_REQUEST = {
  FCFS: "FCFS", SJF: "SJF", SRTF: "SRTF", RR: "Round Robin", PRIORITY_NP: "priority scheduling",
  PRIORITY_P: "priority scheduling", SEMAPHORE: "semaphore", BANKERS: "Banker's algorithm",
};

export default function App() {
  const [sid, setSidState] = useState(() => storage("sid", "demo"));
  const [view, setViewState] = useState(() => storage("view", "home"));   // "home" | "chat" | "learn" | "labs" | "exam" | "progress"
  const [lessonId, setLessonIdState] = useState(() => storage("lesson", null));
  const [theme, setThemeState] = useState(() => storage("theme", "system"));
  const [status, setStatus] = useState(null);
  // not remembered between page loads: every reload starts the next person on the recommended model, with the LLM on
  const [model, setModel] = useState(null);
  const [useLLM, setUseLLM] = useState(true);
  const [showMeta, setShowMetaState] = useState(() => storage("showMeta", false));
  const [chats, setChats] = useState([]);
  const [chat, setChat] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [drawer, setDrawer] = useState(false);
  const [groups, setGroups] = useState([]);        // lesson groups with how many are done, for the sidebar
  const [labTab, setLabTab] = useState(() => storage("labTab", "scheduler"));
  const [labKey, setLabKey] = useState(0);
  const [noteCount, setNoteCount] = useState(null);
  const scroller = useRef(null);
  const stick = useRef(true);
  const input = useRef(null);
  const queued = useRef(null);      // a message to send as soon as a fresh chat is open

  const remember = (key, setter) => (v) => { setter(v); store(key, v); };
  const setSid = remember("sid", setSidState);
  const setView = remember("view", setViewState);
  const setLessonId = remember("lesson", setLessonIdState);
  const setTheme = remember("theme", setThemeState);

  useEffect(() => {
    if (theme === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
  }, [theme]);
  const setShowMeta = remember("showMeta", setShowMetaState);

  useEffect(() => {
    api.status().then((s) => {
      setStatus(s);
      setModel(s.default_model);
    }).catch(() => setStatus({ online: false, models: [], notes: { chunks: 0 } }));
  }, []);

  const refreshChats = useCallback(() => api.chats(sid).then(setChats).catch(() => {}), [sid]);

  useEffect(() => {
    learnApi.lessons(sid).then((d) => {
      const names = [...new Set(d.lessons.map((l) => l.group))];
      setGroups(names.map((g) => {
        const ls = d.lessons.filter((l) => l.group === g);
        return { name: g, done: ls.filter((l) => l.completed).length, total: ls.length };
      }));
    }).catch(() => {});
  }, [sid, view]);
  useEffect(() => { notesApi.list(sid).then((d) => setNoteCount(d.notes.length)).catch(() => {}); }, [sid]);

  // "Save to notes" under a tutor reply: the student's question becomes the title
  const saveNote = useCallback(async (reply, question) => {
    const title = (question?.content || "").replace(/\s+/g, " ").trim().slice(0, 80);
    await notesApi.add(sid, { text: reply.content, title, source: "Saved from the chat" });
    setNoteCount((n) => (n || 0) + 1);
  }, [sid]);

  useEffect(() => {
    setChat(null);
    api.chat(sid).then(setChat).catch(() => setError("The tutor's server isn't answering. Is `python -m server` still running?"));
    refreshChats();
  }, [sid, refreshChats]);

  // keep the newest message in view while it streams, unless the student scrolled up to read
  useEffect(() => {
    const el = scroller.current;
    if (el && stick.current && view === "chat") el.scrollTop = el.scrollHeight;
  }, [chat, busy, view]);
  useEffect(() => { if (view !== "chat") scroller.current?.scrollTo({ top: 0 }); }, [view]);
  const onScroll = () => {
    const el = scroller.current;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  };

  const send = useCallback(async (text, structured = null) => {
    if (busy || !chat) return;
    setBusy(true);
    setError(null);
    stick.current = true;
    const pending = { role: "assistant", content: "", pending: true, cards: [] };
    setChat((c) => ({ ...c, form: null, messages: [...c.messages, { role: "user", content: text }, pending] }));
    const patchLast = (fn) => setChat((c) => {
      const msgs = c.messages.slice();
      msgs[msgs.length - 1] = fn(msgs[msgs.length - 1]);
      return { ...c, messages: msgs };
    });
    try {
      await streamMessage({ sid, id: chat.id, text, structured, model: status?.online ? model : null, use_llm: useLLM },
        (ev) => {
          if (ev.type === "meta") patchLast((m) => ({ ...m, meta: ev.meta }));
          else if (ev.type === "delta") patchLast((m) => ({ ...m, content: m.content + ev.text }));
          else if (ev.type === "done") {
            setChat((c) => {
              const msgs = c.messages.slice();
              msgs[msgs.length - 1] = ev.message;
              return { ...c, id: ev.chat.id, title: ev.chat.title, form: ev.form, messages: msgs };
            });
          } else if (ev.type === "error") {
            patchLast((m) => ({ ...m, pending: false, content: m.content || "Something went wrong while answering that.", meta: { error: ev.text } }));
          }
        });
      refreshChats();
    } catch (e) {
      patchLast((m) => ({ ...m, pending: false, content: "I couldn't reach the tutor's server. Check that `python -m server` is still running, then try again." }));
    } finally {
      setBusy(false);
      setTimeout(() => input.current?.focus(), 0);
    }
  }, [busy, chat, sid, model, useLLM, status, refreshChats]);

  useEffect(() => {
    if (chat && queued.current && !busy) {
      const text = queued.current;
      queued.current = null;
      send(text);
    }
  }, [chat, busy, send]);

  const openChat = (id) => { setDrawer(false); setView("chat"); api.chat(sid, id).then(setChat); };
  const newChat = () => { setDrawer(false); setView("chat"); api.newChat(sid).then(setChat); };
  const deleteChat = async (id) => {
    await api.deleteChat(sid, id);
    await refreshChats();
    if (chat?.id === id) newChat();
  };
  // "Practise" from a lesson (a topic: an easy problem) or the dashboard (a full request): a fresh chat that starts with it
  const practise = (what) => {
    queued.current = PRACTICE_REQUEST[what] ? `Give me an easy ${PRACTICE_REQUEST[what]} problem` : what;
    newChat();
  };
  const scrollTop = () => scroller.current?.scrollTo({ top: 0 });
  const go = (v) => { setDrawer(false); setView(v); if (v === "learn") setLessonId(null); };
  const openLearnGroup = (name) => {
    go("learn");
    setTimeout(() => document.getElementById(groupId(name))?.scrollIntoView({ behavior: "smooth", block: "start" }), 120);
  };
  const openLab = (id) => { store("labTab", id); setLabTab(id); setLabKey((k) => k + 1); go("labs"); };
  const openLesson = (id) => { go("learn"); setLessonId(id); };

  const msgs = chat?.messages || [];
  const fresh = msgs.length <= 1;
  const welcome = msgs[0];

  return (
    <div className="app">
      <Sidebar sid={sid} setSid={setSid} chats={chats} current={chat?.id} onOpen={openChat} onNew={newChat}
               onDelete={deleteChat} status={status} model={model} setModel={setModel} useLLM={useLLM}
               setUseLLM={setUseLLM} showMeta={showMeta} setShowMeta={setShowMeta} open={drawer}
               onClose={() => setDrawer(false)} view={view} setView={go}
               theme={theme} setTheme={setTheme} groups={groups} onLearnGroup={openLearnGroup}
               labTab={labTab} onLabTab={openLab} noteCount={noteCount} />
      {drawer && <div className="scrim" onClick={() => setDrawer(false)} />}
      <main className="main">
        <header className="topbar">
          <button className="icon-btn" aria-label="Open menu" onClick={() => setDrawer(true)}>
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
          </button>
          <span className="topbar__title">{{ home: "Home", learn: "Learn", labs: "Labs", exam: "Exam", progress: "Progress", notes: "Notes" }[view] || chat?.title || "OS Tutor"}</span>
        </header>
        {view === "home" ? (
          <div className="scroll" ref={scroller}>
            <div className="column column--home">
              <Home sid={sid} chats={chats} onLesson={openLesson} onChat={newChat} onOpenChat={openChat} onPractice={practise}
                    onExam={() => go("exam")} onLabs={() => go("labs")} onLearn={openLearnGroup} onProgress={() => go("progress")} />
            </div>
          </div>
        ) : view === "notes" ? (
          <div className="scroll" ref={scroller}>
            <div className="column column--home"><Notes sid={sid} onCount={setNoteCount} /></div>
          </div>
        ) : view === "exam" ? (
          <div className="scroll" ref={scroller}>
            <div className="column column--wide"><Exam sid={sid} onProgress={() => setView("progress")} scrollTop={scrollTop} /></div>
          </div>
        ) : view === "labs" ? (
          <div className="scroll" ref={scroller}>
            <div className="column column--wide"><Labs key={labKey} onTab={setLabTab} /></div>
          </div>
        ) : view === "progress" ? (
          <div className="scroll" ref={scroller}>
            <div className="column column--wide">
              <Progress sid={sid} onPractice={practise} onLearn={() => setView("learn")} onChat={() => setView("chat")} />
            </div>
          </div>
        ) : view === "learn" ? (
          <div className="scroll" ref={scroller}>
            <div className="column column--wide">
              <Learn sid={sid} model={model} useLLM={useLLM} online={!!status?.online} lessonId={lessonId}
                     setLessonId={(id) => { setLessonId(id); scrollTop(); }} onPractice={practise} scrollTop={scrollTop} />
            </div>
          </div>
        ) : (<>
        <div className="scroll" ref={scroller} onScroll={onScroll}>
          <div className="column">
            {error && <p className="banner">{error}</p>}
            {chat && fresh && (
              <Hero name={sid} welcome={welcome?.content?.startsWith("Welcome back")}
                    suggestions={welcome?.suggestions || []} onSend={send}
                    onGo={(v) => { setView(v); if (v === "learn") setLessonId(null); }} />
            )}
            {chat && !fresh && msgs.map((m, i) => (
              <Message key={i} message={m} isLast={i === msgs.length - 1} onSend={send} busy={busy} showMeta={showMeta}
                       onSaveNote={m.role === "assistant" && i > 0 ? () => saveNote(m, msgs[i - 1]) : null} />
            ))}
            {chat && !busy && <AnswerSheet key={chat.form?.key} form={chat.form} onSubmit={send} busy={busy} />}
          </div>
        </div>
        <div className="dock">
          <div className="column">
            <Composer onSend={send} busy={busy || !chat} inputRef={input} />
            <p className="dock__note">Every number is checked by the OS Engine. Explanations come from the language model and can still be imperfect.</p>
          </div>
        </div>
        </>)}
      </main>
    </div>
  );
}
