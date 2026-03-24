import { useState, useEffect, useRef, useCallback } from 'react'
import { createVoiceSocket } from '../api.js'
import ProgressBar from './ProgressBar.jsx'

function Spinner() {
  return (
    <div className="flex gap-1 items-center px-4 py-3">
      {[0, 1, 2].map(i => (
        <span
          key={i}
          className="w-2 h-2 rounded-full bg-slate-400 dark:bg-slate-500 animate-bounce"
          style={{ animationDelay: `${i * 120}ms` }}
        />
      ))}
    </div>
  )
}

function MicButton({ isRecording, onStart, onStop, disabled }) {
  return (
    <button
      onMouseDown={onStart}
      onMouseUp={onStop}
      onMouseLeave={onStop}
      onTouchStart={onStart}
      onTouchEnd={onStop}
      disabled={disabled}
      className={`
        w-16 h-16 rounded-full flex items-center justify-center text-2xl
        transition-all duration-150 select-none
        ${isRecording
          ? 'bg-red-500 scale-110 shadow-lg shadow-red-500/30'
          : 'bg-cyan-600 hover:bg-cyan-500 hover:scale-105'
        }
        ${disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}
        text-white
      `}
    >
      {isRecording ? '🎤' : '🎙️'}
    </button>
  )
}

function SpeakingIndicator() {
  return (
    <div className="flex items-center gap-2 text-cyan-500 dark:text-cyan-400">
      <div className="flex gap-0.5 items-end h-4">
        {[0, 1, 2, 3, 4].map(i => (
          <div
            key={i}
            className="w-1 bg-current rounded-full animate-pulse"
            style={{
              height: `${Math.random() * 12 + 4}px`,
              animationDelay: `${i * 100}ms`,
              animationDuration: '0.5s',
            }}
          />
        ))}
      </div>
      <span className="text-sm">AI is speaking...</span>
    </div>
  )
}

