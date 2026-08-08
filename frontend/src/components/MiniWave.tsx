interface Props {
  curve: string;
  active?: boolean;
  width?: number;
  height?: number;
}

export default function MiniWave({ curve, active = false, width = 80, height = 22 }: Props) {
  const BARS = 40;
  const samples: number[] = [];
  for (let i = 0; i < BARS; i++) {
    const idx = Math.min(curve.length - 1, Math.floor(i * curve.length / BARS));
    samples.push((parseInt(curve[idx] ?? '5', 10) || 5) / 9);
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'flex-end', gap: 1,
      width, height, flexShrink: 0, overflow: 'hidden',
    }}>
      {samples.map((h, i) => (
        <div
          key={i}
          style={{
            flex: 1,
            minWidth: 1,
            height: `${Math.max(15, h * 100)}%`,
            background: active ? 'var(--orange)' : 'var(--text-3)',
            borderRadius: '1px 1px 0 0',
          }}
        />
      ))}
    </div>
  );
}
