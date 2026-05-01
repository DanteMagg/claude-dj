export interface TrackRef {
  id: string;
  path: string;
  bpm: number;
  first_downbeat_s: number;
}

export interface MixAction {
  type: string;
  track: string;
  at_bar?: number;
  from_bar?: number;
  start_bar?: number;
  duration_bars?: number;
  stems?: Record<string, number>;
  bar?: number;
  low?: number;
  mid?: number;
  high?: number;
  incoming_track?: string;
  loop_bars?: number;
  loop_repeats?: number;
  loop_mute_tail?: boolean;
}

export interface MixScript {
  mix_title: string;
  reasoning: string;
  tracks: TrackRef[];
  actions: MixAction[];
}

export interface AnalysisJob {
  status: "running" | "done" | "error";
  progress: number;
  total: number;
  analyses: Record<string, unknown>[];
  error: string | null;
}

export interface Session {
  session_id: string;
  script: MixScript;
  ref_bpm: number;
  /** "loading" → audio is loading in bg; "ready" → WS can open; "error" → load failed */
  status: string;
  load_total: number;
}

export interface SessionPoll {
  status: string;
  load_progress: number;
  load_total: number;
  error: string | null;
}

export interface StatusResponse {
  current_bar: number;
  buffer_depth_bars: number;
  ref_bpm: number;
  tracks: TrackRef[];
}

// ── Library ───────────────────────────────────────────────────────────────────

export interface LibraryTrack {
  hash: string;
  path: string;
  title: string;
  artist: string;
  bpm: number;
  key_camelot: string;
  key_standard: string;
  energy: number;
  duration_s: number;
  /** compact energy string e.g. "4567898765…" (one digit 0-9 per bar) */
  energy_curve: string;
  cue_points: { name: string; bar: number; type: string }[];
  first_downbeat_s: number;
  analyzed_at?: string;
}

export interface LibraryScanJob {
  status: "running" | "done" | "error";
  progress: number;
  total: number;
  known: number;
  new: number;
  error: string | null;
}

// ── DJ Session ────────────────────────────────────────────────────────────────

export interface DjDeck {
  track_id: string;
  hash: string;
  title: string;
  start_bar: number;
  status: string;
}

export interface DjState {
  status: "starting" | "playing" | "error";
  session_id: string | null;
  deck_a: DjDeck | null;
  deck_b: DjDeck | null;
  history: string[];
  queue: string[];
  ref_bpm: number | null;
  script: MixScript | null;
  error: string | null;
}
