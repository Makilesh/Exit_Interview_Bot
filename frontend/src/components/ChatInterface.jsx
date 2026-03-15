import { useState, useEffect, useRef } from 'react'
import { sendResponse } from '../api.js'
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

function decisionLabel(decision) {
  if (!decision) return null
  const { decision: d, reason: r } = decision
  const label = d === 'ask_followup' ? '↩ follow-up requested' : '✓ moving to next question'
  return `${label} · ${r.replace(/_/g, ' ')}`
}

export default function ChatInterface({ sessionId, firstQuestion, totalQuestions, onComplete }) {
  const [messages, setMessages] = useState([
    { role: 'ai', text: firstQuestion, type: 'question' }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [questionNumber, setQuestionNumber] = useState(1)
  const bottomRef = useRef(null)

  // Scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function handleSubmit() {
    const answer = input.trim()
    if (!answer || loading) return

    setInput('')
    setError(null)

    // Optimistically add user message (decision filled in after API responds)
    setMessages(prev => [...prev, { role: 'user', text: answer }])
    setLoading(true)

    try {
      const data = await sendResponse(sessionId, answer)

      // Update the last user message with the decision
      setMessages(prev => {
        const updated = [...prev]
        const lastUserIdx = [...updated].reverse().findIndex(m => m.role === 'user')
        if (lastUserIdx !== -1) {
          const idx = updated.length - 1 - lastUserIdx
          updated[idx] = {
            ...updated[idx],
            decision: data.agent_decision,
          }
        }
        return updated
      })

      if (data.is_complete) {
        // Show completion AI message, then hand off to summary
        setMessages(prev => [
          ...prev,
          {
            role: 'ai',
            text: 'Thank you for completing the exit interview. Your feedback is valuable and will help us improve the workplace. We wish you all the best.',
            type: 'closing',
          },
        ])
        setTimeout(() => onComplete(data.summary, data.detected_topics), 1200)
      } else {
        // Update question counter (only on primary questions, not follow-ups)
        if (!data.follow_up) {
          setQuestionNumber(data.question_number)
        }

        // Add next AI message
        setMessages(prev => [
          ...prev,
          {
            role: 'ai',
            text: data.next_question,
            type: data.follow_up ? 'followup' : 'question',
          },
        ])
      }
    } catch (e) {
      setError(e.message)
      // Remove the optimistic user message on hard error
      setMessages(prev => prev.slice(0, -1))
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] max-w-2xl mx-auto">
      {/* Progress bar */}
      <div className="mb-4">
        <ProgressBar current={questionNumber} total={totalQuestions} />
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 space-y-4">
        {messages.map((msg, i) => (
          <div key={i}>
            {msg.role === 'ai' && (
              <div className="flex items-start gap-3 max-w-[85%]">
                {/* Avatar */}
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-cyan-100 dark:bg-cyan-900 flex items-center justify-center text-xs font-bold text-cyan-700 dark:text-cyan-300">
                  AI
                </div>
                <div>
                  {msg.type === 'followup' && (
                    <span className="block text-[10px] font-semibold uppercase tracking-wider text-amber-500 dark:text-amber-400 mb-1">
                      Follow-up
                    </span>
                  )}
                  <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 text-sm leading-relaxed">
                    {msg.text}
                  </div>
                </div>
              </div>
            )}

            {msg.role === 'user' && (
              <div className="flex flex-col items-end">
                <div className="max-w-[85%] px-4 py-3 rounded-2xl rounded-tr-sm bg-cyan-600 text-white text-sm leading-relaxed">
                  {msg.text}
                </div>
                {msg.decision && (
                  <span className="mt-1 text-[11px] text-gray-400 dark:text-gray-500 italic pr-1">
                    {decisionLabel(msg.decision)}
                  </span>
                )}
              </div>
            )}
          </div>
        ))}

        {/* Typing indicator */}
        {loading && (
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
          {error}
        </div>
      )}

      {/* Input bar */}
      <div className="mt-3 flex gap-2">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          rows={2}
          placeholder="Type your answer… (Enter to send)"
          className="flex-1 resize-none px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 text-sm placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-cyan-500 disabled:opacity-50 transition-colors"
        />
        <button
          onClick={handleSubmit}
          disabled={loading || !input.trim()}
          className="px-5 py-3 rounded-xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold transition-colors self-end"
        >
          Send
        </button>
      </div>
    </div>
  )
}
