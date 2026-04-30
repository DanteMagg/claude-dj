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
}

export interface StatusResponse {
  current_bar: number;
  buffer_depth_bars: number;
  ref_bpm: number;
  tracks: TrackRef[];
}
