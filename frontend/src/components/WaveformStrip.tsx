import { useEffect, useRef } from 'react';
import type { CuePoint, LibraryTrack } from '../types';

interface Props {
  trackA:     LibraryTrack | undefined;
  trackB:     LibraryTrack | undefined;
  currentBar: number;
  onSeek:     (bar: number) => void;
}

function sampleCurve(curve: string, targetBars: number): number[] {
  const out: number[] = [];
  for (let i = 0; i < targetBars; i++) {
    const idx = Math.floor(i * curve.length / targetBars);
    out.push((parseInt(curve[idx] ?? '5', 10) || 5) / 9);
  }
  return out;
}

function drawCurve(
  ctx: CanvasRenderingContext2D,
  samples: number[],
  _W: number,
  H: number,
  startX: number,
  endX: number,
  colorFrom: string,
  colorTo: string,
  alphaScale: number,
) {
  if (samples.length === 0) return;
  ctx.beginPath();
  ctx.moveTo(startX, H);
  for (let i = 0; i < samples.length; i++) {
    const x = startX + (i / samples.length) * (endX - startX);
    const y = H - samples[i] * (H - 10) - 5;
    ctx.lineTo(x, y);
  }
  ctx.lineTo(endX, H);
  ctx.closePath();
  const grad = ctx.createLinearGradient(startX, 0, endX, 0);
  grad.addColorStop(0, colorFrom);
  grad.addColorStop(1, colorTo);
  ctx.fillStyle = grad;
  ctx.globalAlpha = alphaScale;
  ctx.fill();
  ctx.globalAlpha = 1;
}

export default function WaveformStrip({ trackA, trackB, currentBar, onSeek }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const W = container.clientWidth;
    const H = 64;
    canvas.width  = W;
    canvas.height = H;

    const ctx = canvas.getContext('2d')!;
    ctx.clearRect(0, 0, W, H);

    const totalBars  = trackA ? Math.max(1, trackA.energy_curve.length) : 128;
    const playheadX  = (currentBar / totalBars) * W;
    // Estimate transition start at 75% of total bars (visual approximation)
    const transX     = W * 0.75;

    // ── Deck A curve ────────────────────────────────────────────────────────
    if (trackA?.energy_curve) {
      const samplesA = sampleCurve(trackA.energy_curve, totalBars);
      // Past portion (dimmed)
      const pastSamples = samplesA.slice(0, currentBar);
      drawCurve(ctx, pastSamples, W, H, 0, playheadX,
        'rgba(255,95,0,0.15)', 'rgba(255,95,0,0.15)', 1);
      // Future portion (bright)
      const futureSamples = samplesA.slice(currentBar);
      drawCurve(ctx, futureSamples, W, H, playheadX, W,
        'rgba(255,95,0,0.85)', 'rgba(255,95,0,0.2)', 1);
    }

    // ── Deck B curve (transition zone) ──────────────────────────────────────
    if (trackB?.energy_curve && transX < W) {
      const bBars    = Math.max(1, Math.floor(totalBars * 0.25));
      const samplesB = sampleCurve(trackB.energy_curve, bBars);
      drawCurve(ctx, samplesB, W, H, transX, W,
        'rgba(0,180,255,0.05)', 'rgba(0,180,255,0.7)', 1);
    }

    // ── Transition zone dashed line ──────────────────────────────────────────
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(transX, 4);
    ctx.lineTo(transX, H - 4);
    ctx.strokeStyle = 'rgba(255,255,255,0.12)';
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.setLineDash([]);

    // ── Cue points ───────────────────────────────────────────────────────────
    if (trackA?.cue_points) {
      trackA.cue_points.forEach((cp: CuePoint) => {
        const x = (cp.bar / totalBars) * W;
        ctx.beginPath();
        ctx.moveTo(x - 4, 0);
        ctx.lineTo(x + 4, 0);
        ctx.lineTo(x,     6);
        ctx.closePath();
        ctx.fillStyle = '#ffd60a';
        ctx.fill();
      });
    }

    // ── Playhead ─────────────────────────────────────────────────────────────
    ctx.beginPath();
    ctx.moveTo(playheadX, 0);
    ctx.lineTo(playheadX, H);
    ctx.strokeStyle = 'rgba(255,255,255,0.6)';
    ctx.lineWidth = 2;
    ctx.stroke();
  }, [trackA, trackB, currentBar]);

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const x    = e.clientX - rect.left;
    const totalBars = trackA ? Math.max(1, trackA.energy_curve.length) : 128;
    const bar  = Math.round((x / rect.width) * totalBars);
    onSeek(Math.max(0, Math.min(bar, totalBars - 1)));
  };

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: 64,
        background: 'var(--bg)',
        borderBottom: '1px solid var(--border)',
        cursor: 'crosshair',
        flexShrink: 0,
      }}
    >
      <canvas
        ref={canvasRef}
        style={{ display: 'block', width: '100%', height: '100%' }}
        onClick={handleClick}
      />
    </div>
  );
}
