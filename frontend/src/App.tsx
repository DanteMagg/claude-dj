import { useState } from "react";
import { apiFetch } from "./api";
import DropZone from "./components/DropZone";
import MixPlayer from "./components/MixPlayer";
import type { Session } from "./types";

const MODELS = [
  "claude-sonnet-4-6",
  "claude-opus-4-5",
  "claude-haiku-4-5",
];

export default function App() {
  const [jobId,      setJobId]      = useState<string | null>(null);
  const [session,    setSession]    = useState<Session | null>(null);
  const [planning,   setPlanning]   = useState(false);
  const [model,      setModel]      = useState(MODELS[0]!);
  const [minMinutes, setMinMinutes] = useState<number | "">("");
  const [planError,  setPlanError]  = useState<string | null>(null);

  const handlePlan = async () => {
    if (!jobId) return;
    setPlanning(true);
    setPlanError(null);
    setSession(null);
    try {
      const res = await apiFetch("/api/plan", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({
          job_id:      jobId,
          model,
          min_minutes: minMinutes === "" ? null : minMinutes,
        }),
      });
      const data = (await res.json()) as Session & { error?: string };
      if (data.error) setPlanError(data.error);
      else setSession(data);
    } catch (e) {
      setPlanError(String(e));
    } finally {
      setPlanning(false);
    }
  };

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="logo">
          <span className="logo-icon">◈</span>
          <span className="logo-text">Claude DJ</span>
        </div>

        <section className="section">
          <div className="section-title">Tracks</div>
          <DropZone onJobReady={setJobId} />
        </section>

        <section className="section">
          <div className="section-title">Mix</div>
          <div className="field">
            <label className="field-label">Model</label>
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              {MODELS.map((m) => <option key={m}>{m}</option>)}
            </select>
          </div>
          <div className="field">
            <label className="field-label">Min minutes</label>
            <input
              type="number"
              min={1}
              placeholder="optional"
              value={minMinutes}
              onChange={(e) =>
                setMinMinutes(e.target.value === "" ? "" : Number(e.target.value))
              }
            />
          </div>
          <button
            className="btn-generate"
            disabled={!jobId || planning}
            onClick={handlePlan}
          >
            {planning ? "Asking Claude…" : "Generate Mix"}
          </button>
          {planError && <p className="plan-error">{planError}</p>}
        </section>
      </aside>

      {/* Main */}
      <main className="main">
        {session ? (
          <MixPlayer session={session} />
        ) : (
          <div className="empty-state">
            <span className="empty-icon">◈</span>
            <p className="empty-title">No mix loaded</p>
            <p className="empty-sub">
              {jobId
                ? "Click Generate Mix to ask Claude to plan the set."
                : "Choose a folder of tracks to get started."}
            </p>
          </div>
        )}
      </main>

      <style>{`
        .app { display: flex; height: 100vh; overflow: hidden; }
        .sidebar {
          width: 280px; flex-shrink: 0;
          background: var(--surface); border-right: 1px solid var(--border);
          display: flex; flex-direction: column; overflow-y: auto;
        }
        .logo {
          display: flex; align-items: center; gap: 10px;
          padding: 20px 18px 16px; border-bottom: 1px solid var(--border);
        }
        .logo-icon { font-size: 22px; color: var(--accent); }
        .logo-text { font-size: 16px; font-weight: 700; letter-spacing: .02em; }
        .section {
          padding: 16px 18px; display: flex; flex-direction: column;
          gap: 10px; border-bottom: 1px solid var(--border);
        }
        .section-title {
          font-size: 11px; font-weight: 600; text-transform: uppercase;
          letter-spacing: .09em; color: var(--text-2);
        }
        .field { display: flex; flex-direction: column; gap: 4px; }
        .field-label { font-size: 12px; color: var(--text-2); }
        .field select, .field input { width: 100%; }
        .btn-generate {
          padding: 9px 0; background: var(--accent); color: #fff;
          font-weight: 600; border-radius: var(--radius); font-size: 14px;
          transition: opacity .15s; width: 100%;
        }
        .btn-generate:disabled { opacity: .4; cursor: not-allowed; }
        .btn-generate:not(:disabled):hover { opacity: .85; }
        .plan-error { font-size: 12px; color: #ff4d4d; }
        .main {
          flex: 1; overflow: hidden; display: flex;
          flex-direction: column; padding: 20px;
        }
        .empty-state {
          flex: 1; display: flex; flex-direction: column;
          align-items: center; justify-content: center; gap: 10px; opacity: .4;
        }
        .empty-icon { font-size: 48px; color: var(--accent); }
        .empty-title { font-size: 18px; font-weight: 600; }
        .empty-sub {
          font-size: 13px; color: var(--text-2);
          text-align: center; max-width: 300px;
        }
      `}</style>
    </div>
  );
}
