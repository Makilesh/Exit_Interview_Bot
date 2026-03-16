import { useState } from 'react'
import { startSession } from '../api.js'

const MODES = [
  {
    id: 'text_text',
    label: 'Text → Text',
    icon: '💬',
    description: 'Type your answers, read the questions.',
  },
  {
    id: 'voice_text',
    label: 'Voice → Text',
    icon: '🎤',
    description: 'Speak your answers, read the questions.',
  },
  {
    id: 'text_voice',
    label: 'Text → Voice',
    icon: '🔊',
    description: 'Type your answers, hear the questions spoken aloud.',
  },
  {
    id: 'voice_voice',
    label: 'Voice → Voice',
    icon: '🎙️',
    description: 'Fully spoken interview — speak and listen.',
  },
]

export default function ModeSelector({ onSelect }) {
  const [loading, setLoading] = useState(false)
  const [loadingMode, setLoadingMode] = useState(null)
  const [error, setError] = useState(null)

  async function handleSelect(modeId) {
    setError(null)
    setLoading(true)
    setLoadingMode(modeId)
    try {
      const data = await startSession(modeId)
      onSelect({ ...data, mode: modeId })
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
      setLoadingMode(null)
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
              border-cyan-500 bg-white dark:bg-gray-900 hover:shadow-md hover:border-cyan-400 cursor-pointer
              ${loading ? 'opacity-50 cursor-not-allowed' : ''}
            `}
          >
            <span className="text-2xl">{mode.icon}</span>
            <h3 className="mt-2 font-semibold text-gray-900 dark:text-gray-100">
              {mode.label}
            </h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {mode.description}
            </p>
            <span className="mt-3 inline-block text-xs font-medium text-cyan-600 dark:text-cyan-400">
              {loadingMode === mode.id ? 'Starting...' : 'Click to begin →'}
            </span>
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="w-full max-w-xl p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-400">
          {error}
        </div>
      )}
    </div>
  )
}
