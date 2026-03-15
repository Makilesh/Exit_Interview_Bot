import { useState } from 'react'
import { startSession } from '../api.js'

const MODES = [
  {
    id: 'text_text',
    label: 'Text → Text',
    icon: '💬',
    description: 'Type your answers, read the questions.',
    active: true,
  },
  {
    id: 'voice_text',
    label: 'Voice → Text',
    icon: '🎤',
    description: 'Speak your answers, read the questions.',
    active: false,
  },
  {
    id: 'text_voice',
    label: 'Text → Voice',
    icon: '🔊',
    description: 'Type your answers, hear the questions spoken aloud.',
    active: false,
  },
  {
    id: 'voice_voice',
    label: 'Voice → Voice',
    icon: '🎙️',
    description: 'Fully spoken interview — speak and listen.',
    active: false,
  },
]

export default function ModeSelector({ onSelect }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [phase2Toast, setPhase2Toast] = useState(false)

  // Phase 2: on mode select, check /health for voice endpoint availability
  // If voice WebSocket is live, unlock voice modes dynamically

  async function handleSelect(modeId) {
    if (modeId !== 'text_text') {
      setPhase2Toast(true)
      setTimeout(() => setPhase2Toast(false), 3000)
      return
    }
    setError(null)
    setLoading(true)
    try {
      const data = await startSession(modeId)
      onSelect(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col items-center gap-8">
      {/* Heading */}
      <div className="text-center">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Exit Interview
        </h1>
        <p className="mt-1 text-gray-500 dark:text-gray-400 max-w-sm">
          Select your preferred interview mode to begin.
        </p>
      </div>

      {/* Mode cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-xl">
        {MODES.map(mode => (
          <button
            key={mode.id}
            onClick={() => handleSelect(mode.id)}
            disabled={loading}
            className={`
              relative text-left p-5 rounded-xl border-2 transition-all duration-150
              ${mode.active
                ? 'border-cyan-500 bg-white dark:bg-gray-900 hover:shadow-md hover:border-cyan-400 cursor-pointer'
                : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:border-gray-300 dark:hover:border-gray-600 cursor-pointer opacity-80'
              }
              ${loading ? 'opacity-50 cursor-not-allowed' : ''}
            `}
          >
            {/* Phase 2 badge */}
            {!mode.active && (
              <span className="absolute top-3 right-3 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-700">
                Phase 2
              </span>
            )}

            <span className="text-2xl">{mode.icon}</span>
            <h3 className="mt-2 font-semibold text-gray-900 dark:text-gray-100">
              {mode.label}
            </h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {mode.description}
            </p>

            {mode.active && (
              <span className="mt-3 inline-block text-xs font-medium text-cyan-600 dark:text-cyan-400">
                {loading ? 'Starting…' : 'Click to begin →'}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="w-full max-w-xl p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Phase 2 toast */}
      {phase2Toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 px-5 py-3 rounded-xl bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 text-sm shadow-xl transition-all">
          Voice modes are coming soon. The voice engine is being integrated in Phase 2.
        </div>
      )}
    </div>
  )
}
