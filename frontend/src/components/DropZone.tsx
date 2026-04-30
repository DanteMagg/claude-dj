import { useCallback, useRef, useState } from "react";
import type { AnalysisJob } from "../types";

interface Props {
  onJobReady: (jobId: string) => void;
}

export default function DropZone({ onJobReady }: Props) {
  const [dragging, setDragging] = useState(false);
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [dirPath, setDirPath] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const startAnalysis = useCallback(async (path: string) => {
    if (!path.trim()) return;
    setJob({ status: "running", progress: 0, total: 0, analyses: [], error: null });

    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tracks_dir: path.trim() }),
    });
    const data = (await res.json()) as { job_id: string };
    setJobId(data.job_id);

    pollRef.current = setInterval(async () => {
      const r = await fetch(`/api/analyze/${data.job_id}`);
      const j = (await r.json()) as AnalysisJob;
      setJob(j);
      if (j.status === "done" || j.status === "error") {
        clearInterval(pollRef.current!);
        if (j.status === "done") onJobReady(data.job_id);
      }
    }, 800);
  }, [onJobReady]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const items = Array.from(e.dataTransfer.items);
      const entry = items[0]?.webkitGetAsEntry?.();
      if (entry?.isDirectory) {
        // Extract path from the dropped folder name (limited in browser)
        const name = e.dataTransfer.files[0]?.name ?? "";
        // The server needs the full FS path; prompt user to type it if drag fails
        if (name) setDirPath(name);
      }
    },
    [],
  );

  const pct = job && job.total > 0 ? Math.round((job.progress / job.total) * 100) : 0;

  return (
    <div className="dropzone-wrap">
      <div
        className={`dropzone ${dragging ? "drag-over" : ""}`}
        onDragEnter={() => setDragging(true)}
        onDragLeave={() => setDragging(false)}
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
        onClick={() => fileRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && fileRef.current?.click()}
      >
        <span className="dropzone-icon">🎵</span>
        <span className="dropzone-label">
          {dragging ? "Drop folder here" : "Click or drag a music folder"}
        </span>
        <input
          ref={fileRef}
          type="file"
          // @ts-expect-error — webkitdirectory is non-standard
          webkitdirectory="true"
          multiple
          style={{ display: "none" }}
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            if (files.length > 0) {
              // Derive folder path from the relative path prefix
              const rel = files[0]?.webkitRelativePath ?? "";
              const dir = rel.split("/")[0] ?? "";
              setDirPath(dir);
            }
          }}
        />
      </div>

      <div className="dir-row">
        <input
          className="dir-input"
          type="text"
          placeholder="/absolute/path/to/tracks"
          value={dirPath}
          onChange={(e) => setDirPath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && startAnalysis(dirPath)}
        />
        <button
          className="btn-primary"
          disabled={!dirPath.trim() || job?.status === "running"}
          onClick={() => startAnalysis(dirPath)}
        >
          Analyze
        </button>
      </div>

      {job && (
        <div className="analysis-status">
          {job.status === "running" && (
            <>
              <div className="progress-bar-wrap">
                <div className="progress-bar" style={{ width: `${pct}%` }} />
              </div>
              <span className="status-text">
                Analyzing… {job.progress}/{job.total} tracks
              </span>
            </>
          )}
          {job.status === "done" && (
            <span className="status-text ok">
              ✓ {job.total} track{job.total !== 1 ? "s" : ""} analyzed
              {jobId && <span className="job-id"> · job {jobId.slice(0, 8)}</span>}
            </span>
          )}
          {job.status === "error" && (
            <span className="status-text err">✗ {job.error}</span>
          )}
        </div>
      )}

      <style>{`
        .dropzone-wrap { display: flex; flex-direction: column; gap: 12px; }
        .dropzone {
          border: 2px dashed var(--border);
          border-radius: var(--radius);
          padding: 32px 24px;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 8px;
          cursor: pointer;
          transition: border-color .15s, background .15s;
          user-select: none;
        }
        .dropzone:hover, .dropzone.drag-over {
          border-color: var(--accent);
          background: rgba(255,95,0,.05);
        }
        .dropzone-icon { font-size: 28px; }
        .dropzone-label { color: var(--text-2); font-size: 13px; }
        .dir-row { display: flex; gap: 8px; }
        .dir-input { flex: 1; }
        .btn-primary {
          padding: 6px 16px;
          background: var(--accent);
          color: #fff;
          border-radius: var(--radius);
          font-weight: 600;
          transition: opacity .15s;
        }
        .btn-primary:disabled { opacity: .4; cursor: not-allowed; }
        .btn-primary:not(:disabled):hover { opacity: .85; }
        .analysis-status { display: flex; flex-direction: column; gap: 6px; }
        .progress-bar-wrap {
          height: 3px;
          background: var(--border);
          border-radius: 2px;
          overflow: hidden;
        }
        .progress-bar {
          height: 100%;
          background: var(--accent);
          border-radius: 2px;
          transition: width .3s;
        }
        .status-text { font-size: 12px; color: var(--text-2); }
        .status-text.ok { color: var(--green); }
        .status-text.err { color: #ff4d4d; }
        .job-id { color: var(--text-3); font-family: var(--mono); }
      `}</style>
    </div>
  );
}
