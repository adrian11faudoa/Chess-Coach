"""
Game Session for ChessCoach Web.
Stateless session object that coordinates engine, coach, and opening logic.
Designed for use inside FastAPI WebSocket handlers — no Qt dependencies.
"""

import asyncio
import chess
import time
from typing import Optional, Callable, Awaitable, Dict, Any, List

from chesslogic.core.game_manager import GameManager, GameMode, GameResult, MoveRecord
from chesslogic.engine.engine_manager import EngineManager, EngineConfig, PositionAnalysis
from chesslogic.coach.chess_coach_engine import ChessCoach
from chesslogic.openings.opening_recognizer import OpeningRecognizer, OpeningInfo
from chesslogic.database.db_manager import DatabaseManager
from chesslogic.utils.logger import get_logger

logger = get_logger("game_session")

# Callback type: async fn that receives event_name + data dict
EventCallback = Callable[[str, Dict[str, Any]], Awaitable[None]]


class GameSession:
    """
    One player's game session.
    Holds all state for a single game and exposes async methods
    that the WebSocket handler calls directly.
    """

    def __init__(self, session_id: str, engine: EngineManager,
                 db: DatabaseManager):
        self.session_id = session_id
        self._engine = engine
        self._db = db
        self._game = GameManager()
        self._coach = ChessCoach(verbosity="normal")
        self._opening_recognizer = OpeningRecognizer(db)
        self._current_opening: Optional[OpeningInfo] = None
        self._current_analysis: Optional[PositionAnalysis] = None
        self._player_color: chess.Color = chess.WHITE
        self._engine_elo: int = 1500
        self._mode: GameMode = GameMode.VS_ENGINE
        self._emit: Optional[EventCallback] = None   # Set by WebSocket handler

    def set_event_callback(self, callback: EventCallback):
        """Register the async callback for outbound WebSocket events."""
        self._emit = callback

    async def _send(self, event: str, data: Dict[str, Any]):
        if self._emit:
            await self._emit(event, data)

    # ─── Game Setup ───────────────────────────────────────────────────────────

    async def new_game(self, player_color: int = chess.WHITE,
                       engine_elo: int = 1500,
                       time_control: Optional[str] = None,
                       mode: str = "vs_engine"):
        self._player_color = chess.Color(player_color)
        self._engine_elo = engine_elo
        self._mode = GameMode(mode)
        self._current_opening = None

        # Update engine strength
        if self._engine.is_ready:
            self._engine.update_config(EngineConfig(elo=engine_elo))

        self._game.new_game(
            mode=self._mode,
            player_color=self._player_color,
            time_control=time_control,
        )

        await self._send("game_started", {
            "fen": self._game.fen,
            "player_color": player_color,
            "engine_elo": engine_elo,
            "mode": mode,
        })
        await self._send("coach_comment", {
            "text": "New game started! Good luck.",
            "category": "evaluation"
        })

        # Engine plays first if player is Black
        if self._mode == GameMode.VS_ENGINE and self._player_color == chess.BLACK:
            await asyncio.sleep(0.3)
            await self._engine_move()

    async def handle_move(self, from_sq: int, to_sq: int,
                          promotion: Optional[str] = None) -> bool:
        """Handle an incoming move from the browser."""
        if self._game.is_over:
            return False

        if self._mode == GameMode.VS_ENGINE and not self._game.is_player_turn:
            return False

        # Build move
        promo_map = {"q": chess.QUEEN, "r": chess.ROOK,
                     "b": chess.BISHOP, "n": chess.KNIGHT}
        promo_piece = promo_map.get(promotion, chess.QUEEN) if promotion else None

        move = chess.Move(chess.Square(from_sq), chess.Square(to_sq),
                          promotion=promo_piece)

        # Auto-detect promotion if not specified
        if not self._game.is_legal(move):
            piece = self._game.board.piece_at(chess.Square(from_sq))
            if piece and piece.piece_type == chess.PAWN:
                rank = chess.square_rank(chess.Square(to_sq))
                if (piece.color == chess.WHITE and rank == 7) or \
                   (piece.color == chess.BLACK and rank == 0):
                    move = chess.Move(
                        chess.Square(from_sq), chess.Square(to_sq),
                        promotion=chess.QUEEN
                    )
        if not self._game.is_legal(move):
            await self._send("illegal_move", {"from": from_sq, "to": to_sq})
            return False

        record = self._game.make_move(move)
        if not record:
            return False

        await self._after_move(record, is_engine=False)
        return True

    async def handle_move_uci(self, uci: str) -> bool:
        """Handle a move given as UCI string."""
        try:
            move = chess.Move.from_uci(uci)
            return await self.handle_move(move.from_square, move.to_square,
                                          uci[4] if len(uci) == 5 else None)
        except ValueError:
            return False

    async def _after_move(self, record: MoveRecord, is_engine: bool):
        """Common post-move processing for both player and engine moves."""
        board = self._game.board
        history = self._game.move_history

        # Build move payload
        move_data = {
            "san": record.san,
            "uci": record.move.uci(),
            "from_sq": record.move.from_square,
            "to_sq": record.move.to_square,
            "promotion": chess.piece_symbol(record.move.promotion)
                         if record.move.promotion else None,
            "fen": self._game.fen,
            "move_number": board.fullmove_number,
            "turn": int(board.turn),
            "is_check": board.is_check(),
            "is_engine": is_engine,
            "move_index": len(history) - 1,
        }
        await self._send("move_played", move_data)

        # Check game over
        if self._game.is_over:
            await self._send("game_over", {
                "result": self._game.result.value,
                "reason": self._get_end_reason(),
            })
            asyncio.create_task(self._save_game())
            return

        # Opening detection (async, non-blocking)
        asyncio.create_task(self._check_opening(history))

        # Background analysis
        asyncio.create_task(self._analyze_position(record, is_engine))

        # Engine response
        if (self._mode == GameMode.VS_ENGINE and
                not self._game.is_player_turn and not self._game.is_over):
            await asyncio.sleep(0.15)   # Small delay feels more natural
            await self._engine_move()

    async def _engine_move(self):
        """Get engine's move and play it."""
        if not self._engine.is_ready or self._game.is_over:
            return

        await self._send("engine_thinking", {"thinking": True})

        fen = self._game.fen
        time_limit = self._calc_engine_time()

        # Run in executor so we don't block the event loop
        loop = asyncio.get_event_loop()
        uci = await loop.run_in_executor(
            None,
            lambda: self._engine._get_best_move_sync(fen, time_limit)
        )

        await self._send("engine_thinking", {"thinking": False})

        if uci and not self._game.is_over:
            move = chess.Move.from_uci(uci)
            record = self._game.make_move(move)
            if record:
                await self._after_move(record, is_engine=True)

    def _calc_engine_time(self) -> float:
        clock = self._game.clock
        if not clock:
            return 1.2
        remaining = clock.current_time(self._game.turn)
        return max(0.5, min(4.0, remaining * 0.05))

    async def _check_opening(self, history: List[MoveRecord]):
        """Identify the current opening and emit if changed."""
        moves_uci = [r.move.uci() for r in history]
        opening = self._opening_recognizer.identify_from_moves(moves_uci)
        if opening and opening != self._current_opening:
            self._current_opening = opening
            comment = self._opening_recognizer.get_opening_comment(
                opening, len(moves_uci)
            )
            await self._send("opening_detected", {
                "name": opening.full_name,
                "eco": opening.eco,
                "description": opening.description,
                "strategic_ideas": opening.strategic_ideas,
                "typical_plans": opening.typical_plans,
                "comment": comment,
            })
            await self._send("coach_comment", {
                "text": comment,
                "category": "opening"
            })

    async def _analyze_position(self, record: MoveRecord, is_engine: bool):
        """Run background engine analysis and generate coaching commentary."""
        if not self._engine.is_ready:
            return

        fen = self._game.fen
        loop = asyncio.get_event_loop()

        analysis = await loop.run_in_executor(
            None,
            lambda: self._engine._analyze_position_sync(fen, 18, None, 3)
        )

        if not analysis:
            return

        self._current_analysis = analysis

        # Evaluation payload
        perspective = self._player_color
        sign = 1 if perspective == chess.WHITE else -1
        rel_eval = sign * analysis.evaluation
        eval_desc = analysis.get_evaluation_description(perspective)

        lines_data = []
        for line in analysis.lines[:3]:
            lines_data.append({
                "score": line.score_display,
                "moves": line.san_moves[:6],
                "depth": line.depth,
            })

        await self._send("analysis_update", {
            "evaluation": analysis.evaluation,
            "relative_eval": rel_eval,
            "eval_description": eval_desc,
            "best_move": analysis.best_move,
            "best_move_san": analysis.best_move_san,
            "mate_in": analysis.mate_in,
            "depth": analysis.depth,
            "lines": lines_data,
        })

        # Coaching commentary
        board = chess.Board(fen)
        assessment = self._coach.assess_position(board, analysis, perspective)

        # Emit move comment for last played move
        board_before = chess.Board(record.fen_before)
        move_comment = self._coach.comment_on_move(
            board_before, record.move,
            record.classification or "good",
            analysis
        )
        await self._send("coach_comment", {
            "text": move_comment,
            "category": "evaluation",
        })

        # Emit high-priority strategic/tactical warnings
        for comment in assessment.all_comments[:2]:
            if comment.priority >= 7:
                await self._send("coach_comment", {
                    "text": comment.text,
                    "category": comment.category,
                })

    # ─── Navigation ──────────────────────────────────────────────────────────

    async def navigate_to(self, move_index: int):
        self._game.go_to_move(move_index)
        await self._send("position_set", {
            "fen": self._game.fen,
            "move_index": move_index,
        })

    async def undo(self):
        self._game.undo_move()
        if self._mode == GameMode.VS_ENGINE and not self._game.is_player_turn:
            self._game.undo_move()
        await self._send("position_set", {
            "fen": self._game.fen,
            "move_index": len(self._game.move_history) - 1,
        })

    async def get_hint(self):
        if not self._current_analysis:
            await self._send("coach_comment", {
                "text": "Calculating hint...", "category": "plan"
            })
            return

        board = self._game.board
        assessment = self._coach.assess_position(board, self._current_analysis)
        comments = assessment.all_comments

        if comments:
            hint = comments[0].text
        elif self._current_analysis.best_move:
            try:
                from_sq = chess.Move.from_uci(self._current_analysis.best_move).from_square
                piece = board.piece_at(from_sq)
                if piece:
                    hint = f"Consider moving your {chess.piece_name(piece.piece_type)}."
                else:
                    hint = "Look for the most active continuation."
            except Exception:
                hint = "Look for the most active continuation."
        else:
            hint = "Look for the most active continuation."

        await self._send("coach_comment", {"text": f"💡 {hint}", "category": "plan"})

    async def resign(self):
        self._game.resign(self._player_color)
        await self._send("game_over", {
            "result": self._game.result.value,
            "reason": "resignation"
        })

    async def set_fen(self, fen: str) -> bool:
        ok = self._game.set_fen(fen)
        if ok:
            await self._send("position_set", {
                "fen": self._game.fen, "move_index": -1
            })
        return ok

    async def load_pgn(self, pgn_text: str) -> bool:
        ok = self._game.load_pgn(pgn_text)
        if ok:
            history = self._game.move_history
            moves_list = [{"san": r.san, "uci": r.move.uci()} for r in history]
            await self._send("game_loaded", {
                "fen": self._game.fen,
                "moves": moves_list,
                "move_index": len(history) - 1,
            })
        return ok

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _get_end_reason(self) -> str:
        board = self._game.board
        if board.is_checkmate():
            return "checkmate"
        if board.is_stalemate():
            return "stalemate"
        if board.is_insufficient_material():
            return "insufficient_material"
        if board.is_seventyfive_moves():
            return "75_move_rule"
        if board.is_fivefold_repetition():
            return "repetition"
        return "other"

    async def _save_game(self):
        pgn = self._game.to_pgn()
        summary = self._game.get_game_summary()
        opening = self._current_opening
        game_data = {
            "date": time.strftime("%Y-%m-%d"),
            "white_player": "Player" if self._player_color == chess.WHITE else "Engine",
            "black_player": "Engine" if self._player_color == chess.WHITE else "Player",
            "white_elo": None,
            "black_elo": self._engine_elo,
            "result": self._game.result.value,
            "time_control": None,
            "opening_eco": opening.eco if opening else None,
            "opening_name": opening.full_name if opening else None,
            "pgn": pgn,
            "final_fen": self._game.fen,
            "accuracy_white": None,
            "accuracy_black": None,
            "blunders_white": summary.get("blunders_white", 0),
            "blunders_black": summary.get("blunders_black", 0),
            "mistakes_white": summary.get("mistakes_white", 0),
            "mistakes_black": summary.get("mistakes_black", 0),
            "inaccuracies_white": summary.get("inaccuracies_white", 0),
            "inaccuracies_black": summary.get("inaccuracies_black", 0),
            "game_mode": self._mode.value,
            "notes": None,
            "tags": "[]",
        }
        try:
            loop = asyncio.get_event_loop()
            game_id = await loop.run_in_executor(None, lambda: self._db.save_game(game_data))
            await self._send("game_saved", {"game_id": game_id})
        except Exception as e:
            logger.error(f"Save game error: {e}")

    # ─── Properties ──────────────────────────────────────────────────────────

    @property
    def board(self) -> chess.Board:
        return self._game.board

    @property
    def fen(self) -> str:
        return self._game.fen

    @property
    def move_history(self) -> List[Dict]:
        return [{"san": r.san, "uci": r.move.uci(),
                 "classification": r.classification}
                for r in self._game.move_history]

    def get_legal_moves(self, from_sq: Optional[int] = None) -> List[str]:
        moves = self._game.get_legal_moves(
            chess.Square(from_sq) if from_sq is not None else None
        )
        return [m.uci() for m in moves]
