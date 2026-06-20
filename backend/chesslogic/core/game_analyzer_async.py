"""
Game Analyzer for ChessCoach Web.
Pure async version — no Qt dependencies.
"""

import chess
import chess.pgn
import io
import asyncio
from typing import List, Optional, Dict, Callable, Awaitable
from dataclasses import dataclass, field

from chesslogic.engine.engine_manager import EngineManager
from chesslogic.coach.chess_coach_engine import ChessCoach
from chesslogic.utils.logger import get_logger

logger = get_logger("analyzer")

ProgressCallback = Callable[[int, int], Awaitable[None]]


@dataclass
class MoveAnalysisResult:
    move_index: int
    san: str
    uci: str
    color: int                      # chess.WHITE / chess.BLACK
    evaluation_before: float
    evaluation_after: float
    best_move_uci: str
    best_move_san: str
    cp_loss: float
    accuracy: float
    classification: str             # best / good / inaccuracy / mistake / blunder
    comment: str = ""


@dataclass
class GameReport:
    total_moves: int
    white_accuracy: float
    black_accuracy: float
    white_blunders: int
    white_mistakes: int
    white_inaccuracies: int
    black_blunders: int
    black_mistakes: int
    black_inaccuracies: int
    white_best_moves: int
    black_best_moves: int
    opening_name: str
    opening_eco: str
    move_analyses: List[MoveAnalysisResult] = field(default_factory=list)
    key_moments: List[Dict] = field(default_factory=list)

    def grade(self, color: int) -> str:
        acc = self.white_accuracy if color == chess.WHITE else self.black_accuracy
        for threshold, letter in [(95, "A+"), (90, "A"), (85, "B+"),
                                   (80, "B"), (75, "C+"), (70, "C"), (60, "D")]:
            if acc >= threshold:
                return letter
        return "F"

    def to_dict(self) -> Dict:
        return {
            "total_moves": self.total_moves,
            "white_accuracy": round(self.white_accuracy, 1),
            "black_accuracy": round(self.black_accuracy, 1),
            "white_blunders": self.white_blunders,
            "white_mistakes": self.white_mistakes,
            "white_inaccuracies": self.white_inaccuracies,
            "black_blunders": self.black_blunders,
            "black_mistakes": self.black_mistakes,
            "black_inaccuracies": self.black_inaccuracies,
            "white_best_moves": self.white_best_moves,
            "black_best_moves": self.black_best_moves,
            "white_grade": self.grade(chess.WHITE),
            "black_grade": self.grade(chess.BLACK),
            "opening_name": self.opening_name,
            "opening_eco": self.opening_eco,
            "key_moments": self.key_moments,
            "move_analyses": [
                {
                    "move_index": a.move_index,
                    "san": a.san,
                    "uci": a.uci,
                    "color": a.color,
                    "cp_loss": round(a.cp_loss, 1),
                    "accuracy": round(a.accuracy, 1),
                    "classification": a.classification,
                    "best_move_san": a.best_move_san,
                    "comment": a.comment,
                }
                for a in self.move_analyses
            ],
        }


async def analyze_game_pgn(
    pgn_text: str,
    engine: EngineManager,
    depth: int = 18,
    progress_cb: Optional[ProgressCallback] = None,
) -> GameReport:
    """
    Fully async game analysis.
    Runs engine calls in a thread executor to avoid blocking the event loop.
    """
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if not game:
        raise ValueError("Could not parse PGN")

    board = game.board()
    moves = list(game.mainline_moves())
    total = len(moves)
    coach = ChessCoach()
    loop = asyncio.get_event_loop()
    analyses: List[MoveAnalysisResult] = []

    prev_analysis = await loop.run_in_executor(
        None,
        lambda: engine._analyze_position_sync(board.fen(), depth, None, 1)
    )

    for i, move in enumerate(moves):
        if progress_cb:
            await progress_cb(i + 1, total)

        color = board.turn
        fen_before = board.fen()
        san = board.san(move)

        eval_before = prev_analysis.evaluation if prev_analysis else 0
        best_uci = prev_analysis.best_move or move.uci() if prev_analysis else move.uci()
        best_san = prev_analysis.best_move_san or san if prev_analysis else san

        board.push(move)

        curr = await loop.run_in_executor(
            None,
            lambda fen=board.fen(): engine._analyze_position_sync(fen, depth, None, 1)
        )
        eval_after = curr.evaluation if curr else 0

        sign = 1 if color == chess.WHITE else -1
        rel_before = sign * eval_before
        rel_after = -sign * eval_after

        cp_loss = max(0.0, rel_before - rel_after)
        classification = _classify(cp_loss)
        accuracy = max(0.0, min(100.0, 100.0 - cp_loss / 10.0))
        comment = coach.comment_on_move(chess.Board(fen_before), move, classification)

        analyses.append(MoveAnalysisResult(
            move_index=i,
            san=san,
            uci=move.uci(),
            color=int(color),
            evaluation_before=eval_before,
            evaluation_after=eval_after,
            best_move_uci=best_uci or "",
            best_move_san=best_san or "",
            cp_loss=cp_loss,
            accuracy=accuracy,
            classification=classification,
            comment=comment,
        ))
        prev_analysis = curr

        # Yield control every 5 moves so WS stays responsive
        if i % 5 == 0:
            await asyncio.sleep(0)

    return _build_report(analyses, game)


def _classify(cp_loss: float) -> str:
    if cp_loss == 0:     return "best"
    if cp_loss < 10:     return "good"
    if cp_loss < 30:     return "inaccuracy"
    if cp_loss < 100:    return "mistake"
    return "blunder"


def _build_report(analyses: List[MoveAnalysisResult],
                  game: chess.pgn.Game) -> GameReport:
    white = [a for a in analyses if a.color == chess.WHITE]
    black = [a for a in analyses if a.color == chess.BLACK]

    def avg_acc(lst): return sum(a.accuracy for a in lst) / len(lst) if lst else 100.0
    def cnt(lst, cls): return sum(1 for a in lst if a.classification == cls)

    key_moments = sorted(
        [
            {
                "move_number": (a.move_index // 2) + 1,
                "color": "white" if a.color == chess.WHITE else "black",
                "classification": a.classification,
                "san": a.san,
                "best_san": a.best_move_san,
                "cp_loss": round(a.cp_loss),
                "description": (
                    f"{'White' if a.color == chess.WHITE else 'Black'} played "
                    f"{a.san} ({a.classification}, -{a.cp_loss:.0f} cp). "
                    f"Best was {a.best_move_san}."
                ),
            }
            for a in analyses if a.classification in ("blunder", "mistake")
        ],
        key=lambda k: k["cp_loss"],
        reverse=True,
    )[:10]

    return GameReport(
        total_moves=len(analyses),
        white_accuracy=avg_acc(white),
        black_accuracy=avg_acc(black),
        white_blunders=cnt(white, "blunder"),
        white_mistakes=cnt(white, "mistake"),
        white_inaccuracies=cnt(white, "inaccuracy"),
        black_blunders=cnt(black, "blunder"),
        black_mistakes=cnt(black, "mistake"),
        black_inaccuracies=cnt(black, "inaccuracy"),
        white_best_moves=cnt(white, "best"),
        black_best_moves=cnt(black, "best"),
        opening_name=game.headers.get("Opening", "Unknown"),
        opening_eco=game.headers.get("ECO", "?"),
        move_analyses=analyses,
        key_moments=key_moments,
    )
