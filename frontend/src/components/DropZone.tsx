import { useCallback, useRef, useState } from "react";
import { apiFetch } from "../api";
import type { AnalysisJob } from "../types";

interface Props {
  onJobReady: (jobId: string) => void;
}

declare global {
  interface Window {
    electron?: {
      selectFolder: () => Promise<string | null>;
      showInFolder: (path: string) => void;
      isElectron: true;
    };
  }
}

export default function DropZone({ onJobReady }: Props) {
  const [job,    setJob]    = useState<AnalysisJob | null>(null);
  const [jobId,  setJobId]  = useState<string | null>(null);
  const [folder, setFolder] = useState<string>("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startAnalysis = useCallback(async (dirPath: string) => {
    if (!dirPath.trim()) return;
    setJob({ status: "running", progress: 0, total: 0, analyses: [], error: null });
    setJobId(null);

    const res  = await apiFetch("/api/analyze", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ tracks_dir: dirPath.trim() }),
    });
    const data = (await res.json()) as { job_id: string };
    setJobId(data.job_id);

    clearInterval(pollRef.current!);
    pollRef.current = setInterval(async () => {
      const r = await apiFetch(`/api/analyze/${data.job_id}`);
      const j = (await r.json()) as AnalysisJob;
      setJob(j);
      if (j.status === "done" || j.status === "error") {
        clearInterval(pollRef.current!);
        if (j.status === "done") onJobReady(data.job_id);
      }
    }, 800);
  }, [onJobReady]);

  const pickFolder = useCallback(async () => {
    if (window.electron) {
      const picked = await window.electron.selectFolder();
      if (picked) {
        setFolder(picked);
        await startAnalysis(picked);
      }
    }
  }, [startAnalysis]);

  const pct = job && job.total > 0 ? Math.round((job.progress / job.total) * 100) : 0;
  const isElectron = !!window.electron;

  return (
    <div className="dz-wrap">
      {isElectron ? (
        /* Native picker — the clean path */
        <button className="dz-pick-btn" onClick={pickFolder} disabled={job?.status === "running"}>
          <span className="dz-pick-icon">📂</span>
          <span>{folder ? folder.split("/").pop() : "Choose Music Folder…"}</span>
        </button>
      ) : (
        /* Browser fallback: manual path entry */
        <div className="dz-row">
          <input
            className="dz-input"
            type="text"
            placeholder="/absolute/path/to/tracks"
            value={folder}
            onChange={(e) => setFolder(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && startAnalysis(folder)}
          />
          <button
            className="dz-analyze-btn"
            disabled={!folder.trim() || job?.status === "running"}
            onClick={() => startAnalysis(folder)}
          >
            Analyze
          </button>
        </div>
      )}

      {job && (
        <div className="dz-status">
          {job.status === "running" && (
            <>
              <div className="dz-progress-wrap">
                <div className="dz-progress-fill" style={{ width: `${pct}%` }} />
              </div>
              <span className="dz-status-txt">
                Analyzing… {job.progress}/{job.total}
              </span>
            </>
          )}
          {job.status === "done" && (
            <span className="dz-status-txt ok">
              ✓ {job.total} track{job.total !== 1 ? "s" : ""} ready
              {jobId && <span className="dz-jid"> · {jobId.slice(0, 8)}</span>}
            </span>
          )}
          {job.status === "error" && (
            <span className="dz-status-txt err">✗ {job.error}</span>
          )}
        </div>
      )}

      <style>{`
        .dz-wrap { display: flex; flex-direction: column; gap: 10px; }
        .dz-pick-btn {
          display: flex;
          align-items: center;
          gap: 10px;
          width: 100%;
          padding: 12px 14px;
          background: var(--surface2);
          border: 1px solid var(--border);
          border-radius: var(--radius);
          cursor: pointer;
          font-size: 13px;
          color: var(--text);
          transition: border-color .15s;
          text-align: left;
          overflow: hidden;
          white-space: nowrap;
          text-overflow: ellipsis;
        }
        .dz-pick-btn:hover:not(:disabled) { border-color: var(--accent); }
        .dz-pick-btn:disabled { opacity: .5; cursor: not-allowed; }
        .dz-pick-icon { font-size: 16px; flex-shrink: 0; }
        .dz-row { display: flex; gap: 8px; }
        .dz-input { flex: 1; }
        .dz-analyze-btn {
          padding: 6px 14px;
          background: var(--accent);
          color: #fff;
          border-radius: var(--radius);
          font-weight: 600;
        }
        .dz-analyze-btn:disabled { opacity: .4; cursor: not-allowed; }
        .dz-status { display: flex; flex-direction: column; gap: 5px; }
        .dz-progress-wrap {
          height: 2px; background: var(--border); border-radius: 1px; overflow: hidden;
        }
        .dz-progress-fill {
          height: 100%; background: var(--accent); border-radius: 1px; transition: width .3s;
        }
        .dz-status-txt { font-size: 11px; color: var(--text-2); }
        .dz-status-txt.ok  { color: var(--green); }
        .dz-status-txt.err { color: #ff4d4d; }
        .dz-jid { color: var(--text-3); font-family: var(--mono); }
      `}</style>
    </div>
  );
}
