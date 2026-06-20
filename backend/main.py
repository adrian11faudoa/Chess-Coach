"""
ChessCoach Web — FastAPI Backend
Serves WebSocket game sessions and REST API endpoints.
"""

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Add chess logic to path
import sys
sys.path.insert(0, os.path.dirname(__file__))

from chesslogic.engine.engine_manager import EngineManager, EngineConfig
from chesslogic.database.db_manager import DatabaseManager
from chesslogic.core.game_session import GameSession
from chesslogic.core.game_analyzer_async import analyze_game_pgn
from chesslogic.utils.config import Config
from chesslogic.utils.logger import get_logger, setup_logger

logger = get_logger("app")

# ─── App-level singletons ────────────────────────────────────────────────────

config = Config()
db = DatabaseManager(config.db_path)
engine = EngineManager()

# Active WebSocket sessions: session_id → GameSession
sessions: Dict[str, GameSession] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    setup_logger()
    db.initialize()
    logger.info("Database initialized")

    # Start Stockfish
    path = config.stockfish_path or EngineManager.find_stockfish()
    if path:
        ok = engine.start(path, EngineConfig(
            elo=1500, depth=20, threads=2, hash_mb=256
        ))
        if ok:
            logger.info(f"Stockfish started: {path}")
        else:
            logger.warning("Stockfish found but failed to start")
    else:
        logger.warning(
            "Stockfish not found. Set STOCKFISH_PATH env var or install stockfish."
        )

    yield   # App runs here

    engine.stop()
    logger.info("Engine stopped, shutting down")


