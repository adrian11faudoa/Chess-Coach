"""
Game Manager for ChessCoach.

Central game state controller that coordinates:
- Legal move validation
- Move history tracking
- PGN/FEN import/export
- Clock management
- Game result detection
- Undo/redo functionality
"""

import chess
import chess.pgn
import io
import time
from typing import Optional, List, Tuple, Dict, Callable
from dataclasses import dataclass, field
from enum import Enum

from chesslogic.utils.logger import get_logger

logger = get_logger("game")


class GameMode(Enum):
    VS_ENGINE = "vs_engine"
    ANALYSIS = "analysis"
    PUZZLE = "puzzle"
    OPENING_TRAINER = "opening_trainer"
    TWO_PLAYER = "two_player"


class GameResult(Enum):
    ONGOING = "*"
    WHITE_WINS = "1-0"
    BLACK_WINS = "0-1"
    DRAW = "1/2-1/2"
    UNKNOWN = "?"


@dataclass
class MoveRecord:
    """Complete record of a played move."""
    move: chess.Move
    san: str
    fen_before: str
    fen_after: str
    clock_before: Optional[float] = None    # Seconds remaining
    time_spent: float = 0.0                  # Seconds spent on this move
    evaluation: Optional[float] = None
    classification: Optional[str] = None
    comment: Optional[str] = None
    annotations: List[Dict] = field(default_factory=list)


@dataclass
class ClockState:
    """Tracks time for both players."""
    white_time: float   # Seconds
    black_time: float
    increment: float = 0.0
    running: bool = False
    turn: chess.Color = chess.WHITE
    _last_start: float = 0.0

    def start(self, color: chess.Color):
        self.turn = color
        self.running = True
        self._last_start = time.time()

    def stop(self) -> float:
        """Stop the clock and return time spent."""
        if not self.running:
            return 0.0
        elapsed = time.time() - self._last_start
        self.running = False
        if self.turn == chess.WHITE:
            self.white_time -= elapsed
            self.white_time += self.increment
            self.white_time = max(0, self.white_time)
        else:
            self.black_time -= elapsed
            self.black_time += self.increment
            self.black_time = max(0, self.black_time)
        return elapsed

    def current_time(self, color: chess.Color) -> float:
        """Get current time for a player (accounting for running clock)."""
        base = self.white_time if color == chess.WHITE else self.black_time
        if self.running and self.turn == color:
            elapsed = time.time() - self._last_start
            return max(0, base - elapsed)
        return base

    def is_flagged(self, color: chess.Color) -> bool:
        return self.current_time(color) <= 0


