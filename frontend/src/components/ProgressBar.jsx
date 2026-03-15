export default function ProgressBar({ current, total }) {
  const pct = Math.round((current / total) * 100)

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap">
        Question {current} of {total}
      </span>
      <div className="flex-1 h-1.5 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
        <div
          className="h-full rounded-full bg-cyan-500 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-medium text-gray-400 dark:text-gray-500 w-8 text-right">
        {pct}%
      </span>
    </div>
  )
}
