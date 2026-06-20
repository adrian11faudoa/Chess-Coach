import { useState } from 'react'

const TIME_CONTROLS = [
  { label: 'Unlimited', value: '' },
  { label: '1 min Bullet', value: '1+0' },
  { label: '2+1 Bullet', value: '2+1' },
  { label: '3 min Blitz', value: '3+0' },
  { label: '3+2 Blitz', value: '3+2' },
  { label: '5 min Blitz', value: '5+0' },
  { label: '10 min Rapid', value: '10+0' },
  { label: '15+10 Rapid', value: '15+10' },
]

const ELO_PRESETS = [
  { label: 'Beginner', elo: 800 },
  { label: 'Club', elo: 1200 },
  { label: 'Intermediate', elo: 1500 },
  { label: 'Advanced', elo: 1800 },
  { label: 'Expert', elo: 2000 },
  { label: 'Master', elo: 2400 },
]

export default function NewGameModal({ onStart, onClose }) {
  const [color, setColor] = useState(1)     // 1=white, 0=black
  const [elo, setElo] = useState(1500)
  const [tc, setTc] = useState('')

  const handleStart = () => {
    const finalColor = color === -1 ? (Math.random() < 0.5 ? 1 : 0) : color
    onStart({ player_color: finalColor, engine_elo: elo, time_control: tc || null })
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-surface-2 rounded-xl shadow-2xl w-full max-w-sm border border-surface-4">
        <div className="px-5 py-4 border-b border-surface-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-white">New Game</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-xl">×</button>
        </div>

        <div className="p-5 space-y-5">
          {/* Color */}
          <div>
            <label className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2 block">
              Play as
            </label>
            <div className="flex gap-2">
              {[['♔ White', 1], ['♚ Black', 0], ['🎲 Random', -1]].map(([label, val]) => (
                <button key={val} onClick={() => setColor(val)}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors border
                    ${color === val
                      ? 'bg-accent border-accent text-white'
                      : 'bg-surface-3 border-surface-4 text-gray-400 hover:border-gray-500'}`}>
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* ELO */}
          <div>
            <label className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2 block">
              Engine Strength — ELO {elo}
            </label>
            <input
              type="range" min={800} max={2800} step={50} value={elo}
              onChange={e => setElo(+e.target.value)}
              className="w-full accent-accent"
            />
            <div className="flex gap-1 mt-2 flex-wrap">
              {ELO_PRESETS.map(p => (
                <button key={p.elo} onClick={() => setElo(p.elo)}
                  className={`px-2 py-1 rounded text-xs transition-colors border
                    ${elo === p.elo ? 'bg-accent border-accent text-white' : 'bg-surface-3 border-surface-4 text-gray-400 hover:border-gray-500'}`}>
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Time control */}
          <div>
            <label className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2 block">
              Time Control
            </label>
            <div className="grid grid-cols-2 gap-1">
              {TIME_CONTROLS.map(t => (
                <button key={t.value} onClick={() => setTc(t.value)}
                  className={`py-1.5 px-2 rounded text-xs transition-colors border
                    ${tc === t.value ? 'bg-accent border-accent text-white' : 'bg-surface-3 border-surface-4 text-gray-400 hover:border-gray-500'}`}>
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="px-5 pb-5 flex gap-2">
          <button onClick={onClose}
            className="flex-1 py-2.5 bg-surface-3 hover:bg-surface-4 text-gray-400 rounded-lg text-sm transition-colors">
            Cancel
          </button>
          <button onClick={handleStart}
            className="flex-1 py-2.5 bg-accent hover:bg-accent-hover text-white font-bold rounded-lg text-sm transition-colors">
            Start Game
          </button>
        </div>
      </div>
    </div>
  )
}
