/**
 * Runtime URL base detection.
 *
 * - Electron production: page is loaded from file://, so fetch("/api/...") would fail.
 *   We always talk directly to 127.0.0.1:8000.
 * - Electron dev / browser dev: Vite proxy forwards /api/* and /ws/* to :8000, so
 *   relative URLs work fine.
 */

const ELECTRON_PROD = typeof window !== "undefined" && window.location.protocol === "file:";

export const API_BASE: string = ELECTRON_PROD ? "http://127.0.0.1:8000" : "";
export const WS_BASE:  string = ELECTRON_PROD
  ? "ws://127.0.0.1:8000"
  : `ws://${window.location.host}`;

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API_BASE}${path}`, init);
}
