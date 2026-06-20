import { useState, useCallback, useRef, useEffect } from 'react'
import { Chess } from 'chess.js'

// Unicode pieces — crisp, no external deps
const PIECES = {
  wK:'♔', wQ:'♕', wR:'♖', wB:'♗', wN:'♘', wP:'♙',
  bK:'♚', bQ:'♛', bR:'♜', bB:'♝', bN:'♞', bP:'♟',
}

const FILES = ['a','b','c','d','e','f','g','h']

export default function ChessBoard({
  fen,
  flipped = false,
  legalMoves = [],      // UCI strings
  lastMove = null,      // { from, to } alg squares
  engineArrow = null,   // { from, to } alg squares
  onMove,               // (fromAlg, toAlg, promotion) => void
  disabled = false,
  showCoords = true,
  theme = 'classic',
}) {
  const [selected, setSelected] = useState(null)      // alg square
  const [dragging, setDragging] = useState(null)      // { alg, piece }
  const [dragPos, setDragPos] = useState({ x: 0, y: 0 })
  const [promotion, setPromotion] = useState(null)    // { from, to }
  const boardRef = useRef(null)

  const chess = new Chess(fen)
  const board = chess.board()  // 8x8 array [rank8..rank1][a..h]

  // Parse legal moves into a set for fast lookup
  const legalSet = new Set(legalMoves)

  // Legal destinations for selected square
  const legalDests = selected
    ? legalMoves.filter(m => m.slice(0, 2) === selected).map(m => m.slice(2, 4))
    : []

  // Determine if promotion needed
  const needsPromotion = (fromAlg, toAlg) => {
    const piece = chess.get(fromAlg)
    if (!piece || piece.type !== 'p') return false
    const toRank = parseInt(toAlg[1])
    return (piece.color === 'w' && toRank === 8) || (piece.color === 'b' && toRank === 1)
  }

  const attemptMove = useCallback((fromAlg, toAlg) => {
    if (!onMove) return
    const uci = fromAlg + toAlg
    // Check if any legal move matches (with any promotion)
    const hasMove = legalMoves.some(m => m.slice(0, 4) === uci)
    if (!hasMove) return

    if (needsPromotion(fromAlg, toAlg)) {
      setPromotion({ from: fromAlg, to: toAlg })
    } else {
      onMove(fromAlg, toAlg, null)
    }
    setSelected(null)
  }, [legalMoves, onMove, fen])

  const handleSquareClick = useCallback((alg) => {
    if (disabled) return
    const piece = chess.get(alg)
    const turn = chess.turn()

    if (selected) {
      if (selected === alg) { setSelected(null); return }
      if (legalDests.includes(alg)) {
        attemptMove(selected, alg)
      } else if (piece && piece.color === turn) {
        setSelected(alg)
      } else {
        setSelected(null)
      }
    } else {
      if (piece && piece.color === turn) setSelected(alg)
    }
  }, [selected, legalDests, disabled, chess, attemptMove])

  // ── Drag handlers ────────────────────────────────────────────────────────
  const getBoardCoords = (clientX, clientY) => {
    const rect = boardRef.current?.getBoundingClientRect()
    if (!rect) return null
    const sqSize = rect.width / 8
    let file = Math.floor((clientX - rect.left) / sqSize)
    let rank = Math.floor((clientY - rect.top) / sqSize)
    if (flipped) { file = 7 - file; rank = 7 - rank }
    else rank = 7 - rank
    if (file < 0 || file > 7 || rank < 0 || rank > 7) return null
    return FILES[file] + (rank + 1)
  }

  const handleMouseDown = (e, alg) => {
    if (disabled || e.button !== 0) return
    const piece = chess.get(alg)
    if (!piece || piece.color !== chess.turn()) return
    e.preventDefault()
    setSelected(alg)
    setDragging({ alg, piece: piece.color + piece.type.toUpperCase() })
    setDragPos({ x: e.clientX, y: e.clientY })
  }

  useEffect(() => {
    if (!dragging) return
    const onMove_ = (e) => setDragPos({ x: e.clientX, y: e.clientY })
    const onUp = (e) => {
      const dest = getBoardCoords(e.clientX, e.clientY)
      if (dest && dest !== dragging.alg && legalMoves.some(m => m.slice(0,4) === dragging.alg + dest)) {
        attemptMove(dragging.alg, dest)
      }
      setDragging(null)
    }
    window.addEventListener('mousemove', onMove_)
    window.addEventListener('mouseup', onUp)
    return () => { window.removeEventListener('mousemove', onMove_); window.removeEventListener('mouseup', onUp) }
  }, [dragging, legalMoves, attemptMove])

  // ── Render ───────────────────────────────────────────────────────────────
  const renderSquares = () => {
    const squares = []
    const displayRanks = flipped ? [...Array(8).keys()] : [...Array(8).keys()].reverse()
    const displayFiles = flipped ? [...Array(8).keys()].reverse() : [...Array(8).keys()]

    displayRanks.forEach((rankIdx) => {
      displayFiles.forEach((fileIdx) => {
        const alg = FILES[fileIdx] + (rankIdx + 1)
        const isLight = (fileIdx + rankIdx) % 2 === 0
        const piece = chess.get(alg)
        const pieceKey = piece ? piece.color + piece.type.toUpperCase() : null

        const isSelected   = selected === alg
        const isLastFrom   = lastMove?.from === alg
        const isLastTo     = lastMove?.to === alg
        const isLegalDest  = legalDests.includes(alg)
        const isCaptureDst = isLegalDest && !!piece
        const inCheck      = chess.inCheck() && piece?.type === 'k' && piece.color === chess.turn()
        const isDragSrc    = dragging?.alg === alg

        let sqClass = isLight ? 'sq-light' : 'sq-dark'
        if (isLastFrom || isLastTo) sqClass += ' last-move'
        if (isSelected) sqClass += ' sq-selected'
        if (inCheck) sqClass += ' sq-check'

        squares.push(
          <div
            key={alg}
            className={`${sqClass} relative cursor-pointer select-none`}
            style={{ aspectRatio: '1' }}
            onClick={() => handleSquareClick(alg)}
          >
            {/* Coordinate labels */}
            {showCoords && fileIdx === (flipped ? 7 : 0) && (
              <span className="absolute top-0.5 left-0.5 text-[10px] font-bold opacity-60 leading-none">
                {rankIdx + 1}
              </span>
            )}
            {showCoords && rankIdx === (flipped ? 7 : 0) && (
              <span className="absolute bottom-0.5 right-1 text-[10px] font-bold opacity-60 leading-none">
                {FILES[fileIdx]}
              </span>
            )}

            {/* Legal move indicator */}
            {isLegalDest && !isCaptureDst && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
                <div className="w-[32%] h-[32%] rounded-full bg-black/25" />
              </div>
            )}
            {isCaptureDst && (
              <div className="absolute inset-0 border-4 border-black/30 rounded pointer-events-none z-10 box-border" />
            )}

            {/* Piece */}
            {piece && !isDragSrc && (
              <div
                className="absolute inset-0 flex items-center justify-center text-[min(5.5vw,48px)] leading-none z-20 cursor-grab active:cursor-grabbing"
                style={{
                  filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.6))',
                  userSelect: 'none',
                }}
                onMouseDown={(e) => handleMouseDown(e, alg)}
              >
                <span style={{
                  color: piece.color === 'w' ? '#fff' : '#1a1a1a',
                  WebkitTextStroke: piece.color === 'w' ? '0.5px #555' : '0.5px #888',
                }}>
                  {PIECES[pieceKey] || '?'}
                </span>
              </div>
            )}
          </div>
        )
      })
    })
    return squares
  }

  // SVG arrow overlay
  const renderArrow = (fromAlg, toAlg, color = 'rgba(0,150,255,0.75)') => {
    const boardEl = boardRef.current
    if (!boardEl) return null
    const sqSz = boardEl.offsetWidth / 8

    const toCoord = (alg) => {
      let f = FILES.indexOf(alg[0])
      let r = parseInt(alg[1]) - 1
      if (flipped) { f = 7 - f; r = 7 - r }
      else r = 7 - r
      return { x: f * sqSz + sqSz / 2, y: r * sqSz + sqSz / 2 }
    }

    const from = toCoord(fromAlg)
    const to = toCoord(toAlg)
    const dx = to.x - from.x, dy = to.y - from.y
    const len = Math.sqrt(dx * dx + dy * dy)
    if (len < 1) return null
    const nx = dx / len, ny = dy / len
    const headLen = sqSz * 0.35
    const shaftEnd = { x: to.x - nx * headLen, y: to.y - ny * headLen }
    const perp = sqSz * 0.13
    const arrowHead = [
      `${to.x},${to.y}`,
      `${shaftEnd.x + (-ny) * perp},${shaftEnd.y + nx * perp}`,
      `${shaftEnd.x - (-ny) * perp},${shaftEnd.y - nx * perp}`,
    ].join(' ')

    return (
      <g key={`${fromAlg}${toAlg}`}>
        <line
          x1={from.x + nx * sqSz * 0.2} y1={from.y + ny * sqSz * 0.2}
          x2={shaftEnd.x} y2={shaftEnd.y}
          stroke={color} strokeWidth={sqSz * 0.12} strokeLinecap="round"
          opacity={0.85}
        />
        <polygon points={arrowHead} fill={color} opacity={0.85} />
      </g>
    )
  }

  const boardSize = boardRef.current?.offsetWidth || 480

  return (
    <div className="relative w-full max-w-[min(80vh,600px)] mx-auto select-none">
      {/* Board grid */}
      <div
        ref={boardRef}
        className="grid grid-cols-8 w-full border border-surface-4 rounded overflow-hidden"
      >
        {renderSquares()}
      </div>

      {/* SVG overlay for arrows */}
      <svg
        className="absolute inset-0 w-full h-full pointer-events-none"
        viewBox={`0 0 ${boardSize} ${boardSize}`}
        style={{ zIndex: 30 }}
      >
        {lastMove && renderArrow(lastMove.from, lastMove.to, 'rgba(200,200,0,0.35)')}
        {engineArrow && renderArrow(engineArrow.from, engineArrow.to, 'rgba(0,150,255,0.7)')}
      </svg>

      {/* Dragged piece */}
      {dragging && (
        <div
          className="fixed pointer-events-none z-50 flex items-center justify-center"
          style={{
            left: dragPos.x - 30,
            top:  dragPos.y - 30,
            width: 60, height: 60,
            fontSize: 52,
            filter: 'drop-shadow(0 2px 6px rgba(0,0,0,0.7))',
          }}
        >
          <span style={{
            color: dragging.piece[0] === 'w' ? '#fff' : '#1a1a1a',
            WebkitTextStroke: dragging.piece[0] === 'w' ? '0.5px #555' : '0.5px #888',
          }}>
            {PIECES[dragging.piece] || '?'}
          </span>
        </div>
      )}

      {/* Promotion picker */}
      {promotion && (
        <div className="absolute inset-0 bg-black/70 flex items-center justify-center z-50 rounded">
          <div className="bg-surface-2 rounded-lg p-4 shadow-2xl">
            <p className="text-center text-sm mb-3 text-gray-400">Choose promotion piece</p>
            <div className="flex gap-3">
              {['Q','R','B','N'].map(p => {
                const color = chess.turn()
                const key = color + p
                return (
                  <button
                    key={p}
                    className="w-14 h-14 text-4xl bg-surface-3 hover:bg-accent rounded-lg flex items-center justify-center transition-colors"
                    style={{ color: color === 'w' ? '#fff' : '#1a1a1a', WebkitTextStroke: color === 'w' ? '0.5px #555' : '0.5px #888' }}
                    onClick={() => {
                      onMove(promotion.from, promotion.to, p.toLowerCase())
                      setPromotion(null)
                    }}
                  >
                    {PIECES[key]}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
