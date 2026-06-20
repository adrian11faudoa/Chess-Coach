import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import { Chess } from 'chess.js'
import { useGameSocket } from './hooks/useGameSocket'
import ChessBoard from './components/ChessBoard'
import { EvalBar, CoachPanel } from './components/CoachPanel'
import { MoveList, OpeningPanel, AnalysisPanel } from './components/SidePanels'
import NewGameModal from './components/NewGameModal'

// Stable session ID from localStorage
function getSessionId() {
  let id = localStorage.getItem('chesscoach_session')
  if (!id) { id = crypto.randomUUID(); localStorage.setItem('chesscoach_session', id) }
  return id
}

const SESSION_ID = getSessionId()
const MAX_COMMENTS = 12

export default function App() {
  const [fen, setFen] = useState('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
  const [moves, setMoves] = useState([])           // [{san, uci, classification}]
  const [currentMoveIdx, setCurrentMoveIdx] = useState(-1)
  const [legalMoves, setLegalMoves] = useState([]) // UCI strings
  const [lastMove, setLastMove] = useState(null)   // {from, to} alg
  const [engineArrow, setEngineArrow] = useState(null)
  const [flipped, setFlipped] = useState(false)
  const [playerColor, setPlayerColor] = useState(1) // 1=white 0=black
  const [engineThinking, setEngineThinking] = useState(false)
  const [evaluation, setEvaluation] = useState({ cp: 0, desc: '', mateIn: null, lines: [] })
  const [comments, setComments] = useState([])
  const [opening, setOpening] = useState(null)
  const [gameOver, setGameOver] = useState(null)   // {result, reason}
  const [showNewGame, setShowNewGame] = useState(true)
  const [activeTab, setActiveTab] = useState('moves')

  // Derived chess state
  const chess = useMemo(() => { try { return new Chess(fen) } catch { return new Chess() } }, [fen])
  const isPlayerTurn = chess.turn() === (playerColor === 1 ? 'w' : 'b')

  // ── WebSocket handlers ───────────────────────────────────────────────────
  const wsHandlers = {
    connected: (msg) => {
      if (msg.fen) setFen(msg.fen)
    },
    game_started: (msg) => {
      const startFen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
      setFen(msg.fen || startFen)
      setMoves([])
      setCurrentMoveIdx(-1)
      setComments([])
      setOpening(null)
      setGameOver(null)
      setLastMove(null)
      setEngineArrow(null)
      setEvaluation({ cp: 0, desc: '', mateIn: null, lines: [] })
      setPlayerColor(msg.player_color ?? 1)
      setFlipped(msg.player_color === 0)
      setShowNewGame(false)
    },
    move_played: (msg) => {
      setFen(msg.fen)
      setLastMove({ from: indexToAlg(msg.from_sq), to: indexToAlg(msg.to_sq) })
      setCurrentMoveIdx(msg.move_index)

      if (!msg.is_engine) {
        // Optimistically update moves list immediately for player moves
        setMoves(prev => {
          const next = [...prev]
          next[msg.move_index] = { san: msg.san, uci: msg.uci, classification: null }
          return next
        })
      } else {
        setMoves(prev => {
          const next = [...prev]
          next[msg.move_index] = { san: msg.san, uci: msg.uci, classification: null }
          return next
        })
      }
      // Request legal moves for new position
      requestLegalMoves(msg.fen)
    },
    engine_thinking: (msg) => setEngineThinking(msg.thinking),
    analysis_update: (msg) => {
      setEvaluation({
        cp: msg.evaluation,
        desc: msg.eval_description,
        mateIn: msg.mate_in ?? null,
        lines: msg.lines || [],
      })
      if (msg.best_move) {
        const uci = msg.best_move
        setEngineArrow({
          from: uci.slice(0, 2),
          to: uci.slice(2, 4),
        })
      }
    },
    coach_comment: (msg) => {
      setComments(prev => {
        const next = [...prev, { text: msg.text, category: msg.category }]
        return next.slice(-MAX_COMMENTS)
      })
    },
    opening_detected: (msg) => {
      setOpening(msg)
      setActiveTab('opening')
    },
    game_over: (msg) => {
      setGameOver(msg)
      setEngineThinking(false)
    },
    game_loaded: (msg) => {
      setFen(msg.fen)
      setMoves(msg.moves || [])
      setCurrentMoveIdx(msg.move_index)
      setLastMove(null)
      setEngineArrow(null)
    },
    position_set: (msg) => {
      setFen(msg.fen)
      setCurrentMoveIdx(msg.move_index)
      requestLegalMoves(msg.fen)
    },
    legal_moves: (msg) => setLegalMoves(msg.moves || []),
    illegal_move: () => {},
    error: (msg) => console.error('Server error:', msg.message),
    pong: () => {},
    game_saved: () => {},
  }

  const { send, connected, engineReady } = useGameSocket(SESSION_ID, wsHandlers)

  // Request legal moves for current position
  const requestLegalMoves = useCallback((fenStr) => {
    // Compute locally for immediate response
    try {
      const c = new Chess(fenStr || fen)
      setLegalMoves(c.moves({ verbose: true }).map(m => m.from + m.to + (m.promotion || '')))
    } catch {}
  }, [fen])

  // Update legal moves when fen changes
  useEffect(() => { requestLegalMoves(fen) }, [fen])

  // ── Move handler ─────────────────────────────────────────────────────────
  const handleMove = useCallback((fromAlg, toAlg, promo) => {
    if (gameOver) return
    send('move', {
      from: algToIndex(fromAlg),
      to: algToIndex(toAlg),
      promotion: promo,
    })
  }, [send, gameOver])

  // ── Navigation ───────────────────────────────────────────────────────────
  const handleNavigate = (idx) => { send('navigate', { move_index: idx }) }
  const handleStart    = () => { send('navigate', { move_index: 0 }) }
  const handlePrev     = () => { if (currentMoveIdx > 0) send('navigate', { move_index: currentMoveIdx - 1 }) }
  const handleNext     = () => { if (currentMoveIdx < moves.length - 1) send('navigate', { move_index: currentMoveIdx + 1 }) }
  const handleEnd      = () => { send('navigate', { move_index: moves.length - 1 }) }

  // ── New game ─────────────────────────────────────────────────────────────
  const handleNewGame = (opts) => {
    send('new_game', {
      player_color: opts.player_color,
      engine_elo: opts.engine_elo,
      time_control: opts.time_control,
      mode: 'vs_engine',
    })
  }

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
      if (e.key === 'ArrowLeft')  handlePrev()
      if (e.key === 'ArrowRight') handleNext()
      if (e.key === 'Home')       handleStart()
      if (e.key === 'End')        handleEnd()
      if (e.key === 'f')          setFlipped(f => !f)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [currentMoveIdx, moves.length])

  // ── Player info ──────────────────────────────────────────────────────────
  const topName    = playerColor === 1 ? 'Engine' : 'You'
  const bottomName = playerColor === 1 ? 'You' : 'Engine'
  const inCheck = chess.inCheck()

  return (
    <div className="min-h-screen bg-[#141414] text-gray-200 flex flex-col">
      {/* ── Top Bar ── */}
      <header className="flex items-center justify-between px-4 py-2 bg-[#0d0d0d] border-b border-surface-4">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold text-white">♛ ChessCoach</span>
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-500'}`} />
          {!engineReady && connected && (
            <span className="text-xs text-yellow-500">Engine not found — AI disabled</span>
          )}
          {engineThinking && (
            <span className="text-xs text-yellow-400 thinking">Engine thinking...</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setFlipped(f => !f)}
            className="px-3 py-1 bg-surface-3 hover:bg-surface-4 rounded text-xs transition-colors">
            ⇅ Flip
          </button>
          <button onClick={() => send('undo')}
            className="px-3 py-1 bg-surface-3 hover:bg-surface-4 rounded text-xs transition-colors">
            ↩ Undo
          </button>
          <button onClick={() => setShowNewGame(true)}
            className="px-3 py-1 bg-accent hover:bg-accent-hover text-white rounded text-xs font-semibold transition-colors">
            ⊕ New Game
          </button>
        </div>
      </header>

      {/* ── Main Layout ── */}
      <div className="flex flex-1 gap-2 p-2 min-h-0">

        {/* Left: Coach */}
        <div className="hidden lg:flex flex-col w-56 xl:w-64 flex-shrink-0">
          <CoachPanel
            comments={comments}
            evalText={evaluation.desc}
            onHint={() => send('hint')}
            loading={engineThinking}
          />
        </div>

        {/* Center: Board */}
        <div className="flex flex-col flex-1 items-center gap-2 min-w-0">
          {/* Eval bar */}
          <div className="w-full max-w-[min(80vh,600px)]">
            <EvalBar evaluation={evaluation.cp} mateIn={evaluation.mateIn} />
          </div>

          {/* Top player */}
          <PlayerBar name={topName} isActive={!isPlayerTurn && !gameOver} />

          {/* Board */}
          <ChessBoard
            fen={fen}
            flipped={flipped}
            legalMoves={isPlayerTurn && !gameOver ? legalMoves : []}
            lastMove={lastMove}
            engineArrow={engineArrow}
            onMove={handleMove}
            disabled={!isPlayerTurn || !!gameOver || !connected}
          />

          {/* Bottom player */}
          <PlayerBar name={bottomName} isActive={isPlayerTurn && !gameOver} />

          {/* Game over banner */}
          {gameOver && (
            <div className="w-full max-w-[min(80vh,600px)] bg-surface-2 border border-surface-4 rounded-lg p-3 text-center fade-in">
              <div className="text-lg font-bold mb-1">
                {gameOver.result === '1-0' ? '♔ White wins' :
                 gameOver.result === '0-1' ? '♚ Black wins' : '½–½ Draw'}
              </div>
              <div className="text-xs text-gray-500 mb-3 capitalize">{gameOver.reason?.replace(/_/g,' ')}</div>
              <button onClick={() => setShowNewGame(true)}
                className="px-4 py-2 bg-accent hover:bg-accent-hover text-white text-sm font-semibold rounded-lg transition-colors">
                Play Again
              </button>
            </div>
          )}

          {/* Mobile coach (small screens) */}
          {comments.length > 0 && (
            <div className="lg:hidden w-full max-w-[min(80vh,600px)]">
              <div className="bg-surface-2 rounded-lg p-2 text-xs text-gray-300 border border-surface-4">
                {comments[comments.length - 1]?.text}
              </div>
            </div>
          )}
        </div>

        {/* Right: Tabs */}
        <div className="flex flex-col w-52 xl:w-64 flex-shrink-0">
          {/* Tab bar */}
          <div className="flex bg-[#1a1a1a] rounded-t-lg overflow-hidden border border-surface-4 border-b-0">
            {[['moves','Moves'], ['analysis','Lines'], ['opening','Opening']].map(([id, label]) => (
              <button key={id} onClick={() => setActiveTab(id)}
                className={`flex-1 py-2 text-xs font-semibold transition-colors border-b-2
                  ${activeTab === id ? 'text-white border-accent' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
                {label}
              </button>
            ))}
          </div>

          <div className="flex-1 border border-surface-4 border-t-0 rounded-b-lg overflow-hidden">
            {activeTab === 'moves' && (
              <MoveList
                moves={moves}
                currentIndex={currentMoveIdx}
                onSelect={handleNavigate}
                onStart={handleStart}
                onPrev={handlePrev}
                onNext={handleNext}
                onEnd={handleEnd}
              />
            )}
            {activeTab === 'analysis' && <AnalysisPanel lines={evaluation.lines} />}
            {activeTab === 'opening' && <OpeningPanel opening={opening} />}
          </div>

          {/* Resign button */}
          {!gameOver && (
            <button onClick={() => { if(confirm('Resign?')) send('resign') }}
              className="mt-2 py-1.5 bg-surface-3 hover:bg-red-900 text-gray-500 hover:text-red-300 rounded text-xs transition-colors border border-surface-4">
              Resign
            </button>
          )}
        </div>
      </div>

      {/* New Game Modal */}
      {showNewGame && (
        <NewGameModal
          onStart={handleNewGame}
          onClose={() => setShowNewGame(false)}
        />
      )}
    </div>
  )
}

function PlayerBar({ name, isActive }) {
  return (
    <div className={`flex items-center gap-2 w-full max-w-[min(80vh,600px)] px-3 py-1.5 rounded-lg transition-colors
      ${isActive ? 'bg-surface-2 border border-accent/40' : 'bg-[#1a1a1a]'}`}>
      <div className={`w-2 h-2 rounded-full ${isActive ? 'bg-accent' : 'bg-surface-4'}`} />
      <span className="text-sm font-medium text-gray-300">{name}</span>
      {isActive && <span className="text-xs text-accent ml-auto">to move</span>}
    </div>
  )
}

// Coordinate helpers
const FILES = ['a','b','c','d','e','f','g','h']
function indexToAlg(idx) { return FILES[idx % 8] + (Math.floor(idx / 8) + 1) }
function algToIndex(alg)  { return FILES.indexOf(alg[0]) + (parseInt(alg[1]) - 1) * 8 }
