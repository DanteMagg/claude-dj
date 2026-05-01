import { useCallback, useRef, useState } from "react";
import { apiFetch } from "../api";
import type { AnalysisJob } from "../types";

interface Props { onJobReady: (jobId: string) => void; }

declare global {
  interface Window {
    electron?: { selectFolder: () => Promise<string | null>; isElectron: true };
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
      if (picked) { setFolder(picked); await startAnalysis(picked); }
    }
  }, [startAnalysis]);

  const pct        = job && job.total > 0 ? Math.round((job.progress / job.total) * 100) : 0;
  const isElectron = !!window.electron;

  return (
    <div className="dz">
      {isElectron ? (
        <button className="dz-pick" onClick={pickFolder} disabled={job?.status === "running"}>
          <span className="dz-pick-icon">◫</span>
          {folder ? folder.split("/").pop() : "Choose Music Folder…"}
        </button>
      ) : (
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
            className="dz-btn"
            disabled={!folder.trim() || job?.status === "running"}
            onClick={() => startAnalysis(folder)}
          >
            {job?.status === "running" ? "…" : "Analyze"}
          </button>
        </div>
      )}

      {job && (
        <div className="dz-status">
          {job.status === "running" && (
            <>
              <div className="dz-bar"><div className="dz-bar-fill" style={{ width: `${pct}%` }} /></div>
              <span className="dz-txt">Analyzing {job.progress}/{job.total} tracks…</span>
            </>
          )}
          {job.status === "done" && (
            <span className="dz-txt dz-txt--ok">
              ✓ {job.total} track{job.total !== 1 ? "s" : ""} ready
              {jobId && <span className="dz-id"> · {jobId.slice(0, 8)}</span>}
            </span>
          )}
          {job.status === "error" && (
            <span className="dz-txt dz-txt--err">✗ {job.error}</span>
          )}
        </div>
      )}

      <style>{`
        .dz { display: flex; flex-direction: column; gap: 8px; }
        .dz-pick {
          display: flex; align-items: center; gap: 8px; width: 100%;
          padding: 10px 12px; background: var(--surface2);
          border: 1px solid var(--border); border-radius: var(--radius);
          font-size: 13px; color: var(--text); text-align: left;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
          transition: border-color .15s;
        }
        .dz-pick:hover:not(:disabled) { border-color: var(--border2); }
        .dz-pick:disabled { opacity: .5; cursor: not-allowed; }
        .dz-pick-icon { font-size: 15px; flex-shrink: 0; }

        .dz-row { display: flex; gap: 8px; }
        .dz-input { flex: 1; font-size: 13px; }
        .dz-btn {
          padding: 6px 14px; background: var(--surface3);
          border: 1px solid var(--border2); border-radius: var(--radius);
          font-size: 12px; font-weight: 600; color: var(--text); white-space: nowrap;
          transition: border-color .15s;
        }
        .dz-btn:hover:not(:disabled) { border-color: var(--orange); color: var(--orange); }
        .dz-btn:disabled { opacity: .4; cursor: not-allowed; }

        .dz-status { display: flex; flex-direction: column; gap: 5px; }
        .dz-bar {
          height: 2px; background: var(--border); border-radius: 1px; overflow: hidden;
        }
        .dz-bar-fill {
          height: 100%; background: var(--orange); border-radius: 1px; transition: width .3s;
        }
        .dz-txt     { font-size: 11px; color: var(--text-2); font-family: var(--mono); }
        .dz-txt--ok  { color: var(--green); }
        .dz-txt--err { color: var(--red); }
        .dz-id { color: var(--text-3); }
      `}</style>
    </div>
  );
}
