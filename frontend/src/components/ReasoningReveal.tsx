import { useEffect, useRef, useState } from 'react';

interface Props {
  status:    string;    // deck_b.status
  reasoning: string;   // djState.script.reasoning (latest segment already extracted by parent)
}

const STATUS_LABELS: Record<string, string> = {
  starting:   'Starting…',
  analyzing:  'Analyzing track…',
  selecting:  'Selecting transition window…',
  planning:   'Deep zone analysis + planning…',
  loading:    'Loading audio…',
};

export default function ReasoningReveal({ status, reasoning }: Props) {
  const [displayed, setDisplayed] = useState('');
  // Use a ref (not state) to track which reasoning string we started typing.
  // Using state here causes a re-render that triggers the effect cleanup, which
  // cancels the interval before even one character is typed.
  const startedRef = useRef('');
  const timerRef   = useRef<ReturnType<typeof setInterval> | null>(null);
  const posRef     = useRef(0);

  // Kick off typewriter whenever `reasoning` arrives or changes.
  // Only `reasoning` in the deps array — changes to startedRef don't cause re-runs.
  useEffect(() => {
    if (!reasoning || reasoning === startedRef.current) return;
    startedRef.current = reasoning;
    posRef.current = 0;
    setDisplayed('');
    clearInterval(timerRef.current!);
    timerRef.current = setInterval(() => {
      posRef.current += 2;
      setDisplayed(reasoning.slice(0, posRef.current));
      if (posRef.current >= reasoning.length) clearInterval(timerRef.current!);
    }, 40);
    return () => clearInterval(timerRef.current!);
  }, [reasoning]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reset when a new track starts being analyzed on deck B
  useEffect(() => {
    if (status === 'analyzing' || status === 'selecting' || status === 'starting') {
      clearInterval(timerRef.current!);
      setDisplayed('');
      startedRef.current = '';
      posRef.current = 0;
    }
  }, [status]);

  const label     = STATUS_LABELS[status];
  const isWorking = !!label && !displayed;

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
          margin: 0,
        }}>
          {displayed}
          {displayed.length < startedRef.current.length && (
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
