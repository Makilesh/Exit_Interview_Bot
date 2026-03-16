import { useState, useEffect } from 'react'
import ModeSelector from './components/ModeSelector.jsx'
import ChatInterface from './components/ChatInterface.jsx'
import VoiceInterface from './components/VoiceInterface.jsx'
import SummaryPanel from './components/SummaryPanel.jsx'
import CrisisPanel from './components/CrisisPanel.jsx'

export default function App() {
  const [view, setView] = useState('select')        // 'select' | 'interview' | 'summary' | 'crisis'
  const [dark, setDark] = useState(true)

  useEffect(() => {
    document.documentElement.classList.add('dark')
  }, [])
  const [sessionId, setSessionId] = useState(null)
  const [firstQuestion, setFirstQuestion] = useState('')
  const [totalQuestions, setTotalQuestions] = useState(6)
  const [mode, setMode] = useState('text_text')
  const [summary, setSummary] = useState(null)
  const [detectedTopics, setDetectedTopics] = useState([])

  function handleDark() {
    setDark(d => !d)
    document.documentElement.classList.toggle('dark')
  }

  function handleModeSelect(data) {
    // data = { session_id, first_question, question_number, total_questions, mode }
    setSessionId(data.session_id)
    setFirstQuestion(data.first_question)
    setTotalQuestions(data.total_questions)
    setMode(data.mode || 'text_text')
    setView('interview')
  }

  function handleComplete(summaryData, topics, isCrisis = false) {
    setSummary(summaryData)
    setDetectedTopics(topics || [])
    setView(isCrisis ? 'crisis' : 'summary')
  }

  function handleCancel() {
    setSessionId(null)
    setFirstQuestion('')
    setMode('text_text')
    setView('select')
  }

  function handleRestart() {
    setSessionId(null)
    setFirstQuestion('')
    setMode('text_text')
    setSummary(null)
    setDetectedTopics([])
    setView('select')
  }

  return (
    <div className={`min-h-screen bg-gray-50 dark:bg-gray-950 transition-colors duration-200`}>
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 backdrop-blur">
        <div className="max-w-4xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-cyan-600 dark:text-cyan-400 font-bold tracking-tight text-lg">
              AceNgage
            </span>
            <span className="text-xs text-gray-400 dark:text-gray-500 font-medium">
              AI Exit Interview System
            </span>
          </div>
          <button
            onClick={handleDark}
            className="p-2 rounded-md text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            aria-label="Toggle dark mode"
          >
            {dark ? '☀️' : '🌙'}
          </button>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-4xl mx-auto px-4 py-8">
        {view === 'select' && (
          <ModeSelector onSelect={handleModeSelect} />
        )}
        {view === 'interview' && mode === 'text_text' && (
          <ChatInterface
            sessionId={sessionId}
            firstQuestion={firstQuestion}
            totalQuestions={totalQuestions}
            onComplete={handleComplete}
          />
        )}
        {view === 'interview' && mode !== 'text_text' && (
          <VoiceInterface
            sessionId={sessionId}
            firstQuestion={firstQuestion}
            totalQuestions={totalQuestions}
            mode={mode}
            onComplete={handleComplete}
            onCancel={handleCancel}
          />
        )}
        {view === 'summary' && (
          <SummaryPanel
            summary={summary}
            detectedTopics={detectedTopics}
            sessionId={sessionId}
            onRestart={handleRestart}
          />
        )}
        {view === 'crisis' && (
          <CrisisPanel onRestart={handleRestart} />
        )}
      </main>
    </div>
  )
}
