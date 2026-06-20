"""
Engine Manager for ChessCoach.
Handles all communication with the Stockfish chess engine.
Provides async analysis, evaluation, and move generation.
"""

import asyncio
import threading
import queue
import subprocess
import os
import sys
import time
from typing import Optional, List, Dict, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum

import chess
import chess.engine

from chesslogic.utils.logger import get_logger

logger = get_logger("engine")


class EnginePersonality(Enum):
    """AI personality profiles that affect playing style."""
    AGGRESSIVE = "aggressive"    # Prefers attacking moves
    POSITIONAL = "positional"   # Favors quiet positional play
    TACTICAL = "tactical"       # Goes for complications
    SOLID = "solid"             # Conservative, avoids risk
    BALANCED = "balanced"       # Default engine behavior
    BEGINNER = "beginner"       # Makes human-like mistakes


@dataclass
class EngineConfig:
    """Configuration for the chess engine."""
    elo: int = 1500
    depth: int = 20
    threads: int = 2
    hash_mb: int = 256
    personality: EnginePersonality = EnginePersonality.BALANCED
    use_opening_book: bool = True
    contempt: int = 0           # Contempt for draws
    skill_level: int = 20       # 0-20, Stockfish skill


@dataclass
class AnalysisLine:
    """A single engine analysis variation."""
    moves: List[str]            # UCI moves
    san_moves: List[str]        # SAN notation
    score: float                # Centipawn evaluation
    mate_in: Optional[int]      # Mate in N moves, if applicable
    depth: int

    @property
    def score_display(self) -> str:
        if self.mate_in is not None:
            return f"M{self.mate_in}" if self.mate_in > 0 else f"-M{abs(self.mate_in)}"
        return f"{self.score/100:+.2f}"


@dataclass
class PositionAnalysis:
    """Complete analysis result for a position."""
    fen: str
    best_move: Optional[str]    # UCI notation
    best_move_san: Optional[str]
    evaluation: float           # Centipawn score from White's perspective
    mate_in: Optional[int]
    depth: int
    lines: List[AnalysisLine] = field(default_factory=list)
    thinking_time: float = 0.0

    @property
    def is_equal(self) -> bool:
        return abs(self.evaluation) < 30

    @property
    def is_advantage(self) -> bool:
        return 30 <= abs(self.evaluation) < 150

    @property
    def is_winning(self) -> bool:
        return 150 <= abs(self.evaluation) < 500

    @property
    def is_decisive(self) -> bool:
        return abs(self.evaluation) >= 500 or self.mate_in is not None

    def get_evaluation_description(self, side_to_move: chess.Color) -> str:
        """Human-readable evaluation description."""
        if self.mate_in is not None:
            if (self.mate_in > 0) == (side_to_move == chess.WHITE):
                return f"Forced checkmate in {abs(self.mate_in)}"
            else:
                return f"Facing checkmate in {abs(self.mate_in)}"

        adv_side = chess.WHITE if self.evaluation > 0 else chess.BLACK
        adv_name = "White" if adv_side == chess.WHITE else "Black"

        if abs(self.evaluation) < 20:
            return "Position is equal"
        elif abs(self.evaluation) < 50:
            return f"Slight advantage for {adv_name}"
        elif abs(self.evaluation) < 150:
            return f"Clear advantage for {adv_name}"
        elif abs(self.evaluation) < 300:
            return f"Strong advantage for {adv_name}"
        elif abs(self.evaluation) < 600:
            return f"Winning position for {adv_name}"
        else:
            return f"Technically winning for {adv_name}"


