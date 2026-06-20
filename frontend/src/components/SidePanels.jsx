// MoveList.jsx
const QUALITY_SYMBOLS = {
  best: '!', good: '', inaccuracy: '?!', mistake: '?', blunder: '??'
}
const QUALITY_COLORS = {
  best: '#4caf50', good: 'transparent', inaccuracy: '#ffc107',
  mistake: '#ff9800', blunder: '#f44336',
}

export function MoveList({ moves = [], currentIndex = -1, onSelect, onStart, onPrev, onNext, onEnd }) {
  const pairs = []
  for (let i = 0; i < moves.length; i += 2) {
    pairs.push({ white: moves[i], black: moves[i + 1], num: Math.floor(i / 2) + 1, wi: i, bi: i + 1 })
  }

  return (
    <div className="flex flex-col h-full bg-surface rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-[#1a1a1a] border-b border-surface-4 flex items-center justify-between">
        <span className="text-xs font-bold tracking-widest text-gray-500">MOVES</span>
        <span className="text-xs text-gray-600">{moves.length ? `${Math.ceil(moves.length/2)} moves` : ''}</span>
      </div>

      {/* Nav buttons */}
      <div className="flex gap-1 px-2 py-1.5 bg-[#1c1c1c] border-b border-surface-4">
        {[['⏮', onStart], ['◀', onPrev], ['▶', onNext], ['⏭', onEnd]].map(([icon, fn], i) => (
          <button key={i} onClick={fn}
            className="flex-1 py-1 bg-surface-3 hover:bg-surface-4 rounded text-sm transition-colors">
            {icon}
          </button>
        ))}
      </div>

      {/* Move pairs */}
      <div className="flex-1 overflow-y-auto p-1.5">
        {pairs.length === 0 && (
          <p className="text-xs text-gray-600 text-center mt-4">No moves yet.</p>
        )}
        {pairs.map(({ white, black, num, wi, bi }) => (
          <div key={num} className="flex items-center gap-1 mb-0.5">
            <span className="text-xs text-gray-600 w-6 text-right flex-shrink-0">{num}.</span>
            <MoveToken move={white} index={wi} current={currentIndex === wi} onSelect={onSelect} />
            {black && <MoveToken move={black} index={bi} current={currentIndex === bi} onSelect={onSelect} />}
          </div>
        ))}
      </div>
    </div>
  )
}

function MoveToken({ move, index, current, onSelect }) {
  if (!move) return <div className="flex-1" />
  const sym = QUALITY_SYMBOLS[move.classification] || ''
  const borderColor = QUALITY_COLORS[move.classification] || 'transparent'
  return (
    <button
      onClick={() => onSelect(index)}
      className={`flex-1 py-0.5 px-1.5 rounded text-xs font-medium text-left transition-colors truncate
        ${current ? 'bg-accent text-white' : 'bg-surface-2 text-gray-300 hover:bg-surface-3'}`}
      style={{ borderLeft: `2px solid ${borderColor}` }}
    >
      {move.san}{sym}
    </button>
  )
}

// OpeningPanel.jsx
export function OpeningPanel({ opening }) {
  if (!opening) return (
    <div className="p-3 text-xs text-gray-600 text-center">No opening detected yet.</div>
  )
  return (
    <div className="p-3 space-y-3">
      <div>
        <div className="text-sm font-bold text-gray-100">{opening.name}</div>
        <div className="text-xs text-gray-500 mt-0.5">ECO: {opening.eco}</div>
      </div>
      {opening.description && (
        <p className="text-xs text-gray-400 leading-relaxed">{opening.description}</p>
      )}
      {opening.strategic_ideas?.length > 0 && (
        <div>
          <div className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">Strategic Ideas</div>
          <ul className="space-y-0.5">
            {opening.strategic_ideas.slice(0, 3).map((idea, i) => (
              <li key={i} className="text-xs text-gray-400 flex gap-1">
                <span className="text-accent">•</span>{idea}
              </li>
            ))}
          </ul>
        </div>
      )}
      {opening.typical_plans?.length > 0 && (
        <div>
          <div className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-1">Typical Plans</div>
          <ul className="space-y-0.5">
            {opening.typical_plans.slice(0, 4).map((plan, i) => (
              <li key={i} className="text-xs text-gray-400 flex gap-1">
                <span className="text-green-600">▸</span>{plan}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

// AnalysisPanel.jsx
export function AnalysisPanel({ lines = [] }) {
  if (!lines.length) return (
    <div className="p-3 text-xs text-gray-600 text-center">No analysis yet.</div>
  )
  return (
    <div className="p-2 space-y-2">
      {lines.map((line, i) => (
        <div key={i} className="bg-surface-2 rounded p-2">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono font-bold text-accent">{line.score}</span>
            <span className="text-[10px] text-gray-600">depth {line.depth}</span>
          </div>
          <div className="text-xs text-gray-300 font-mono leading-relaxed">
            {line.moves.join(' ')}
          </div>
        </div>
      ))}
    </div>
  )
}
