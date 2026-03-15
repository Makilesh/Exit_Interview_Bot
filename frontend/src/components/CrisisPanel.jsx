export default function CrisisPanel({ onRestart }) {
  return (
    <div className="max-w-lg mx-auto py-8 space-y-6">
      {/* Alert box */}
      <div className="p-6 rounded-2xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-center">
        <div className="text-4xl mb-4">🔴</div>
        <h2 className="text-xl font-bold text-red-700 dark:text-red-400 mb-2">
          Interview Paused
        </h2>
        <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
          What you have shared is serious. This has been securely logged and will
          be escalated to HR with complete confidentiality.
        </p>
      </div>

      {/* What happens next */}
      <div className="p-5 rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm text-gray-700 dark:text-gray-300 space-y-3">
        <p className="font-semibold text-gray-900 dark:text-gray-100">What happens next</p>
        <ul className="space-y-2">
          {[
            'Your response has been securely saved.',
            'An HR representative will follow up with you directly.',
            'You are protected from any form of retaliation.',
          ].map((item, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="text-red-500 dark:text-red-400 mt-0.5">•</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Support nudge */}
      <div className="p-4 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-xs text-amber-800 dark:text-amber-300">
        If you need immediate support, please contact your HR team directly or
        reach out to a confidential employee assistance programme (EAP).
      </div>

      {/* Restart link */}
      <div className="text-center">
        <button
          onClick={onRestart}
          className="text-sm text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 underline underline-offset-2 transition-colors"
        >
          Return to home
        </button>
      </div>
    </div>
  )
}
