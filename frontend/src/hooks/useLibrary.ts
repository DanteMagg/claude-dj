import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../api';
import type { LibraryScanJob, LibraryTrack } from '../types';

export function useLibrary() {
  const [tracks, setTracks]   = useState<LibraryTrack[]>([]);
  const [scanJob, setScanJob] = useState<LibraryScanJob | null>(null);
  const [scanId, setScanId]   = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLibrary = useCallback(async () => {
    try {
      const res  = await apiFetch('/api/library');
      const data = (await res.json()) as { tracks: LibraryTrack[] };
      setTracks(data.tracks);
    } catch { /* ignore transient */ }
  }, []);

  useEffect(() => { void fetchLibrary(); }, [fetchLibrary]);

  // Poll scan job until done
  useEffect(() => {
    if (!scanId) return;
    pollRef.current = setInterval(async () => {
      try {
        const res = await apiFetch(`/api/library/scan/${scanId}`);
        const job = (await res.json()) as LibraryScanJob;
        setScanJob(job);
        if (job.status === 'done' || job.status === 'error') {
          clearInterval(pollRef.current!);
          if (job.status === 'done') void fetchLibrary();
        }
      } catch { /* ignore */ }
    }, 1000);
    return () => clearInterval(pollRef.current!);
  }, [scanId, fetchLibrary]);

  const scanFolder = useCallback(async (folder: string) => {
    setScanJob({ status: 'running', progress: 0, total: 0, known: 0, new: 0, error: null });
    try {
      const res  = await apiFetch('/api/library/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder }),
      });
      const data = (await res.json()) as { scan_id?: string; error?: string };
      if (data.error) {
        setScanJob({ status: 'error', progress: 0, total: 0, known: 0, new: 0, error: data.error });
      } else if (data.scan_id) {
        setScanId(data.scan_id);
      }
    } catch (e) {
      setScanJob({ status: 'error', progress: 0, total: 0, known: 0, new: 0, error: String(e) });
    }
  }, []);

  // Look up a track by hash (O(n) but library is small)
  const trackByHash = useCallback(
    (hash: string): LibraryTrack | undefined => tracks.find(t => t.hash === hash),
    [tracks],
  );

  // Best-effort lookup by title (for deck_b which has no hash in the API response)
  const trackByTitle = useCallback(
    (title: string): LibraryTrack | undefined => tracks.find(t => t.title === title),
    [tracks],
  );

  return { tracks, scanJob, scanFolder, fetchLibrary, trackByHash, trackByTitle };
}
