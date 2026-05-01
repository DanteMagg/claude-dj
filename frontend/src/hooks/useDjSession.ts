import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../api';
import type { DjStartOpts, DjState } from '../types';

export function useDjSession() {
  const [djId,    setDjId]    = useState<string | null>(null);
  const [djState, setDjState] = useState<DjState | null>(null);
  const [error,   setError]   = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!djId) return;
    pollRef.current = setInterval(async () => {
      try {
        const res   = await apiFetch(`/api/dj/${djId}`);
        const state = (await res.json()) as DjState;
        setDjState(state);
        if (state.status === 'error') {
          setError(state.error);
          clearInterval(pollRef.current!);
        }
      } catch { /* ignore transient */ }
    }, 1500);
    return () => clearInterval(pollRef.current!);
  }, [djId]);

  const startDj = useCallback(async (opts: DjStartOpts) => {
    setError(null);
    try {
      const res  = await apiFetch('/api/dj/start', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(opts),
      });
      const data = (await res.json()) as { dj_id?: string; error?: string };
      if (data.error) { setError(data.error); return; }
      if (data.dj_id) setDjId(data.dj_id);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const stopDj = useCallback(() => {
    clearInterval(pollRef.current!);
    setDjId(null);
    setDjState(null);
    setError(null);
  }, []);

  const enqueue = useCallback(async (hash: string) => {
    if (!djId) return;
    try {
      await apiFetch(`/api/dj/${djId}/queue`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ hash }),
      });
    } catch { /* ignore */ }
  }, [djId]);

  return { djId, djState, error, startDj, stopDj, enqueue };
}
