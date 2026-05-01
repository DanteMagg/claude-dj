import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../api';

interface Props {
  status: string;       // deck_b.status: 'analyzing' | 'planning' | 'loading' | 'ready'
  sessionId: string | null;
}

const STATUS_LABELS: Record<string, string> = {
  starting:  'Starting…',
  analyzing: 'Analyzing track…',
  planning:  'Planning transition…',
  loading:   'Loading audio…',
};

export default function ReasoningReveal({ status, sessionId }: Props) {
  const [fullText,   setFullText]   = useState('');
  const [displayed,  setDisplayed]  = useState('');
  const [fetchedFor, setFetchedFor] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const posRef   = useRef(0);

  // Fetch script.reasoning once session is ready
  useEffect(() => {
    if (status !== 'ready' || !sessionId || fetchedFor === sessionId) return;
    setFetchedFor(sessionId);
    apiFetch(`/api/script/${sessionId}`)
      .then(r => r.json())
      .then((s: { reasoning?: string }) => { if (s.reasoning) setFullText(s.reasoning); })
      .catch(() => {});
  }, [status, sessionId, fetchedFor]);

  // Typewriter reveal when fullText arrives
  useEffect(() => {
    if (!fullText) return;
    posRef.current = 0;
    setDisplayed('');
    clearInterval(timerRef.current!);
    timerRef.current = setInterval(() => {
      posRef.current += 2;
      setDisplayed(fullText.slice(0, posRef.current));
      if (posRef.current >= fullText.length) clearInterval(timerRef.current!);
    }, 40);
    return () => clearInterval(timerRef.current!);
  }, [fullText]);

  // Reset when deck_b cycles to a new track
  useEffect(() => {
    if (status === 'analyzing' || status === 'starting') {
      setFullText('');
      setDisplayed('');
      setFetchedFor(null);
      posRef.current = 0;
    }
  }, [status]);

  const label = STATUS_LABELS[status];
  const isWorking = label !== undefined && !displayed;

  if (!isWorking && !displayed) return null;

  return (
    <div style={{ marginTop: 8 }}>
      {isWorking && (
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: '.1em',
          padding: '2px 7px',
          borderRadius: 3,
          background: 'rgba(191,90,242,0.12)',
          color: 'var(--purple)',
          animation: 'pulse 1.8s ease-in-out infinite',
        }}>
          {label}
        </span>
      )}
      {displayed && (
        <p style={{
          fontSize: 11,
          color: 'var(--text-2)',
          lineHeight: 1.65,
          fontFamily: 'var(--font-ui)',
        }}>
          {displayed}
          {displayed.length < fullText.length && (
            <span style={{
              display: 'inline-block',
              width: 6, height: 10,
              background: 'var(--purple)',
              verticalAlign: 'middle',
              marginLeft: 2,
              animation: 'blink 1s step-end infinite',
            }} />
          )}
        </p>
      )}
    </div>
  );
}
