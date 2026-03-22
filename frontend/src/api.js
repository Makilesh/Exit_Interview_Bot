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
 * Creates a WebSocket connection for voice interview sessions with auto-reconnect.
 * @param {string} sessionId
 * @param {string} mode - 'voice_text' | 'text_voice' | 'voice_voice'
 * @param {Object} handlers - Event handlers
 * @param {Function} handlers.onQuestion - Called when server sends a question
 * @param {Function} handlers.onComplete - Called when interview is complete
 * @param {Function} handlers.onCrisis - Called when crisis escalation is triggered
 * @param {Function} handlers.onTranscript - Called when server sends back the STT transcript
 * @param {Function} handlers.onError - Called on error
 * @param {Function} handlers.onClose - Called when connection closes
 * @param {Function} handlers.onConnect - Called when connection establishes
 * @param {Function} handlers.onStateChange - Called when connection state changes
 * @returns {Object} - { sendAudio, sendText, close, reconnect, getState }
 */
export function createVoiceSocket(sessionId, mode, handlers) {
  let ws = null
  let reconnectTimer = null
  let heartbeatTimer = null
  let connectionTimeout = null
  let reconnectAttempts = 0
  let manualClose = false
  let hasReceivedFirstMessage = false

  const MAX_RECONNECT_ATTEMPTS = 5
  const RECONNECT_DELAY_MS = 2000
  const CONNECTION_TIMEOUT_MS = 10000
  const HEARTBEAT_INTERVAL_MS = 30000

  // Connection states: 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'failed'
  let connectionState = 'connecting'

  const updateState = (newState) => {
    if (connectionState !== newState) {
      connectionState = newState
      console.log(`[Voice WS] State: ${newState}`)
      handlers.onStateChange?.({ state: newState, attempts: reconnectAttempts })
    }
  }

  const clearTimers = () => {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    if (heartbeatTimer) clearInterval(heartbeatTimer)
    if (connectionTimeout) clearTimeout(connectionTimeout)
  }

  const startHeartbeat = () => {
    heartbeatTimer = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) {
        try {
          ws.send(JSON.stringify({ type: 'ping' }))
        } catch (e) {
          console.warn('[Voice WS] Heartbeat ping failed:', e)
        }
      }
    }, HEARTBEAT_INTERVAL_MS)
  }

  const connect = () => {
    clearTimers()

    // Set connection timeout
    connectionTimeout = setTimeout(() => {
      if (ws?.readyState !== WebSocket.OPEN && !hasReceivedFirstMessage) {
        console.error('[Voice WS] Connection timeout')
        ws?.close()
        updateState('failed')
        handlers.onError?.(new Error('Connection timeout - please check if the backend server is running on port 8000'))
      }
    }, CONNECTION_TIMEOUT_MS)

    // Connect directly to backend (bypasses Vite proxy which can have WS issues)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsHost = import.meta.env.PROD ? window.location.host : 'localhost:8000'
    const wsUrl = `${protocol}//${wsHost}/api/voice/ws/${sessionId}?mode=${mode}`

    console.log(`[Voice WS] Connecting to ${wsUrl}`)
    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      clearTimeout(connectionTimeout)
      reconnectAttempts = 0
      updateState('connected')
      console.log('[Voice WS] Connected successfully')
      handlers.onConnect?.()
      startHeartbeat()
    }

    ws.onmessage = (event) => {
      if (!hasReceivedFirstMessage) {
        hasReceivedFirstMessage = true
        clearTimeout(connectionTimeout)
      }

      try {
        const msg = JSON.parse(event.data)

        // Handle heartbeat pong
        if (msg.type === 'pong') {
          return
        }

        switch (msg.type) {
          case 'question':
            handlers.onQuestion?.(msg)
            break
          case 'transcript':
            handlers.onTranscript?.(msg)
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
            console.warn('[Voice WS] Unknown message type:', msg.type)
        }
      } catch (e) {
        console.error('[Voice WS] Failed to parse message:', e)
      }
    }

    ws.onerror = (event) => {
      console.error('[Voice WS] Error:', event)
      const errorMsg = connectionState === 'connecting'
        ? 'Failed to connect - verify backend is running on port 8000'
        : 'Connection error occurred'
      handlers.onError?.(new Error(errorMsg))
    }

    ws.onclose = (event) => {
      clearTimers()
      console.log(`[Voice WS] Closed: code=${event.code}, clean=${event.wasClean}, reason="${event.reason}"`)

      if (manualClose) {
        updateState('disconnected')
        handlers.onClose?.(event)
        return
      }

      // Auto-reconnect on unexpected close
      if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts++
        updateState('reconnecting')
        console.log(`[Voice WS] Reconnecting (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`)

        reconnectTimer = setTimeout(() => {
          connect()
        }, RECONNECT_DELAY_MS)
      } else {
        updateState('failed')
        handlers.onError?.(new Error(`Unable to connect after ${MAX_RECONNECT_ATTEMPTS} attempts. Please refresh the page.`))
        handlers.onClose?.(event)
      }
    }
  }

  // Initial connection
  connect()

  return {
    /**
     * Send audio blob to server for transcription.
     * @param {Blob} blob - Audio blob (WebM/Opus)
     */
    sendAudio: (blob) => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(blob)
      } else {
        console.warn('[Voice WS] Cannot send audio - not connected')
        handlers.onError?.(new Error('Not connected - please wait for reconnection'))
      }
    },

    /**
     * Send text answer (for text_voice mode).
     * @param {string} text
     */
    sendText: (text) => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'text', data: text }))
      } else {
        console.warn('[Voice WS] Cannot send text - not connected')
        handlers.onError?.(new Error('Not connected - please wait for reconnection'))
      }
    },

    /**
     * Manually close the WebSocket connection (no auto-reconnect).
     */
    close: () => {
      manualClose = true
      clearTimers()
      ws?.close()
    },

    /**
     * Manually trigger reconnection.
     */
    reconnect: () => {
      if (connectionState === 'failed' || connectionState === 'disconnected') {
        reconnectAttempts = 0
        hasReceivedFirstMessage = false
        manualClose = false
        updateState('connecting')
        connect()
      }
    },

    /**
     * Check if WebSocket is connected.
     * @returns {boolean}
     */
    isConnected: () => ws?.readyState === WebSocket.OPEN,

    /**
     * Get current connection state.
     * @returns {string}
     */
    getState: () => connectionState,
  }
}