app = FastAPI(
    title="ChessCoach API",
    description="Educational Chess Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Tighten to your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── WebSocket Game Handler ───────────────────────────────────────────────────

@app.websocket("/ws/game/{session_id}")
async def game_websocket(ws: WebSocket, session_id: str):
    """
    Main game WebSocket.

    Client → Server messages (JSON):
      { "type": "new_game",   "player_color": 1, "engine_elo": 1500,
                              "time_control": "10+0", "mode": "vs_engine" }
      { "type": "move",       "from": 52, "to": 36, "promotion": null }
      { "type": "move_uci",   "uci": "e2e4" }
      { "type": "undo" }
      { "type": "navigate",   "move_index": 5 }
      { "type": "hint" }
      { "type": "resign" }
      { "type": "load_pgn",   "pgn": "..." }
      { "type": "set_fen",    "fen": "..." }
      { "type": "legal_moves","from_sq": 12 }
      { "type": "ping" }

    Server → Client messages (JSON):
      { "type": "game_started",    ... }
      { "type": "move_played",     ... }
      { "type": "engine_thinking", "thinking": bool }
      { "type": "analysis_update", ... }
      { "type": "coach_comment",   "text": "...", "category": "..." }
      { "type": "opening_detected",... }
      { "type": "game_over",       "result": "1-0", "reason": "checkmate" }
      { "type": "game_saved",      "game_id": 42 }
      { "type": "legal_moves",     "moves": ["e2e4", ...] }
      { "type": "position_set",    "fen": "...", "move_index": N }
      { "type": "error",           "message": "..." }
      { "type": "pong" }
    """
    await ws.accept()
    logger.info(f"WebSocket connected: {session_id}")

    # Create or retrieve session
    if session_id not in sessions:
        sessions[session_id] = GameSession(session_id, engine, db)

    session = sessions[session_id]

    async def emit(event: str, data: dict):
        """Send a typed event to the client."""
        try:
            await ws.send_json({"type": event, **data})
        except Exception:
            pass

    session.set_event_callback(emit)

    # Send welcome / current state
    await emit("connected", {
        "session_id": session_id,
        "engine_ready": engine.is_ready,
        "fen": session.fen,
    })

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await emit("error", {"message": "Invalid JSON"})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "new_game":
                await session.new_game(
                    player_color=msg.get("player_color", 1),
                    engine_elo=msg.get("engine_elo", 1500),
                    time_control=msg.get("time_control"),
                    mode=msg.get("mode", "vs_engine"),
                )

            elif msg_type == "move":
                ok = await session.handle_move(
                    msg["from"], msg["to"], msg.get("promotion")
                )
                if not ok:
                    await emit("illegal_move", {"from": msg["from"], "to": msg["to"]})

            elif msg_type == "move_uci":
                ok = await session.handle_move_uci(msg["uci"])
                if not ok:
                    await emit("illegal_move", {"uci": msg.get("uci")})

            elif msg_type == "undo":
                await session.undo()

            elif msg_type == "navigate":
                await session.navigate_to(msg.get("move_index", 0))

            elif msg_type == "hint":
                await session.get_hint()

            elif msg_type == "resign":
                await session.resign()

            elif msg_type == "load_pgn":
                ok = await session.load_pgn(msg.get("pgn", ""))
                if not ok:
                    await emit("error", {"message": "Invalid PGN"})

            elif msg_type == "set_fen":
                ok = await session.set_fen(msg.get("fen", ""))
                if not ok:
                    await emit("error", {"message": "Invalid FEN"})

            elif msg_type == "legal_moves":
                moves = session.get_legal_moves(msg.get("from_sq"))
                await emit("legal_moves", {"moves": moves,
                                           "from_sq": msg.get("from_sq")})

            elif msg_type == "ping":
                await emit("pong", {})

            else:
                await emit("error", {"message": f"Unknown message type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error [{session_id}]: {e}")
    finally:
        # Keep session alive for reconnects; clean up after timeout in production
        session.set_event_callback(None)


# ─── Analysis WebSocket ────────────────────────────────────────────────────────

@app.websocket("/ws/analyze/{session_id}")
async def analysis_websocket(ws: WebSocket, session_id: str):
    """
    Streams post-game analysis results move by move.

    Client sends: { "type": "analyze", "pgn": "...", "depth": 18 }
    Server streams:
      { "type": "analysis_progress", "current": N, "total": M }
      { "type": "move_analyzed",     ...MoveAnalysisResult fields... }
      { "type": "analysis_complete", ...GameReport... }
    """
    await ws.accept()
    try:
        raw = await ws.receive_text()
        msg = json.loads(raw)
        if msg.get("type") != "analyze":
            await ws.send_json({"type": "error", "message": "Expected analyze message"})
            return

        pgn = msg.get("pgn", "")
        depth = min(int(msg.get("depth", 18)), 25)

        if not engine.is_ready:
            await ws.send_json({"type": "error",
                                "message": "Engine not available"})
            return

        async def on_progress(current: int, total: int):
            await ws.send_json({
                "type": "analysis_progress",
                "current": current,
                "total": total,
            })

        report = await analyze_game_pgn(pgn, engine, depth, on_progress)

        await ws.send_json({
            "type": "analysis_complete",
            **report.to_dict(),
        })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Analysis WS error: {e}")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


# ─── REST API Routes ──────────────────────────────────────────────────────────

class NewSessionResponse(BaseModel):
    session_id: str


@app.post("/api/sessions", response_model=NewSessionResponse)
async def create_session():
    """Create a new game session and return its ID."""
    session_id = str(uuid.uuid4())
    sessions[session_id] = GameSession(session_id, engine, db)
    return {"session_id": session_id}


@app.get("/api/sessions/{session_id}/fen")
async def get_fen(session_id: str):
    session = _get_session(session_id)
    return {"fen": session.fen}


@app.get("/api/sessions/{session_id}/moves")
async def get_moves(session_id: str):
    session = _get_session(session_id)
    return {"moves": session.move_history}


@app.get("/api/sessions/{session_id}/legal_moves")
async def get_legal_moves(session_id: str, from_sq: Optional[int] = Query(None)):
    session = _get_session(session_id)
    return {"moves": session.get_legal_moves(from_sq)}


@app.get("/api/engine/status")
async def engine_status():
    return {
        "ready": engine.is_ready,
        "info": engine.get_engine_info(),
    }


# ─── Game History ─────────────────────────────────────────────────────────────

@app.get("/api/games")
async def list_games(limit: int = 20, offset: int = 0):
    games = db.get_games(limit=limit, offset=offset)
    return {"games": games}


@app.get("/api/games/{game_id}")
async def get_game(game_id: int):
    game = db.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    moves = db.get_game_moves(game_id)
    return {"game": game, "moves": moves}


@app.get("/api/stats")
async def get_stats():
    return db.get_player_stats()


@app.get("/api/stats/openings")
async def get_opening_stats():
    return {"openings": db.get_opening_stats()}


# ─── Puzzle API ───────────────────────────────────────────────────────────────

@app.get("/api/puzzles/next")
async def next_puzzle(rating: int = 1200):
    puzzle = db.get_puzzle(rating_target=rating)
    if not puzzle:
        raise HTTPException(status_code=404, detail="No puzzles available")
    return puzzle


class PuzzleAttemptRequest(BaseModel):
    puzzle_id: int
    solved: bool
    time_seconds: int
    rating_before: int
    rating_after: int


@app.post("/api/puzzles/attempt")
async def record_puzzle_attempt(req: PuzzleAttemptRequest):
    db.record_puzzle_attempt(
        req.puzzle_id, req.solved, req.time_seconds,
        req.rating_before, req.rating_after
    )
    return {"ok": True}


# ─── Health & Static ──────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "engine": engine.is_ready}


# Serve React frontend (built files) — mount last so API routes take priority
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_session(session_id: str) -> GameSession:
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