export default function VoiceInterface({ sessionId, firstQuestion, totalQuestions, mode, onComplete, onCancel }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState(null)
  const [isFatalError, setIsFatalError] = useState(false)  // Track if error is fatal
  const [questionNumber, setQuestionNumber] = useState(1)
  const [connectionState, setConnectionState] = useState('connecting') // 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'failed'
  const [reconnectAttempts, setReconnectAttempts] = useState(0)

  const bottomRef = useRef(null)
  const wsRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])
  const audioContextRef = useRef(null)

  const useSTT = mode === 'voice_text' || mode === 'voice_voice'
  const useTTS = mode === 'text_voice' || mode === 'voice_voice'

  // Scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isProcessing])

  // Initialize WebSocket connection
  useEffect(() => {
    const ws = createVoiceSocket(sessionId, mode, {
      onQuestion: (msg) => {
        setIsProcessing(false)
        setError(null) // Clear any previous errors

        // Update question number
        setQuestionNumber(msg.question_number)

        // Add AI message
        setMessages(prev => [
          ...prev,
          { role: 'ai', text: msg.text, type: 'question' }
        ])

        // Play audio if TTS mode and audio is provided
        if (useTTS && msg.audio) {
          playAudio(msg.audio)
        }
      },

      onComplete: (msg) => {
        setIsProcessing(false)
        setMessages(prev => [
          ...prev,
          {
            role: 'ai',
            text: 'Thank you for completing the exit interview. Your feedback is valuable and will help us improve the workplace.',
            type: 'closing',
          }
        ])
        setTimeout(() => onComplete(msg.summary, msg.detected_topics), 1200)
      },

      onCrisis: () => {
        setIsProcessing(false)
        setMessages(prev => [
          ...prev,
          {
            role: 'ai',
            text: 'I need to pause this interview. What you have shared is serious and will be handled with complete confidentiality. An HR representative will reach out to you.',
            type: 'crisis',
          }
        ])
        setTimeout(() => onComplete(null, [], true), 1500)
      },

      onError: (err, fatal = false) => {
        setError(err.message)
        setIsProcessing(false)
        if (fatal) {
          setIsFatalError(true)
          setConnectionState('failed')  // Ensure state is failed for fatal errors
        }
      },

      onTranscript: (msg) => {
        // Replace the transcribing placeholder with the real transcribed text
        setMessages(prev => {
          const idx = prev.slice().reverse().findIndex(m => m.transcribing)
          if (idx === -1) return [...prev, { role: 'user', text: msg.text, isVoice: true }]
          const realIdx = prev.length - 1 - idx
          const updated = [...prev]
          updated[realIdx] = { role: 'user', text: msg.text, isVoice: true }
          return updated
        })
        setIsProcessing(true)
        setError(null) // Clear errors on successful transcript
      },

      onConnect: () => {
        console.log('[VoiceInterface] WebSocket connected')
        setError(null) // Clear errors on successful connection
      },

      onStateChange: ({ state, attempts }) => {
        setConnectionState(state)
        setReconnectAttempts(attempts)

        // Only set error messages for 'failed' state - not during normal connecting/reconnecting
        // Don't overwrite existing specific errors with generic message
        if (state === 'failed' && !error) {
          setError('Connection failed. Please check that the backend server is running on port 8000.')
        } else if (state === 'connected' && attempts > 0) {
          // Successfully reconnected - clear any errors
          setError(null)
        } else if (state === 'reconnecting') {
          // Connection was lost - check if there are any pending transcriptions
          setMessages(prev => {
            const hasPendingTranscription = prev.some(m => m.transcribing)
            if (hasPendingTranscription) {
              // Remove the transcribing placeholder since it won't complete
              return prev.filter(m => !m.transcribing)
            }
            return prev
          })
        }
      },

      onClose: (event) => {
        console.log('[VoiceInterface] WebSocket closed')
        // onClose is only called after exhausting all retries - show final error
        if (connectionState === 'failed') {
          setError('Unable to maintain connection. Please refresh the page and try again.')
        }
      }
    })

    wsRef.current = ws

    return () => {
      ws.close()
    }
  }, [sessionId, mode, useTTS, onComplete])

  // Play base64 audio
  const playAudio = useCallback(async (base64Audio) => {
    try {
      setIsPlaying(true)

      // Decode base64 to ArrayBuffer
      const binaryString = atob(base64Audio)
      const bytes = new Uint8Array(binaryString.length)
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i)
      }

      // Create audio context if needed
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)()
      }

      // Decode and play
      const audioBuffer = await audioContextRef.current.decodeAudioData(bytes.buffer)
      const source = audioContextRef.current.createBufferSource()
      source.buffer = audioBuffer
      source.connect(audioContextRef.current.destination)
      source.onended = () => setIsPlaying(false)
      source.start()

    } catch (e) {
      console.error('Audio playback failed:', e)
      setIsPlaying(false)
    }
  }, [])

  // Start recording
  const startRecording = useCallback(async () => {
    const connected = connectionState === 'connected'
    if (isRecording || isProcessing || !connected) return

    setError(null) // Clear previous errors before attempting to record
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })

      // Use WebM/Opus (browser native)
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus'
      })

      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorder.onstop = () => {
        // Stop all tracks
        stream.getTracks().forEach(track => track.stop())

        // Wait for MediaRecorder to finish flushing data
        // Without this delay, the blob may be incomplete/corrupted
        setTimeout(() => {
          // Create blob and send
          const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' })

          if (audioBlob.size === 0) {
            console.warn('[VoiceInterface] Audio blob is empty, not sending')
            setError('Recording was too short or empty. Please try again.')
            return
          }

          if (audioBlob.size < 100) {
            console.warn(`[VoiceInterface] Audio blob suspiciously small (${audioBlob.size} bytes), may be corrupted`)
            setError('Recording failed. Please hold the button longer and try again.')
            return
          }

          console.log(`[VoiceInterface] Sending audio blob: ${audioBlob.size} bytes`)
          setMessages(prev => [...prev, { role: 'user', text: '', isVoice: true, transcribing: true }])
          wsRef.current?.sendAudio(audioBlob)
        }, 100) // 100ms delay to ensure MediaRecorder has flushed all data
      }

      mediaRecorderRef.current = mediaRecorder
      mediaRecorder.start()
      setIsRecording(true)

    } catch (e) {
      console.error('Failed to start recording:', e)
      setError('Microphone access denied. Please allow microphone access.')
    }
  }, [isRecording, isProcessing, connectionState])

  // Stop recording
  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop()
      setIsRecording(false)
    }
  }, [isRecording])

  // Handle text submit (for text_voice mode)
  function handleTextSubmit() {
    const answer = input.trim()
    const connected = connectionState === 'connected'
    if (!answer || isProcessing || !connected) return

    setInput('')
    setError(null)
    setIsProcessing(true)
    setMessages(prev => [...prev, { role: 'user', text: answer }])
    wsRef.current?.sendText(answer)
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleTextSubmit()
    }
  }

  // Manual reconnect handler
  function handleReconnect() {
    setError(null)
    wsRef.current?.reconnect()
  }

  const connected = connectionState === 'connected'
  const canInteract = connected && !isProcessing && !isPlaying

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] max-w-2xl mx-auto">
      {/* Progress bar */}
      <div className="mb-4">
        <ProgressBar current={questionNumber} total={totalQuestions} />
      </div>

      {/* Connection status */}
      {(connectionState === 'connecting' || connectionState === 'reconnecting') && (
        <div className={`mb-2 px-3 py-2 rounded-lg border text-xs ${
          connectionState === 'connecting'
            ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-400'
            : 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400'
        }`}>
          <div className="flex items-center justify-between">
            <span>
              {connectionState === 'connecting' && '🔌 Connecting to voice server...'}
              {connectionState === 'reconnecting' && `🔄 Reconnecting... (attempt ${reconnectAttempts}/5)`}
            </span>
          </div>
          {connectionState === 'reconnecting' && (
            <div className="mt-1 text-[10px] opacity-75">
              If your message was being transcribed, you may need to re-record it.
            </div>
          )}
        </div>
      )}

      {connectionState === 'failed' && (
        <div className="mb-2 px-3 py-2 rounded-lg border text-xs flex items-center justify-between bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-400">
          <span>❌ Connection failed</span>
          <button
            onClick={handleReconnect}
            className="ml-2 px-2 py-1 rounded bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 font-semibold transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 space-y-4">
        {messages.map((msg, i) => (
          <div key={i}>
            {msg.role === 'ai' && (
              <div className="flex items-start gap-3 max-w-[85%]">
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-cyan-100 dark:bg-cyan-900 flex items-center justify-center text-xs font-bold text-cyan-700 dark:text-cyan-300">
                  AI
                </div>
                <div>
                  {msg.type === 'crisis' && (
                    <span className="block text-[10px] font-semibold uppercase tracking-wider text-red-500 dark:text-red-400 mb-1">
                      Interview Paused
                    </span>
                  )}
                  <div className={`px-4 py-3 rounded-2xl rounded-tl-sm text-sm leading-relaxed ${
                    msg.type === 'crisis'
                      ? 'bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-900 dark:text-red-200'
                      : 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100'
                  }`}>
                    {msg.text}
                  </div>
                </div>
              </div>
            )}

            {msg.role === 'user' && (
              <div className="flex flex-col items-end">
                <div className="max-w-[85%] px-4 py-3 rounded-2xl rounded-tr-sm bg-cyan-600 text-white text-sm leading-relaxed">
                  {msg.isVoice && <span className="mr-1">🎤</span>}
                  {msg.transcribing
                    ? <span className="italic opacity-75">Transcribing...</span>
                    : msg.text
                  }
                </div>
              </div>
            )}
          </div>
        ))}

        {/* Processing indicator */}
        {isProcessing && (
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-7 h-7 rounded-full bg-cyan-100 dark:bg-cyan-900 flex items-center justify-center text-xs font-bold text-cyan-700 dark:text-cyan-300">
              AI
            </div>
            <div className="px-1 py-1 rounded-2xl rounded-tl-sm bg-gray-100 dark:bg-gray-800">
              <Spinner />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Error banner */}
      {error && (
        <div className="mt-2 px-3 py-2 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-xs text-red-700 dark:text-red-400">
          <span>{error}</span>
          {isFatalError && onCancel && (
            <button
              onClick={onCancel}
              className="ml-3 px-2 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-semibold transition-colors"
            >
              Change mode
            </button>
          )}
        </div>
      )}

      {/* Speaking indicator */}
      {isPlaying && (
        <div className="mt-2 flex justify-center">
          <SpeakingIndicator />
        </div>
      )}

      {/* Input area */}
      <div className="mt-3">
        {/* Voice input mode */}
        {useSTT && (
          <div className="flex flex-col items-center gap-2">
            <MicButton
              isRecording={isRecording}
              onStart={startRecording}
              onStop={stopRecording}
              disabled={!canInteract}
            />
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {isRecording ? 'Release to send' : connected ? 'Hold to speak' : 'Connecting...'}
            </span>
          </div>
        )}

        {/* Text input mode (for text_voice) */}
        {!useSTT && (
          <div className="flex gap-2">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={!canInteract}
              rows={2}
              placeholder={connected ? "Type your answer... (Enter to send)" : "Connecting..."}
              className="flex-1 resize-none px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 text-sm placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-cyan-500 disabled:opacity-50 transition-colors"
            />
            <button
              onClick={handleTextSubmit}
              disabled={!canInteract || !input.trim()}
              className="px-5 py-3 rounded-xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors self-end"
            >
              Send
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
