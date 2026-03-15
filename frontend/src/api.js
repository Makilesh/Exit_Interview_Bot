/**
 * Centralised API calls for the Exit Interview frontend.
 * All fetch logic lives here — components never call fetch directly.
 */

const BASE = '/api'

export async function startSession(mode = 'text_text') {
  const res = await fetch(`${BASE}/session/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  })
  if (!res.ok) throw new Error((await res.json()).detail ?? 'Failed to start session')
  return res.json()
}

export async function sendResponse(sessionId, answer) {
  const res = await fetch(`${BASE}/session/${sessionId}/respond`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answer }),
  })
  if (!res.ok) throw new Error((await res.json()).detail ?? 'Failed to submit answer')
  return res.json()
}

export async function getSession(sessionId) {
  const res = await fetch(`${BASE}/session/${sessionId}`)
  if (!res.ok) throw new Error('Session not found')
  return res.json()
}

export async function getSessions() {
  const res = await fetch(`${BASE}/sessions`)
  if (!res.ok) throw new Error('Failed to fetch sessions')
  return res.json()
}

/**
 * Triggers a browser download for session files.
 * @param {string} sessionId
 * @param {'json'|'transcript'|'summary'} type
 */
export function downloadFile(sessionId, type) {
  window.open(`${BASE}/session/${sessionId}/download/${type}`, '_blank')
}
