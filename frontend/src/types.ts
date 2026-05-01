export interface CuePoint {
  name: string;
  bar: number;
  type: string;
}

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
  energy_curve: string;
  cue_points: CuePoint[];
  first_downbeat_s: number;
  analyzed_at: string;
}

export interface LibraryScanJob {
  status: 'running' | 'done' | 'error';
  progress: number;
  total: number;
  known: number;
  new: number;
  skipped?: number;
  error: string | null;
}

// deck_a always has a hash; deck_b only has status + title (backend limitation)
export interface DjDeck {
  track_id: string;
  hash: string;
  title: string;
  start_bar: number;
  status: string;
}

export interface DjDeckB {
  status: 'starting' | 'analyzing' | 'selecting' | 'planning' | 'loading' | 'ready';
  title: string;
  hash?: string;
}

export interface MixAction {
  type: string;
  track: string;
  at_bar: number | null;
  from_bar: number | null;
  to_bar: number | null;
  bar: number | null;
  start_bar: number | null;
}

export interface MixTrackRef {
  id: string;
  path: string;
  bpm: number;
  first_downbeat_s: number;
}

export interface MixScript {
  mix_title: string;
  reasoning: string;
  tracks: MixTrackRef[];
  actions: MixAction[];
}

export interface DjState {
  status: 'starting' | 'playing' | 'stopped' | 'error';
  session_id: string | null;
  deck_a: DjDeck | null;
  deck_b: DjDeckB | null;
  ref_bpm: number | null;
  queue: string[];
  history: string[];
  script: MixScript | null;
  error: string | null;
}

export interface PlaybackStatus {
  current_bar: number;
  buffer_depth_bars: number;
  ref_bpm: number;
  status: string;
}

export type PlayerState = 'idle' | 'connecting' | 'buffering' | 'playing' | 'stopped' | 'error';

export interface DjStartOpts {
  pool: string[];
  queue: string[];
  let_claude_pick: boolean;
  model: string;
}

// Electron bridge (exposed by preload.cjs)
declare global {
  interface Window {
    electron?: {
      selectFolder: () => Promise<string | null>;
      showInFolder: (path: string) => Promise<void>;
      isElectron: boolean;
    };
  }
}
