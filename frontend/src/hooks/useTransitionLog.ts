import { useEffect, useRef, useState } from 'react';

export interface LoggedAction {
  type: string;
  track: string;
  at_bar: number | null;
  start_bar: number | null;
  duration_bars: number | null;
  bar: number | null;
  low: number | null;
  mid: number | null;
  high: number | null;
  incoming_track: string | null;
  stems: Record<string, number> | null;
  loop_bars: number | null;
  loop_repeats: number | null;
}

export interface TransitionLogEntry {
  ts: string;
  from_id: string;
  to_id: string;
  from_title: string;
  to_title: string;
  offset_bar: number;
  reasoning: string;
  actions: LoggedAction[];
}

export function useTransitionLog(djId: string | null) {
  const [log, setLog]     = useState<TransitionLogEntry[]>([]);
  const prevLen           = useRef(0);
  const intervalRef       = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!djId) {
      setLog([]);
      prevLen.current = 0;
      return;
    }

    const poll = async () => {
      try {
        const res = await fetch(`/api/dj/${djId}/log`);
        if (!res.ok) return;
        const data = await res.json();
        const entries: TransitionLogEntry[] = data.log ?? [];
        if (entries.length !== prevLen.current) {
          prevLen.current = entries.length;
          setLog([...entries].reverse()); // newest first
        }
      } catch { /* ignore */ }
    };

    poll();
    intervalRef.current = setInterval(poll, 3000);
    return () => clearInterval(intervalRef.current!);
  }, [djId]);

  return log;
}