class GameManager:
    """
    Manages a complete chess game lifecycle.
    
    Handles the board state, move history, clock, and game result.
    Provides PGN import/export and FEN support.
    """

    def __init__(self):
        self._board = chess.Board()
        self._move_history: List[MoveRecord] = []
        self._redo_stack: List[MoveRecord] = []
        self._clock: Optional[ClockState] = None
        self._mode: GameMode = GameMode.VS_ENGINE
        self._player_color: chess.Color = chess.WHITE
        self._result: GameResult = GameResult.ONGOING
        self._game_id: Optional[int] = None
        self._starting_fen: str = chess.STARTING_FEN
        self._callbacks: Dict[str, List[Callable]] = {}
        self._headers: Dict[str, str] = {}
        self._move_start_time: float = 0.0

    # ─── Game Setup ───────────────────────────────────────────────────────────

    def new_game(self, mode: GameMode = GameMode.VS_ENGINE,
                 player_color: chess.Color = chess.WHITE,
                 time_control: Optional[str] = None,
                 starting_fen: Optional[str] = None):
        """Start a new game with the given settings."""
        self._board = chess.Board(starting_fen) if starting_fen else chess.Board()
        self._starting_fen = starting_fen or chess.STARTING_FEN
        self._move_history = []
        self._redo_stack = []
        self._mode = mode
        self._player_color = player_color
        self._result = GameResult.ONGOING
        self._game_id = None

        if time_control:
            self._setup_clock(time_control)

        self._move_start_time = time.time()
        self._emit("game_started", self._board)
        logger.info(f"New game started: mode={mode.value}, player={'White' if player_color else 'Black'}")

    def _setup_clock(self, time_control: str):
        """Parse and setup clock from time control string (e.g. '10+0', '3+2')."""
        try:
            parts = time_control.split("+")
            minutes = float(parts[0])
            increment = float(parts[1]) if len(parts) > 1 else 0
            seconds = minutes * 60
            self._clock = ClockState(
                white_time=seconds,
                black_time=seconds,
                increment=increment
            )
        except Exception:
            self._clock = None

    # ─── Move Execution ───────────────────────────────────────────────────────

    def make_move(self, move: chess.Move,
                  comment: Optional[str] = None) -> Optional[MoveRecord]:
        """
        Execute a legal move on the board.
        Returns MoveRecord if successful, None if illegal.
        """
        if not self.is_legal(move):
            logger.warning(f"Illegal move attempted: {move.uci()}")
            return None

        fen_before = self._board.fen()
        san = self._board.san(move)

        # Record time spent
        time_spent = 0.0
        if self._clock and self._clock.running:
            time_spent = self._clock.stop()
        else:
            time_spent = time.time() - self._move_start_time

        self._board.push(move)
        fen_after = self._board.fen()

        record = MoveRecord(
            move=move,
            san=san,
            fen_before=fen_before,
            fen_after=fen_after,
            clock_before=self._clock.current_time(not self._board.turn) if self._clock else None,
            time_spent=time_spent,
            comment=comment
        )

        self._move_history.append(record)
        self._redo_stack.clear()  # Clear redo on new move

        # Start clock for next player
        if self._clock:
            self._clock.start(self._board.turn)
        self._move_start_time = time.time()

        # Check for game end
        self._check_game_over()

        self._emit("move_made", record)
        return record

    def make_move_uci(self, uci: str) -> Optional[MoveRecord]:
        """Make a move from UCI string."""
        try:
            move = chess.Move.from_uci(uci)
            return self.make_move(move)
        except ValueError:
            return None

    def make_move_san(self, san: str) -> Optional[MoveRecord]:
        """Make a move from SAN string."""
        try:
            move = self._board.parse_san(san)
            return self.make_move(move)
        except ValueError:
            return None

    def is_legal(self, move: chess.Move) -> bool:
        """Check if a move is legal in the current position."""
        return move in self._board.legal_moves

    def get_legal_moves(self, from_square: Optional[chess.Square] = None) -> List[chess.Move]:
        """Get all legal moves, optionally filtered by from square."""
        moves = list(self._board.legal_moves)
        if from_square is not None:
            moves = [m for m in moves if m.from_square == from_square]
        return moves

    # ─── Undo / Redo ─────────────────────────────────────────────────────────

    def undo_move(self) -> Optional[MoveRecord]:
        """Undo the last move."""
        if not self._move_history:
            return None

        record = self._move_history.pop()
        self._redo_stack.append(record)
        self._board.pop()

        self._emit("move_undone", record)
        return record

    def redo_move(self) -> Optional[MoveRecord]:
        """Redo a previously undone move."""
        if not self._redo_stack:
            return None

        record = self._redo_stack.pop()
        self._board.push(record.move)
        self._move_history.append(record)

        self._emit("move_redone", record)
        return record

    def can_undo(self) -> bool:
        return len(self._move_history) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    # ─── Game Navigation ─────────────────────────────────────────────────────

    def go_to_start(self):
        """Navigate to the starting position."""
        while self._move_history:
            self.undo_move()

    def go_to_end(self):
        """Navigate to the latest position."""
        while self._redo_stack:
            self.redo_move()

    def go_to_move(self, move_index: int):
        """Navigate to a specific move index in the game."""
        current = len(self._move_history)
        if move_index < current:
            while len(self._move_history) > move_index:
                self.undo_move()
        elif move_index > current:
            while len(self._move_history) < move_index and self._redo_stack:
                self.redo_move()

    # ─── Game Over Detection ─────────────────────────────────────────────────

    def _check_game_over(self):
        """Check if the game has ended."""
        board = self._board
        result = None

        if board.is_checkmate():
            # The side that just moved wins
            result = GameResult.WHITE_WINS if board.turn == chess.BLACK else GameResult.BLACK_WINS
        elif board.is_stalemate():
            result = GameResult.DRAW
        elif board.is_insufficient_material():
            result = GameResult.DRAW
        elif board.is_seventyfive_moves():
            result = GameResult.DRAW
        elif board.is_fivefold_repetition():
            result = GameResult.DRAW
        elif self._clock:
            if self._clock.is_flagged(chess.WHITE):
                result = GameResult.BLACK_WINS
            elif self._clock.is_flagged(chess.BLACK):
                result = GameResult.WHITE_WINS

        if result:
            self._result = result
            if self._clock:
                self._clock.running = False
            self._emit("game_over", result)

    def resign(self, color: chess.Color):
        """A player resigns."""
        self._result = GameResult.BLACK_WINS if color == chess.WHITE else GameResult.WHITE_WINS
        if self._clock:
            self._clock.running = False
        self._emit("game_over", self._result)

    def offer_draw(self):
        """Offer or accept a draw."""
        self._result = GameResult.DRAW
        if self._clock:
            self._clock.running = False
        self._emit("game_over", self._result)

    # ─── PGN Support ─────────────────────────────────────────────────────────

    def to_pgn(self, extra_headers: Optional[Dict] = None) -> str:
        """Export the current game to PGN format."""
        game = chess.pgn.Game()
        game.headers["Event"] = "ChessCoach Game"
        game.headers["Site"] = "ChessCoach"
        game.headers["Date"] = time.strftime("%Y.%m.%d")
        game.headers["White"] = "Player" if self._player_color == chess.WHITE else "ChessCoach Engine"
        game.headers["Black"] = "ChessCoach Engine" if self._player_color == chess.WHITE else "Player"
        game.headers["Result"] = self._result.value

        if extra_headers:
            for key, value in extra_headers.items():
                game.headers[key] = value

        # Rebuild game from move history
        node = game
        board = chess.Board(self._starting_fen)
        for record in self._move_history:
            node = node.add_variation(record.move)
            if record.comment:
                node.comment = record.comment
            board.push(record.move)

        return str(game)

    def load_pgn(self, pgn_text: str) -> bool:
        """Load a game from PGN text."""
        try:
            game = chess.pgn.read_game(io.StringIO(pgn_text))
            if not game:
                return False

            self._board = chess.Board()
            self._move_history = []
            self._redo_stack = []
            self._result = GameResult.ONGOING

            # Load headers
            self._headers = dict(game.headers)

            # Replay moves
            board = game.board()
            for node in game.mainline():
                move = node.move
                fen_before = board.fen()
                san = board.san(move)
                board.push(move)
                record = MoveRecord(
                    move=move,
                    san=san,
                    fen_before=fen_before,
                    fen_after=board.fen(),
                    comment=node.comment or None
                )
                self._move_history.append(record)

            # Set board to final position
            self._board = board

            # Set result
            result_str = game.headers.get("Result", "*")
            for r in GameResult:
                if r.value == result_str:
                    self._result = r
                    break

            self._emit("game_loaded", self._board)
            return True
        except Exception as e:
            logger.error(f"PGN load error: {e}")
            return False

    def set_fen(self, fen: str) -> bool:
        """Set the board to a specific FEN position."""
        try:
            board = chess.Board(fen)
            self._board = board
            self._move_history = []
            self._redo_stack = []
            self._starting_fen = fen
            self._result = GameResult.ONGOING
            self._emit("position_set", self._board)
            return True
        except ValueError:
            return False

    # ─── Accessors ────────────────────────────────────────────────────────────

    @property
    def board(self) -> chess.Board:
        return self._board

    @property
    def turn(self) -> chess.Color:
        return self._board.turn

    @property
    def is_player_turn(self) -> bool:
        return self._board.turn == self._player_color

    @property
    def move_history(self) -> List[MoveRecord]:
        return list(self._move_history)

    @property
    def mode(self) -> GameMode:
        return self._mode

    @property
    def player_color(self) -> chess.Color:
        return self._player_color

    @property
    def result(self) -> GameResult:
        return self._result

    @property
    def is_over(self) -> bool:
        return self._result != GameResult.ONGOING

    @property
    def clock(self) -> Optional[ClockState]:
        return self._clock

    @property
    def fullmove_number(self) -> int:
        return self._board.fullmove_number

    @property
    def fen(self) -> str:
        return self._board.fen()

    def get_move_san_list(self) -> List[str]:
        """Get list of SAN moves for display."""
        return [r.san for r in self._move_history]

    def get_current_move_record(self) -> Optional[MoveRecord]:
        """Get the most recent move record."""
        return self._move_history[-1] if self._move_history else None

    def update_move_record(self, index: int, **kwargs):
        """Update fields of a move record (for post-analysis)."""
        if 0 <= index < len(self._move_history):
            record = self._move_history[index]
            for key, value in kwargs.items():
                if hasattr(record, key):
                    setattr(record, key, value)

    # ─── Event System ─────────────────────────────────────────────────────────

    def on(self, event: str, callback: Callable):
        """Register an event callback."""
        if event not in self._callbacks:
            self._callbacks[event] = []
        self._callbacks[event].append(callback)

    def _emit(self, event: str, *args):
        """Fire all callbacks for an event."""
        for cb in self._callbacks.get(event, []):
            try:
                cb(*args)
            except Exception as e:
                logger.error(f"Callback error for {event}: {e}")

    # ─── Game Summary ─────────────────────────────────────────────────────────

    def get_game_summary(self) -> Dict:
        """Generate a summary of the completed game."""
        if not self._move_history:
            return {}

        total_moves = len(self._move_history)
        white_moves = [r for i, r in enumerate(self._move_history) if i % 2 == 0]
        black_moves = [r for i, r in enumerate(self._move_history) if i % 2 == 1]

        blunders_w = sum(1 for r in white_moves if r.classification == "blunder")
        mistakes_w = sum(1 for r in white_moves if r.classification == "mistake")
        inaccuracies_w = sum(1 for r in white_moves if r.classification == "inaccuracy")

        blunders_b = sum(1 for r in black_moves if r.classification == "blunder")
        mistakes_b = sum(1 for r in black_moves if r.classification == "mistake")
        inaccuracies_b = sum(1 for r in black_moves if r.classification == "inaccuracy")

        return {
            "total_moves": total_moves,
            "result": self._result.value,
            "player_color": "White" if self._player_color == chess.WHITE else "Black",
            "blunders_white": blunders_w,
            "mistakes_white": mistakes_w,
            "inaccuracies_white": inaccuracies_w,
            "blunders_black": blunders_b,
            "mistakes_black": mistakes_b,
            "inaccuracies_black": inaccuracies_b,
        }
