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

/**
 * Creates a WebSocket connection for voice interview sessions.
 * @param {string} sessionId
 * @param {string} mode - 'voice_text' | 'text_voice' | 'voice_voice'
 * @param {Object} handlers - Event handlers
 * @param {Function} handlers.onQuestion - Called when server sends a question
 * @param {Function} handlers.onComplete - Called when interview is complete
 * @param {Function} handlers.onCrisis - Called when crisis escalation is triggered
 * @param {Function} handlers.onTranscription - Called when STT transcription is ready
 * @param {Function} handlers.onError - Called on error
 * @param {Function} handlers.onClose - Called when connection closes
 * @returns {Object} - { sendAudio, sendText, close }
 */
export function createVoiceSocket(sessionId, mode, handlers) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  const ws = new WebSocket(`${protocol}//${host}/api/voice/ws/${sessionId}?mode=${mode}`)

  ws.onopen = () => {
    console.log('Voice WebSocket connected')
    handlers.onConnect?.()
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)

      switch (msg.type) {
        case 'question':
          handlers.onQuestion?.(msg)
          break
        case 'transcription':
          handlers.onTranscription?.(msg)
          break
        case 'complete':
          handlers.onComplete?.(msg)
          break
        case 'crisis':
          handlers.onCrisis?.(msg)
          break
        case 'error':
          handlers.onError?.(new Error(msg.message))
          break
        default:
          console.warn('Unknown message type:', msg.type)
      }
    } catch (e) {
      console.error('Failed to parse WebSocket message:', e)
    }
  }

  ws.onerror = (event) => {
    console.error('Voice WebSocket error:', event)
    handlers.onError?.(new Error('WebSocket connection error'))
  }

  ws.onclose = (event) => {
    console.log('Voice WebSocket closed:', event.code, event.reason)
    handlers.onClose?.(event)
  }

  return {
    /**
     * Send audio blob to server for transcription.
     * @param {Blob} blob - Audio blob (WebM/Opus)
     */
    sendAudio: (blob) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(blob)
      }
    },

    /**
     * Send text answer (for text_voice mode).
     * @param {string} text
     */
    sendText: (text) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'text', data: text }))
      }
    },

    /**
     * Close the WebSocket connection.
     */
    close: () => {
      ws.close()
    },

    /**
     * Check if WebSocket is connected.
     * @returns {boolean}
     */
    isConnected: () => ws.readyState === WebSocket.OPEN,
  }
}
