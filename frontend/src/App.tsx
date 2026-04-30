import { useEffect, useRef, useState } from "react";
import { apiFetch } from "./api";
import ClawdDJ from "./components/ClawdDJ";
import DropZone from "./components/DropZone";
import MixPlayer from "./components/MixPlayer";
import type { Session, SessionPoll } from "./types";

const MODELS = [
  { id: "claude-sonnet-4-6",  label: "Sonnet 4.6" },
  { id: "claude-opus-4-5",    label: "Opus 4.5"   },
  { id: "claude-haiku-4-5-20251001", label: "Haiku 4.5" },
];

export default function App() {
  const [jobId,         setJobId]         = useState<string | null>(null);
  const [session,       setSession]       = useState<Session | null>(null);
  const [audioReady,    setAudioReady]    = useState(false);
  const [loadProgress,  setLoadProgress]  = useState(0);
  const [loadTotal,     setLoadTotal]     = useState(0);
  const [planning,      setPlanning]      = useState(false);
  const [model,         setModel]         = useState(MODELS[0]!.id);
  const [minMinutes,    setMinMinutes]    = useState<number | "">("");
  const [planError,     setPlanError]     = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll session loading status until audio is ready
  useEffect(() => {
    if (!session || audioReady) return;
    pollRef.current = setInterval(async () => {
      try {
        const res  = await apiFetch(`/api/session/${session.session_id}`);
        const poll = (await res.json()) as SessionPoll;
        setLoadProgress(poll.load_progress);
        setLoadTotal(poll.load_total);
        if (poll.status === "ready") {
          setAudioReady(true);
          clearInterval(pollRef.current!);
        } else if (poll.status === "error") {
          setPlanError(poll.error ?? "Audio loading failed");
          clearInterval(pollRef.current!);
        }
      } catch { /* ignore transient errors */ }
    }, 1000);
    return () => clearInterval(pollRef.current!);
  }, [session, audioReady]);

  const handlePlan = async () => {
    if (!jobId) return;
    setPlanning(true);
    setPlanError(null);
    setSession(null);
    setAudioReady(false);
    setLoadProgress(0);
    try {
      const res  = await apiFetch("/api/plan", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ job_id: jobId, model, min_minutes: minMinutes || null }),
      });
      const data = (await res.json()) as Session & { error?: string };
      if (data.error) setPlanError(data.error);
      else { setSession(data); setLoadTotal(data.load_total); }
    } catch (e) {
      setPlanError(String(e));
    } finally {
      setPlanning(false);
    }
  };

  if (session) return <MixPlayer session={session} audioReady={audioReady} loadProgress={loadProgress} loadTotal={loadTotal} />;

  return (
    <div className="setup-root">
      {/* brand strip */}
      <div className="setup-topbar">
        <ClawdDJ state={planning ? "buffering" : "idle"} size={32} />
        <span className="setup-brand">CLAUDE DJ</span>
      </div>

      {/* center card */}
      <div className="setup-card">
        {/* Clawd hero */}
        <div className="setup-hero">
          <ClawdDJ state={planning ? "buffering" : jobId ? "paused" : "idle"} size={120} />
          <div className="setup-hero-text">
            <div className="setup-hero-title">
              {planning ? "Asking Claude to plan the mix…" : jobId ? "Ready to generate" : "Drop your tracks"}
            </div>
            <div className="setup-hero-sub">
              {planning
                ? "Analyzing energy, key, and structure"
                : jobId
                ? "Claude will listen, then orchestrate the set"
                : "Point to a folder of audio files to get started"}
            </div>
          </div>
        </div>

        <div className="setup-divider" />

        {/* Track input */}
        <div className="setup-section">
          <div className="setup-section-label">TRACKS</div>
          <DropZone onJobReady={setJobId} />
        </div>

        <div className="setup-divider" />

        {/* Mix settings */}
        <div className="setup-section">
          <div className="setup-section-label">MIX SETTINGS</div>
          <div className="setup-fields">
            <div className="setup-field">
              <label className="setup-field-label">Model</label>
              <select value={model} onChange={(e) => setModel(e.target.value)}>
                {MODELS.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
              </select>
            </div>
            <div className="setup-field">
              <label className="setup-field-label">Min length (min)</label>
              <input
                type="number" min={1} placeholder="optional"
                value={minMinutes}
                onChange={(e) => setMinMinutes(e.target.value === "" ? "" : Number(e.target.value))}
              />
            </div>
          </div>
        </div>

        {/* Generate button */}
        <button
          className="setup-generate"
          disabled={!jobId || planning}
          onClick={handlePlan}
        >
          {planning ? (
            <><span className="setup-generate-spinner" />Generating Mix…</>
          ) : (
            <>◈ Generate Mix</>
          )}
        </button>

        {planError && <div className="setup-error">{planError}</div>}
      </div>

      <style>{`
        .setup-root {
          height: 100%; display: flex; flex-direction: column;
          background: var(--bg);
        }
        .setup-topbar {
          display: flex; align-items: center; gap: 10px;
          padding: 10px 20px; border-bottom: 1px solid var(--border);
          background: var(--surface); flex-shrink: 0;
        }
        .setup-brand {
          font-size: 11px; font-weight: 700; letter-spacing: .2em;
          color: var(--orange); font-family: var(--mono);
        }

        .setup-card {
          flex: 1; display: flex; flex-direction: column; gap: 0;
          max-width: 480px; width: 100%; margin: 0 auto;
          padding: 0 20px; overflow-y: auto; justify-content: center;
          padding-top: 24px; padding-bottom: 24px;
        }

        .setup-hero {
          display: flex; flex-direction: column; align-items: center; gap: 16px;
          padding: 28px 0; text-align: center;
        }
        .setup-hero-text { display: flex; flex-direction: column; gap: 6px; }
        .setup-hero-title { font-size: 20px; font-weight: 700; color: var(--text); }
        .setup-hero-sub   { font-size: 13px; color: var(--text-2); line-height: 1.5; }

        .setup-divider { height: 1px; background: var(--border); margin: 4px 0; }

        .setup-section { padding: 18px 0; display: flex; flex-direction: column; gap: 12px; }
        .setup-section-label {
          font-size: 10px; font-weight: 700; letter-spacing: .14em;
          color: var(--text-3); text-transform: uppercase; font-family: var(--mono);
        }
        .setup-fields { display: flex; gap: 12px; }
        .setup-field { display: flex; flex-direction: column; gap: 5px; flex: 1; }
        .setup-field-label { font-size: 11px; color: var(--text-2); }
        .setup-field select, .setup-field input { width: 100%; }

        .setup-generate {
          display: flex; align-items: center; justify-content: center; gap: 8px;
          width: 100%; padding: 13px;
          background: var(--orange); color: white;
          font-size: 15px; font-weight: 700; letter-spacing: .03em;
          border-radius: var(--radius); transition: opacity .15s, transform .1s;
          margin-top: 8px;
        }
        .setup-generate:not(:disabled):hover  { opacity: .88; }
        .setup-generate:not(:disabled):active { transform: scale(.98); }
        .setup-generate:disabled { opacity: .35; cursor: not-allowed; }

        .setup-generate-spinner {
          width: 14px; height: 14px; border-radius: 50%;
          border: 2px solid rgba(255,255,255,.3); border-top-color: white;
          animation: spin .7s linear infinite; flex-shrink: 0;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        .setup-error {
          margin-top: 10px; padding: 10px 14px; border-radius: var(--radius);
          background: rgba(255,55,95,.1); border: 1px solid var(--red);
          color: var(--red); font-size: 12px; font-family: var(--mono);
        }
      `}</style>
    </div>
  );
}
