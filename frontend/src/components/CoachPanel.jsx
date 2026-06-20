// EvalBar.jsx — Horizontal evaluation bar
export function EvalBar({ evaluation = 0, mateIn = null }) {
  let whitePct = 50
  if (mateIn !== null) {
    whitePct = mateIn > 0 ? 95 : 5
  } else {
    const x = Math.max(-6, Math.min(6, evaluation / 100))
    whitePct = (1 / (1 + Math.exp(-x))) * 100
  }

  const label = mateIn !== null
    ? (mateIn > 0 ? `M${mateIn}` : `M${-mateIn}`)
    : (Math.abs(evaluation) < 9999 ? (evaluation >= 0 ? `+${(evaluation/100).toFixed(1)}` : (evaluation/100).toFixed(1)) : '0.0')

  return (
    <div className="w-full h-5 bg-[#1a1a1a] rounded overflow-hidden relative flex items-center">
      <div
        className="eval-bar h-full bg-[#eeeeee] absolute left-0 top-0"
        style={{ width: `${whitePct}%` }}
      />
      <span className="absolute left-1/2 -translate-x-1/2 text-xs font-bold font-mono text-[#444] mix-blend-difference z-10">
        {label}
      </span>
    </div>
  )
}

// CoachPanel.jsx — Real-time coaching commentary
const CATEGORY_STYLES = {
  tactical:   { icon: '⚔️', color: '#FF6B35', bg: '#2A1500' },
  strategic:  { icon: '♟️', color: '#4FC3F7', bg: '#001A2A' },
  plan:       { icon: '💡', color: '#81C784', bg: '#001A00' },
  warning:    { icon: '⚠️', color: '#FFB74D', bg: '#2A1A00' },
  opening:    { icon: '📖', color: '#CE93D8', bg: '#1A0029' },
  evaluation: { icon: '📊', color: '#80CBC4', bg: '#001A18' },
  endgame:    { icon: '👑', color: '#F48FB1', bg: '#2A0018' },
}

export function CoachPanel({ comments = [], evalText = '', onHint, loading = false }) {
  return (
    <div className="flex flex-col h-full bg-surface rounded-lg overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 bg-[#1a1a1a] border-b border-surface-4 flex items-center justify-between">
        <span className="text-xs font-bold tracking-widest text-gray-500">COACH</span>
        {loading && <span className="text-xs text-yellow-400 thinking">analysing...</span>}
      </div>

      {/* Eval description */}
      {evalText && (
        <div className="px-3 py-2 text-xs text-gray-400 border-b border-surface-4 bg-[#1c1c1c]">
          {evalText}
        </div>
      )}

      {/* Comments */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {comments.length === 0 && (
          <p className="text-xs text-gray-600 text-center mt-4">
            Make a move to get coaching feedback.
          </p>
        )}
        {comments.map((c, i) => {
          const style = CATEGORY_STYLES[c.category] || CATEGORY_STYLES.evaluation
          return (
            <div
              key={i}
              className="fade-in flex gap-2 p-2 rounded-md text-xs leading-relaxed"
              style={{ background: style.bg, borderLeft: `3px solid ${style.color}` }}
            >
              <span className="text-sm flex-shrink-0">{style.icon}</span>
              <div>
                <div className="font-bold mb-0.5 uppercase tracking-wide text-[10px]"
                     style={{ color: style.color }}>
                  {c.category}
                </div>
                <div className="text-gray-300">{c.text}</div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Hint button */}
      <div className="p-2 border-t border-surface-4 bg-[#1a1a1a]">
        <button
          onClick={onHint}
          className="w-full py-1.5 bg-accent hover:bg-accent-hover text-white text-xs font-semibold rounded transition-colors"
        >
          💡 Get Hint
        </button>
      </div>
    </div>
  )
}
