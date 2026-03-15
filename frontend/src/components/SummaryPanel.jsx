import { downloadFile } from '../api.js'

const SENTIMENT_STYLES = {
  positive: {
    dot: 'bg-emerald-500',
    text: 'text-emerald-700 dark:text-emerald-400',
    badge: 'bg-emerald-50 dark:bg-emerald-900/30 border-emerald-200 dark:border-emerald-700',
  },
  neutral: {
    dot: 'bg-amber-400',
    text: 'text-amber-700 dark:text-amber-400',
    badge: 'bg-amber-50 dark:bg-amber-900/30 border-amber-200 dark:border-amber-700',
  },
  negative: {
    dot: 'bg-red-500',
    text: 'text-red-700 dark:text-red-400',
    badge: 'bg-red-50 dark:bg-red-900/30 border-red-200 dark:border-red-700',
  },
}

function Section({ title, children }) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-2">
        {title}
      </h3>
      {children}
    </div>
  )
}

export default function SummaryPanel({ summary, detectedTopics, sessionId, onRestart }) {
  if (!summary) {
    return (
      <div className="text-center text-gray-400 dark:text-gray-500 py-16">
        Summary not available.
      </div>
    )
  }

  const sentiment = summary.sentiment ?? 'neutral'
  const style = SENTIMENT_STYLES[sentiment] ?? SENTIMENT_STYLES.neutral
  const confPct = Math.round((summary.confidence_score ?? 0) * 100)

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div className="text-center space-y-1">
        <div className="inline-block px-3 py-1 rounded-full text-xs font-medium bg-cyan-100 dark:bg-cyan-900/40 text-cyan-700 dark:text-cyan-300 border border-cyan-200 dark:border-cyan-800">
          Interview Complete
        </div>
        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
          Exit Interview Summary
        </h2>
        <p className="text-xs text-gray-400 dark:text-gray-500">Session {sessionId}</p>
      </div>

      {/* Card */}
      <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 divide-y divide-gray-100 dark:divide-gray-800">

        {/* Primary exit reason */}
        <div className="p-5">
          <Section title="Primary Exit Reason">
            <p className="text-base font-semibold text-gray-900 dark:text-gray-100">
              {summary.primary_exit_reason}
            </p>
          </Section>
        </div>

        {/* Sentiment + Confidence side by side */}
        <div className="p-5 grid grid-cols-2 gap-6">
          <Section title="Overall Sentiment">
            <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm font-medium ${style.badge} ${style.text}`}>
              <span className={`w-2 h-2 rounded-full ${style.dot}`} />
              {sentiment.charAt(0).toUpperCase() + sentiment.slice(1)}
            </div>
          </Section>

          <Section title="Confidence Score">
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                  {confPct}%
                </span>
              </div>
              <div className="h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
                <div
                  className="h-full rounded-full bg-cyan-500 transition-all duration-700"
                  style={{ width: `${confPct}%` }}
                />
              </div>
            </div>
          </Section>
        </div>

        {/* Top positives */}
        {summary.top_positives?.length > 0 && (
          <div className="p-5">
            <Section title="Top Positives">
              <ul className="space-y-1.5">
                {summary.top_positives.map((item, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <span className="text-emerald-500 mt-0.5">✓</span>
                    {item}
                  </li>
                ))}
              </ul>
            </Section>
          </div>
        )}

        {/* Improvement areas */}
        {summary.improvement_areas?.length > 0 && (
          <div className="p-5">
            <Section title="Improvement Areas">
              <ul className="space-y-1.5">
                {summary.improvement_areas.map((item, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <span className="text-amber-500 mt-0.5">→</span>
                    {item}
                  </li>
                ))}
              </ul>
            </Section>
          </div>
        )}

        {/* Detected topics */}
        {detectedTopics?.length > 0 && (
          <div className="p-5">
            <Section title="Detected Topics">
              <div className="flex flex-wrap gap-2">
                {detectedTopics.map(topic => (
                  <span
                    key={topic}
                    className="px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700"
                  >
                    {topic.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            </Section>
          </div>
        )}

        {/* HR flag */}
        {summary.flag_for_hr && (
          <div className="p-5">
            <div className="flex gap-3 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
              <span className="text-red-500 text-lg flex-shrink-0">⚠</span>
              <div>
                <p className="text-sm font-semibold text-red-800 dark:text-red-300">
                  HR Escalation Required
                </p>
                <p className="mt-0.5 text-sm text-red-700 dark:text-red-400">
                  {summary.flag_reason ?? 'This session has been flagged for HR review.'}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Downloads */}
      {sessionId && (
        <div>
          <p className="text-xs text-center text-gray-400 dark:text-gray-500 mb-3">Download session data</p>
          <div className="flex justify-center gap-3">
            {[
              { type: 'json', label: 'JSON', icon: '{ }' },
              { type: 'summary', label: 'Summary', icon: '📄' },
              { type: 'transcript', label: 'Transcript', icon: '📝' },
            ].map(({ type, label, icon }) => (
              <button
                key={type}
                onClick={() => downloadFile(sessionId, type)}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-600 transition-colors"
              >
                <span>{icon}</span>
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Restart */}
      <div className="text-center pb-4">
        <button
          onClick={onRestart}
          className="text-sm text-gray-400 dark:text-gray-500 hover:text-cyan-600 dark:hover:text-cyan-400 underline-offset-2 hover:underline transition-colors"
        >
          Start a new interview
        </button>
      </div>
    </div>
  )
}
