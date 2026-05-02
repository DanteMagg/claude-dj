// Vite dev server proxies /api → http://127.0.0.1:8000 and /ws → ws://127.0.0.1:8000
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(path, init);
}

export function buildWsUrl(path: string): string {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${location.host}${path}`;
}