class EngineManager:
    """
    Manages Stockfish engine lifecycle and analysis.
    
    Uses a dedicated thread for engine communication to avoid
    blocking the UI. Analysis requests are queued and processed
    in order, with cancellation support.
    """

    # ELO to Stockfish skill level mapping
    ELO_TO_SKILL = {
        800: 1,   1000: 3,  1200: 5,  1400: 8,
        1500: 10, 1600: 12, 1800: 15, 2000: 17,
        2200: 19, 2400: 20, 2600: 20, 2800: 20,
    }

    def __init__(self):
        self._engine: Optional[chess.engine.SimpleEngine] = None
        self._engine_path: Optional[str] = None
        self._config = EngineConfig()
        self._analysis_thread: Optional[threading.Thread] = None
        self._analysis_queue: queue.Queue = queue.Queue()
        self._running = False
        self._current_task_id: int = 0
        self._lock = threading.Lock()

    # ─── Engine Lifecycle ─────────────────────────────────────────────────────

    def start(self, engine_path: str, config: Optional[EngineConfig] = None) -> bool:
        """
        Start the engine process.
        Returns True on success, False on failure.
        """
        if config:
            self._config = config

        self._engine_path = engine_path

        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(engine_path)
            self._configure_engine()
            self._running = True
            self._start_analysis_thread()
            logger.info(f"Engine started: {engine_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to start engine: {e}")
            self._engine = None
            return False

    def stop(self):
        """Cleanly shut down the engine."""
        self._running = False
        if self._analysis_queue:
            self._analysis_queue.put(None)  # Sentinel to stop thread
        if self._engine:
            try:
                self._engine.quit()
            except Exception:
                pass
            self._engine = None
        logger.info("Engine stopped")

    def _configure_engine(self):
        """Apply current configuration to the engine."""
        if not self._engine:
            return

        options = {
            "Threads": self._config.threads,
            "Hash": self._config.hash_mb,
        }

        # Set ELO-based skill level
        skill = self._elo_to_skill(self._config.elo)
        if skill < 20:
            options["Skill Level"] = skill
            # Add error margin for lower levels to simulate human mistakes
            error = max(0, (20 - skill) * 20)
            options["UCI_LimitStrength"] = True
            options["UCI_Elo"] = max(1320, self._config.elo)
        else:
            options["UCI_LimitStrength"] = False

        for name, value in options.items():
            try:
                self._engine.configure({name: value})
            except Exception as e:
                logger.debug(f"Could not set option {name}: {e}")

    def _elo_to_skill(self, elo: int) -> int:
        """Convert ELO rating to Stockfish skill level."""
        levels = sorted(self.ELO_TO_SKILL.keys())
        for level in levels:
            if elo <= level:
                return self.ELO_TO_SKILL[level]
        return 20

    def update_config(self, config: EngineConfig):
        """Update engine configuration at runtime."""
        self._config = config
        if self._engine:
            self._configure_engine()

    @property
    def is_ready(self) -> bool:
        return self._engine is not None and self._running

    # ─── Analysis Thread ──────────────────────────────────────────────────────

    def _start_analysis_thread(self):
        """Start the background analysis thread."""
        self._analysis_thread = threading.Thread(
            target=self._analysis_worker,
            daemon=True,
            name="EngineAnalysis"
        )
        self._analysis_thread.start()

    def _analysis_worker(self):
        """Worker thread that processes analysis requests."""
        while self._running:
            try:
                task = self._analysis_queue.get(timeout=0.1)
                if task is None:
                    break
                task_id, func, args, kwargs, callback = task
                try:
                    result = func(*args, **kwargs)
                    if callback and task_id == self._current_task_id:
                        callback(result)
                except Exception as e:
                    logger.error(f"Analysis error: {e}")
            except queue.Empty:
                continue

    def _submit_task(self, func, args, kwargs, callback) -> int:
        """Submit an analysis task, cancelling any pending tasks."""
        with self._lock:
            self._current_task_id += 1
            task_id = self._current_task_id

        # Clear pending tasks (keep only latest)
        while not self._analysis_queue.empty():
            try:
                self._analysis_queue.get_nowait()
            except queue.Empty:
                break

        self._analysis_queue.put((task_id, func, args, kwargs, callback))
        return task_id

    # ─── Move Generation ──────────────────────────────────────────────────────

    def get_best_move(self, board: chess.Board,
                      time_limit: float = 1.0,
                      callback: Optional[Callable] = None) -> Optional[str]:
        """
        Get the engine's best move for the current position.
        If callback provided, runs asynchronously.
        """
        if not self.is_ready:
            return None

        if callback:
            self._submit_task(
                self._get_best_move_sync,
                (board.fen(), time_limit),
                {},
                callback
            )
            return None
        else:
            return self._get_best_move_sync(board.fen(), time_limit)

    def _get_best_move_sync(self, fen: str, time_limit: float) -> Optional[str]:
        """Synchronous move generation."""
        if not self._engine:
            return None
        try:
            board = chess.Board(fen)
            result = self._engine.play(
                board,
                chess.engine.Limit(time=time_limit),
                info=chess.engine.INFO_ALL
            )
            if result.move:
                return result.move.uci()
        except Exception as e:
            logger.error(f"Move generation error: {e}")
        return None

    # ─── Position Analysis ────────────────────────────────────────────────────

    def analyze_position(self, board: chess.Board,
                         depth: Optional[int] = None,
                         time_limit: Optional[float] = None,
                         multipv: int = 3,
                         callback: Optional[Callable] = None) -> Optional[PositionAnalysis]:
        """
        Analyze a chess position with the engine.
        Returns PositionAnalysis or calls callback asynchronously.
        """
        if not self.is_ready:
            return None

        depth = depth or self._config.depth
        fen = board.fen()

        if callback:
            self._submit_task(
                self._analyze_position_sync,
                (fen, depth, time_limit, multipv),
                {},
                callback
            )
            return None
        else:
            return self._analyze_position_sync(fen, depth, time_limit, multipv)

    def _analyze_position_sync(self, fen: str, depth: int,
                                time_limit: Optional[float],
                                multipv: int) -> PositionAnalysis:
        """Synchronous position analysis."""
        board = chess.Board(fen)
        start = time.time()

        limit = chess.engine.Limit(depth=depth)
        if time_limit:
            limit = chess.engine.Limit(time=time_limit, depth=depth)

        with self._engine.analysis(board, limit, multipv=multipv) as analysis:
            info = None
            lines = []

            for info in analysis:
                pass  # Let it complete

        thinking_time = time.time() - start
        lines = []

        if info:
            # Process multi-PV lines
            for pv_num in range(1, multipv + 1):
                try:
                    pv_info = info.get(pv_num) if hasattr(info, 'get') else None
                    if pv_info is None:
                        continue

                    score = pv_info.get("score")
                    pv_moves = pv_info.get("pv", [])

                    if not score:
                        continue

                    cp = score.white().score(mate_score=10000)
                    mate = score.white().mate()

                    san_moves = []
                    temp_board = board.copy()
                    for move in pv_moves[:10]:
                        try:
                            san_moves.append(temp_board.san(move))
                            temp_board.push(move)
                        except Exception:
                            break

                    lines.append(AnalysisLine(
                        moves=[m.uci() for m in pv_moves[:10]],
                        san_moves=san_moves,
                        score=cp or 0,
                        mate_in=mate,
                        depth=pv_info.get("depth", depth)
                    ))
                except Exception:
                    continue

        # Fallback: use simple analysis
        if not lines:
            try:
                result = self._engine.analyse(board, chess.engine.Limit(depth=depth))
                score = result.get("score")
                pv = result.get("pv", [])

                cp = score.white().score(mate_score=10000) if score else 0
                mate = score.white().mate() if score else None

                san_moves = []
                temp_board = board.copy()
                for move in pv[:10]:
                    try:
                        san_moves.append(temp_board.san(move))
                        temp_board.push(move)
                    except Exception:
                        break

                lines.append(AnalysisLine(
                    moves=[m.uci() for m in pv[:10]],
                    san_moves=san_moves,
                    score=cp or 0,
                    mate_in=mate,
                    depth=result.get("depth", depth)
                ))
            except Exception as e:
                logger.error(f"Analysis fallback failed: {e}")

        best_line = lines[0] if lines else None
        best_move_uci = best_line.moves[0] if best_line and best_line.moves else None
        best_move_san = best_line.san_moves[0] if best_line and best_line.san_moves else None

        return PositionAnalysis(
            fen=fen,
            best_move=best_move_uci,
            best_move_san=best_move_san,
            evaluation=best_line.score if best_line else 0,
            mate_in=best_line.mate_in if best_line else None,
            depth=best_line.depth if best_line else 0,
            lines=lines,
            thinking_time=thinking_time
        )

    # ─── Move Evaluation ─────────────────────────────────────────────────────

    def evaluate_move(self, board_before: chess.Board,
                      move: chess.Move,
                      depth: int = 18) -> Tuple[float, str]:
        """
        Evaluate the quality of a move.
        Returns (accuracy_percentage, classification).
        
        Classifications:
        - Brilliant (!!)  
        - Best (!)
        - Good
        - Inaccuracy (?!)
        - Mistake (?)
        - Blunder (??)
        """
        if not self.is_ready:
            return 100.0, "good"

        try:
            # Analyze position before move
            before_analysis = self._analyze_position_sync(
                board_before.fen(), depth, None, 1
            )

            # Apply move and analyze resulting position
            board_after = board_before.copy()
            board_after.push(move)
            after_analysis = self._analyze_position_sync(
                board_after.fen(), depth, None, 1
            )

            # Convert evaluations to the moving side's perspective
            color = board_before.turn
            sign = 1 if color == chess.WHITE else -1

            eval_before = sign * before_analysis.evaluation
            eval_after = sign * (-after_analysis.evaluation)  # Flip for opponent's turn

            # Best possible move's evaluation
            best_eval = eval_before

            # Centipawn loss
            cp_loss = max(0, best_eval - eval_after)

            # Classify the move
            classification = self._classify_move(cp_loss, eval_before, eval_after)

            # Calculate accuracy (0-100)
            accuracy = max(0, min(100, 100 - (cp_loss / 10)))

            return accuracy, classification

        except Exception as e:
            logger.error(f"Move evaluation error: {e}")
            return 100.0, "good"

    def _classify_move(self, cp_loss: float,
                       eval_before: float,
                       eval_after: float) -> str:
        """Classify a move based on centipawn loss."""
        if cp_loss == 0:
            return "best"
        elif cp_loss < 10:
            return "good"
        elif cp_loss < 30:
            return "inaccuracy"
        elif cp_loss < 100:
            return "mistake"
        else:
            return "blunder"

    # ─── Engine Discovery ─────────────────────────────────────────────────────

    @staticmethod
    def find_stockfish() -> Optional[str]:
        """
        Try to auto-detect Stockfish installation.
        Checks common installation paths.
        """
        # Common paths by platform
        if sys.platform == "win32":
            candidates = [
                "stockfish.exe",
                r"C:\Program Files\Stockfish\stockfish.exe",
                r"C:\stockfish\stockfish.exe",
                os.path.join(os.path.dirname(__file__), "..", "engines", "stockfish.exe"),
            ]
        elif sys.platform == "darwin":
            candidates = [
                "/usr/local/bin/stockfish",
                "/opt/homebrew/bin/stockfish",
                "/usr/bin/stockfish",
            ]
        else:
            candidates = [
                "/usr/bin/stockfish",
                "/usr/local/bin/stockfish",
                "/usr/games/stockfish",
                "stockfish",
            ]

        # Also check engines directory in project
        project_engines = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "engines"
        )
        if os.path.exists(project_engines):
            for f in os.listdir(project_engines):
                if "stockfish" in f.lower():
                    candidates.insert(0, os.path.join(project_engines, f))

        for path in candidates:
            try:
                # Expand environment variables
                path = os.path.expandvars(os.path.expanduser(path))
                if os.path.isfile(path) and os.access(path, os.X_OK):
                    return path
                # Try running it from PATH
                result = subprocess.run(
                    [path, "quit"],
                    capture_output=True,
                    timeout=3
                )
                if result.returncode in (0, 1):
                    return path
            except Exception:
                continue

        return None

    def get_engine_info(self) -> Dict:
        """Get information about the running engine."""
        if not self._engine:
            return {"status": "not_running"}

        try:
            return {
                "status": "running",
                "path": self._engine_path,
                "elo": self._config.elo,
                "depth": self._config.depth,
                "personality": self._config.personality.value,
            }
        except Exception:
            return {"status": "error"}
