/**
 * Voice WebSocket URL.
 * In dev, use same origin as the Vite page so /voice is proxied (avoids cross-port WS issues).
 * In production, use VITE_API_URL or default orchestrator origin.
 */
const DEFAULT_API_ORIGIN = 'http://127.0.0.1:8002';

export function voiceWebSocketUrl(sessionId) {
  if (import.meta.env.DEV) {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${window.location.host}/voice/ws?session_id=${encodeURIComponent(sessionId)}`;
  }
  const base = (import.meta.env.VITE_API_URL || DEFAULT_API_ORIGIN).replace(/\/$/, '');
  const u = new URL(base.startsWith('http') ? base : `https://${base}`);
  const proto = u.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${u.host}/voice/ws?session_id=${encodeURIComponent(sessionId)}`;
}
