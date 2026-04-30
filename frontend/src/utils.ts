export function barToMmss(bar: number, bpm: number): string {
  const ms = Math.round((bar * 4 * 60_000) / bpm);
  const s  = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
