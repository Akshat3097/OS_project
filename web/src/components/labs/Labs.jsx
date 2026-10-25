// Labs: the OS Engine to play with directly. Four tabs; every number comes from the server (server/labs.py).
import { useEffect, useState } from "react";
import { getJSON, storage, store } from "../../api.js";
import BankersLab from "./BankersLab.jsx";
import DeadlockLab from "./DeadlockLab.jsx";
import SchedulerLab from "./SchedulerLab.jsx";
import SemaphoreLab from "./SemaphoreLab.jsx";

const TABS = [
  ["scheduler", "Scheduler", "One set of processes through all six algorithms, compared side by side."],
  ["bankers", "Banker's algorithm", "Check a state for safety step by step, and test a resource request."],
  ["semaphores", "Semaphores", "Run wait() and signal() in any order and watch who blocks and who wakes."],
  ["deadlocks", "Deadlocks", "Draw a resource-allocation graph and find out whether it is deadlocked."],
];

export const post = (url, body) =>
  getJSON(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export default function Labs({ onTab }) {
  const [tab, setTabState] = useState(() => storage("labTab", "scheduler"));
  const [presets, setPresets] = useState(null);
  const setTab = (t) => { setTabState(t); store("labTab", t); onTab?.(t); };
  useEffect(() => { getJSON("/api/labs/presets").then(setPresets).catch(() => setPresets({})); }, []);
  const about = TABS.find(([id]) => id === tab);
  return (
    <div className="labs">
      <h1>Labs</h1>
      <p className="hero__sub">Try your own numbers. The OS Engine works out every answer, the same engine that checks your work in the chat.</p>
      <div className="tabs" role="tablist" aria-label="Labs">
        {TABS.map(([id, name]) => (
          <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "is-on" : ""} onClick={() => setTab(id)}>{name}</button>
        ))}
      </div>
      <p className="muted labs__about">{about[2]}</p>
      {!presets ? <p className="loading">Loading…</p> : (
        <>
          {tab === "scheduler" && <SchedulerLab presets={presets.scheduler || []} />}
          {tab === "bankers" && <BankersLab presets={presets.bankers || []} />}
          {tab === "semaphores" && <SemaphoreLab presets={presets.semaphores || []} />}
          {tab === "deadlocks" && <DeadlockLab presets={presets.deadlocks || []} />}
        </>
      )}
    </div>
  );
}
