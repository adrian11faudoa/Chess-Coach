"""
Chess Coach Engine for ChessCoach.

The heart of the educational system. Analyzes positions and generates
natural language explanations of:
- Tactical motifs (forks, pins, skewers, discovered attacks)
- Strategic themes (weak squares, pawn structure, king safety)
- Move quality assessments
- Plans and ideas
- Opening transitions
"""

import chess
import chess.pgn
from typing import Optional, List, Dict, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
import random

from chesslogic.engine.engine_manager import PositionAnalysis, AnalysisLine
from chesslogic.utils.logger import get_logger

logger = get_logger("coach")


class TacticalMotif(Enum):
    FORK = "fork"
    PIN = "pin"
    SKEWER = "skewer"
    DISCOVERED_ATTACK = "discovered_attack"
    DOUBLE_CHECK = "double_check"
    BACK_RANK = "back_rank"
    OVERLOADED_PIECE = "overloaded_piece"
    ZWISCHENZUG = "zwischenzug"
    DEFLECTION = "deflection"
    DECOY = "decoy"
    TRAPPED_PIECE = "trapped_piece"
    ZUGZWANG = "zugzwang"


class StrategicTheme(Enum):
    WEAK_SQUARES = "weak_squares"
    OUTPOST = "outpost"
    PAWN_MAJORITY = "pawn_majority"
    PAWN_MINORITY = "pawn_minority"
    OPEN_FILE = "open_file"
    HALF_OPEN_FILE = "half_open_file"
    BISHOP_PAIR = "bishop_pair"
    KNIGHT_VS_BISHOP = "knight_vs_bishop"
    BAD_BISHOP = "bad_bishop"
    KING_SAFETY = "king_safety"
    KING_ATTACK = "king_attack"
    SPACE_ADVANTAGE = "space_advantage"
    INITIATIVE = "initiative"
    TEMPO = "tempo"
    PROPHYLAXIS = "prophylaxis"
    RESTRICTION = "restriction"
    PASSED_PAWN = "passed_pawn"
    ISOLATED_PAWN = "isolated_pawn"
    DOUBLED_PAWNS = "doubled_pawns"
    BACKWARD_PAWN = "backward_pawn"
    PAWN_CHAIN = "pawn_chain"


@dataclass
class CoachComment:
    """A single coaching comment with context."""
    text: str
    category: str           # tactical, strategic, opening, endgame, evaluation
    priority: int = 5       # 1-10, higher = more important
    motifs: List[str] = field(default_factory=list)
    squares: List[str] = field(default_factory=list)   # Relevant squares
    move_quality: Optional[str] = None  # best, good, inaccuracy, mistake, blunder


@dataclass 
class PositionAssessment:
    """Complete coach assessment of a position."""
    evaluation_text: str
    tactical_comments: List[CoachComment] = field(default_factory=list)
    strategic_comments: List[CoachComment] = field(default_factory=list)
    plan_comments: List[CoachComment] = field(default_factory=list)
    warning_comments: List[CoachComment] = field(default_factory=list)
    primary_comment: Optional[str] = None

    @property
    def all_comments(self) -> List[CoachComment]:
        all_c = (self.warning_comments + self.tactical_comments +
                 self.strategic_comments + self.plan_comments)
        return sorted(all_c, key=lambda c: c.priority, reverse=True)


class ChessCoach:
    """
    The educational coach that analyzes positions and explains chess concepts.
    
    Combines tactical pattern recognition, strategic theme identification,
    and natural language generation to provide meaningful coaching feedback.
    """

    # Piece value map for tactical calculations
    PIECE_VALUES = {
        chess.PAWN: 1,
        chess.KNIGHT: 3,
        chess.BISHOP: 3,
        chess.ROOK: 5,
        chess.QUEEN: 9,
        chess.KING: 0,
    }

    def __init__(self, verbosity: str = "normal"):
        """
        Initialize the coach.
        
        verbosity: 'minimal', 'normal', 'detailed'
        """
        self.verbosity = verbosity

    # ─── Main Assessment Interface ────────────────────────────────────────────

    def assess_position(self, board: chess.Board,
                        analysis: Optional[PositionAnalysis] = None,
                        color_perspective: Optional[chess.Color] = None) -> PositionAssessment:
        """
        Generate a complete coaching assessment of the current position.
        """
        if color_perspective is None:
            color_perspective = board.turn

        assessment = PositionAssessment(
            evaluation_text=self._describe_evaluation(board, analysis, color_perspective)
        )

        # Tactical analysis
        tactical = self._analyze_tactics(board, color_perspective)
        assessment.tactical_comments.extend(tactical)

        # Strategic analysis
        strategic = self._analyze_strategy(board, color_perspective)
        assessment.strategic_comments.extend(strategic)

        # Plans and ideas
        plans = self._suggest_plans(board, analysis, color_perspective)
        assessment.plan_comments.extend(plans)

        # Warnings (threats, king safety)
        warnings = self._check_warnings(board, color_perspective)
        assessment.warning_comments.extend(warnings)

        # Select the most important primary comment
        all_comments = assessment.all_comments
        if all_comments:
            assessment.primary_comment = all_comments[0].text

        return assessment

    def comment_on_move(self, board_before: chess.Board,
                        move: chess.Move,
                        classification: str,
                        analysis_before: Optional[PositionAnalysis] = None,
                        analysis_after: Optional[PositionAnalysis] = None) -> str:
        """
        Generate a coach comment specifically about a played move.
        """
        color = board_before.turn
        color_name = "White" if color == chess.WHITE else "Black"
        san = board_before.san(move)

        board_after = board_before.copy()
        board_after.push(move)

        comments = []

        # Comment on move quality
        quality_comment = self._comment_on_quality(
            classification, san, board_before, move, analysis_before
        )
        if quality_comment:
            comments.append(quality_comment)

        # Comment on tactical ideas
        tactic = self._detect_move_tactic(board_before, move, board_after)
        if tactic:
            comments.append(tactic)

        # Comment on strategic implications
        strategic = self._comment_on_strategic_impact(board_before, move, board_after)
        if strategic:
            comments.append(strategic)

        if comments:
            return " ".join(comments)

        return self._generic_move_comment(board_before, move, board_after)

    # ─── Evaluation Description ───────────────────────────────────────────────

    def _describe_evaluation(self, board: chess.Board,
                              analysis: Optional[PositionAnalysis],
                              perspective: chess.Color) -> str:
        """Generate a natural language description of the position's evaluation."""
        if not analysis:
            return "Position is being evaluated..."

        if analysis.mate_in is not None:
            sign = 1 if perspective == chess.WHITE else -1
            effective_mate = sign * analysis.mate_in
            if effective_mate > 0:
                return f"You have a forced checkmate in {abs(effective_mate)} move{'s' if abs(effective_mate) > 1 else ''}! Find the winning sequence."
            else:
                return f"The opponent has a forced checkmate in {abs(effective_mate)} move{'s' if abs(effective_mate) > 1 else ''}. Find the best defense."

        sign = 1 if perspective == chess.WHITE else -1
        rel_eval = sign * analysis.evaluation

        if rel_eval > 500:
            return "You have a completely winning position. Convert it carefully."
        elif rel_eval > 200:
            return f"You have a strong advantage (+{rel_eval/100:.1f}). Press it with accuracy."
        elif rel_eval > 80:
            return f"You have a slight advantage (+{rel_eval/100:.1f}). Look for a plan to increase it."
        elif rel_eval > 20:
            return f"You have a small edge (+{rel_eval/100:.1f}). Continue solid play."
        elif rel_eval > -20:
            return "The position is approximately equal. Find the best plan."
        elif rel_eval > -80:
            return f"You are slightly worse ({rel_eval/100:.1f}). Look for counterplay."
        elif rel_eval > -200:
            return f"You are at a disadvantage ({rel_eval/100:.1f}). Find active defensive resources."
        elif rel_eval > -500:
            return f"You are in serious trouble ({rel_eval/100:.1f}). Find the most stubborn defense."
        else:
            return "Your position is very difficult. Look for practical chances."

    # ─── Tactical Analysis ────────────────────────────────────────────────────

    def _analyze_tactics(self, board: chess.Board,
                         perspective: chess.Color) -> List[CoachComment]:
        """Detect and explain tactical motifs in the position."""
        comments = []

        # Check for forks
        forks = self._find_forks(board, perspective)
        comments.extend(forks)

        # Check for pins
        pins = self._find_pins(board, perspective)
        comments.extend(pins)

        # Check for back rank weakness
        back_rank = self._check_back_rank(board, perspective)
        if back_rank:
            comments.append(back_rank)

        # Check for trapped pieces
        trapped = self._find_trapped_pieces(board, 1 - perspective)
        comments.extend(trapped)

        return comments

    def _find_forks(self, board: chess.Board,
                    color: chess.Color) -> List[CoachComment]:
        """Find knight and pawn fork opportunities."""
        comments = []

        # Check for possible knight forks
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if piece and piece.color == color and piece.piece_type == chess.KNIGHT:
                # Check each square the knight attacks
                attacks = board.attacks(sq)
                attacked_pieces = []
                for target_sq in attacks:
                    target = board.piece_at(target_sq)
                    if target and target.color != color and target.piece_type != chess.PAWN:
                        attacked_pieces.append((target_sq, target))

                if len(attacked_pieces) >= 2:
                    # Knight is forking multiple pieces
                    piece_names = [chess.piece_name(p.piece_type) for _, p in attacked_pieces]
                    squares_names = [chess.square_name(sq) for sq, _ in attacked_pieces]
                    comments.append(CoachComment(
                        text=f"Your knight on {chess.square_name(sq)} is forking the {' and '.join(piece_names)} on {' and '.join(squares_names)}!",
                        category="tactical",
                        priority=8,
                        motifs=["fork"],
                        squares=[chess.square_name(sq)] + squares_names
                    ))

        # Look for potential knight forks (one move away)
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if piece and piece.color == color and piece.piece_type == chess.KNIGHT:
                # Check each potential landing square for the knight
                for landing in chess.SQUARES:
                    if chess.square_distance(sq, landing) > 3:
                        continue
                    # Check if this is a valid knight move
                    diff = abs(chess.square_file(sq) - chess.square_file(landing))
                    diff2 = abs(chess.square_rank(sq) - chess.square_rank(landing))
                    if not ({diff, diff2} == {1, 2}):
                        continue
                    # Check if landing is safe
                    landing_piece = board.piece_at(landing)
                    if landing_piece and landing_piece.color == color:
                        continue

                    # Count attacks from this landing square
                    attacks_from_landing = chess.SquareSet(
                        chess.BB_KNIGHT_ATTACKS[landing]
                    )
                    fork_targets = []
                    for target_sq in attacks_from_landing:
                        target = board.piece_at(target_sq)
                        if (target and target.color != color and
                                target.piece_type in (chess.QUEEN, chess.ROOK, chess.KING)):
                            fork_targets.append((target_sq, target))

                    if len(fork_targets) >= 2:
                        target_names = [chess.piece_name(t.piece_type) for _, t in fork_targets]
                        comments.append(CoachComment(
                            text=f"Look for a knight fork! Moving to {chess.square_name(landing)} would attack the {' and '.join(target_names)} simultaneously.",
                            category="tactical",
                            priority=7,
                            motifs=["fork"],
                            squares=[chess.square_name(landing)]
                        ))
                        break

        return comments[:2]  # Limit to most important

    def _find_pins(self, board: chess.Board,
                   color: chess.Color) -> List[CoachComment]:
        """Detect pins and explain their significance."""
        comments = []
        opponent = not color

        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if not piece or piece.color != color:
                continue

            # Check if this piece is pinned
            if board.is_pinned(color, sq):
                pinner_sq = board.pin(color, sq)
                # Find the pinner piece
                for pinner_sq in chess.SQUARES:
                    pinner = board.piece_at(pinner_sq)
                    if pinner and pinner.color == opponent:
                        if chess.square_name(pinner_sq) in str(board.pin(color, sq)):
                            pass

                comments.append(CoachComment(
                    text=f"Your {chess.piece_name(piece.piece_type)} on {chess.square_name(sq)} is pinned! It cannot move without exposing a more valuable piece.",
                    category="tactical",
                    priority=6,
                    motifs=["pin"],
                    squares=[chess.square_name(sq)]
                ))

        return comments[:1]

    def _check_back_rank(self, board: chess.Board,
                         color: chess.Color) -> Optional[CoachComment]:
        """Check for back rank weakness."""
        back_rank = chess.BB_RANK_1 if color == chess.WHITE else chess.BB_RANK_8
        king_sq = board.king(color)

        if not king_sq:
            return None

        # Check if king is on back rank and pawns are blocking escape
        if chess.BB_SQUARES[king_sq] & back_rank:
            escape_squares = 0
            for sq in chess.SquareSet(chess.BB_KING_ATTACKS[king_sq]):
                if not (chess.BB_SQUARES[sq] & back_rank):
                    escape_squares += 1

            if escape_squares == 0:
                # Check if opponent has a rook or queen that could exploit this
                opponent = not color
                for sq in chess.SQUARES:
                    piece = board.piece_at(sq)
                    if (piece and piece.color == opponent and
                            piece.piece_type in (chess.ROOK, chess.QUEEN)):
                        return CoachComment(
                            text="Warning: Your king has a back rank weakness! The opponent may threaten a back rank checkmate. Consider creating a luft (escape square) for your king.",
                            category="tactical",
                            priority=9,
                            motifs=["back_rank"],
                            squares=[chess.square_name(king_sq)]
                        )
        return None

    def _find_trapped_pieces(self, board: chess.Board,
                             color: chess.Color) -> List[CoachComment]:
        """Identify pieces with very limited mobility (potentially trapped)."""
        comments = []

        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if not piece or piece.color != color:
                continue
            if piece.piece_type in (chess.KING, chess.PAWN):
                continue

            # Count legal moves for this piece
            legal_moves = [m for m in board.legal_moves
                          if m.from_square == sq]

            if len(legal_moves) == 0 and piece.piece_type != chess.KING:
                comments.append(CoachComment(
                    text=f"The opponent's {chess.piece_name(piece.piece_type)} on {chess.square_name(sq)} has no legal moves — it's trapped!",
                    category="tactical",
                    priority=8,
                    motifs=["trapped_piece"],
                    squares=[chess.square_name(sq)]
                ))
            elif len(legal_moves) == 1 and piece.piece_type == chess.BISHOP:
                comments.append(CoachComment(
                    text=f"The {chess.piece_name(piece.piece_type)} on {chess.square_name(sq)} has very limited mobility. Consider exploiting this.",
                    category="tactical",
                    priority=5,
                    motifs=["trapped_piece"],
                    squares=[chess.square_name(sq)]
                ))

        return comments[:1]

    # ─── Strategic Analysis ───────────────────────────────────────────────────

    def _analyze_strategy(self, board: chess.Board,
                          perspective: chess.Color) -> List[CoachComment]:
        """Identify and explain strategic themes."""
        comments = []

        # Pawn structure analysis
        pawn_comments = self._analyze_pawn_structure(board, perspective)
        comments.extend(pawn_comments)

        # King safety
        king_comment = self._evaluate_king_safety(board, perspective)
        if king_comment:
            comments.append(king_comment)

        # Piece activity
        activity = self._evaluate_piece_activity(board, perspective)
        comments.extend(activity)

        # Open files
        file_comments = self._analyze_open_files(board, perspective)
        comments.extend(file_comments)

        # Outposts
        outpost_comments = self._find_outposts(board, perspective)
        comments.extend(outpost_comments)

        return comments

    def _analyze_pawn_structure(self, board: chess.Board,
                                color: chess.Color) -> List[CoachComment]:
        """Analyze pawn structure weaknesses and strengths."""
        comments = []
        opponent = not color

        # Find doubled pawns
        for file in range(8):
            pawns_on_file = 0
            opp_pawns_on_file = 0
            for rank in range(8):
                sq = chess.square(file, rank)
                piece = board.piece_at(sq)
                if piece and piece.piece_type == chess.PAWN:
                    if piece.color == color:
                        pawns_on_file += 1
                    else:
                        opp_pawns_on_file += 1

            if pawns_on_file >= 2:
                file_name = "abcdefgh"[file]
                comments.append(CoachComment(
                    text=f"You have doubled pawns on the {file_name}-file. These can be a structural weakness — keep an eye on them.",
                    category="strategic",
                    priority=4,
                    motifs=["doubled_pawns"]
                ))

        # Find isolated pawns
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if not piece or piece.piece_type != chess.PAWN or piece.color != color:
                continue

            file = chess.square_file(sq)
            is_isolated = True

            for adj_file in [file - 1, file + 1]:
                if 0 <= adj_file <= 7:
                    for rank in range(8):
                        adj_sq = chess.square(adj_file, rank)
                        adj_piece = board.piece_at(adj_sq)
                        if adj_piece and adj_piece.piece_type == chess.PAWN and adj_piece.color == color:
                            is_isolated = False
                            break

            if is_isolated:
                comments.append(CoachComment(
                    text=f"Your pawn on {chess.square_name(sq)} is isolated — it has no pawn neighbors to support it. Avoid creating more pawn weaknesses.",
                    category="strategic",
                    priority=4,
                    motifs=["isolated_pawn"],
                    squares=[chess.square_name(sq)]
                ))

        # Find passed pawns
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if not piece or piece.piece_type != chess.PAWN or piece.color != color:
                continue

            if self._is_passed_pawn(board, sq, color):
                rank = chess.square_rank(sq)
                advancement = rank if color == chess.WHITE else 7 - rank
                if advancement >= 4:
                    comments.append(CoachComment(
                        text=f"You have a powerful passed pawn on {chess.square_name(sq)}! Push it forward — passed pawns must be advanced.",
                        category="strategic",
                        priority=7,
                        motifs=["passed_pawn"],
                        squares=[chess.square_name(sq)]
                    ))
                else:
                    comments.append(CoachComment(
                        text=f"You have a passed pawn on {chess.square_name(sq)}. Support it with your pieces and advance it when the time is right.",
                        category="strategic",
                        priority=5,
                        motifs=["passed_pawn"],
                        squares=[chess.square_name(sq)]
                    ))

        return comments[:3]

    def _is_passed_pawn(self, board: chess.Board,
                        sq: chess.Square, color: chess.Color) -> bool:
        """Check if a pawn is passed (no opponent pawns blocking or adjacent)."""
        file = chess.square_file(sq)
        rank = chess.square_rank(sq)
        opponent = not color

        ranks_ahead = range(rank + 1, 8) if color == chess.WHITE else range(rank - 1, -1, -1)

        for check_rank in ranks_ahead:
            for check_file in [file - 1, file, file + 1]:
                if 0 <= check_file <= 7:
                    check_sq = chess.square(check_file, check_rank)
                    piece = board.piece_at(check_sq)
                    if piece and piece.piece_type == chess.PAWN and piece.color == opponent:
                        return False
        return True

    def _evaluate_king_safety(self, board: chess.Board,
                              color: chess.Color) -> Optional[CoachComment]:
        """Evaluate king safety and warn about dangers."""
        king_sq = board.king(color)
        if not king_sq:
            return None

        opponent = not color

        # Count attackers near the king
        king_zone = chess.SquareSet(chess.BB_KING_ATTACKS[king_sq])
        attackers = 0
        for sq in king_zone:
            attackers += len(list(board.attackers(opponent, sq)))

        # Check if king has castled (roughly)
        king_file = chess.square_file(king_sq)
        king_rank = chess.square_rank(king_sq)
        on_back_rank = (king_rank == 0 and color == chess.WHITE) or \
                       (king_rank == 7 and color == chess.BLACK)

        if not on_back_rank and board.fullmove_number > 5:
            return CoachComment(
                text="Your king is in the center! Consider castling soon to ensure king safety.",
                category="strategic",
                priority=8,
                motifs=["king_safety"],
                squares=[chess.square_name(king_sq)]
            )

        if attackers > 3:
            return CoachComment(
                text=f"Your king is under significant pressure! The opponent has {attackers} attacking pieces near your king. Prioritize defense.",
                category="strategic",
                priority=9,
                motifs=["king_safety"],
                squares=[chess.square_name(king_sq)]
            )

        # Check pawn shelter
        if on_back_rank:
            shelter_pawns = 0
            pawn_rank = 1 if color == chess.WHITE else 6
            for file in range(max(0, king_file - 1), min(8, king_file + 2)):
                sq = chess.square(file, pawn_rank)
                piece = board.piece_at(sq)
                if piece and piece.piece_type == chess.PAWN and piece.color == color:
                    shelter_pawns += 1

            if shelter_pawns == 0 and board.fullmove_number > 10:
                return CoachComment(
                    text="Your king's pawn shelter has been broken. Be careful of attacks on the open lines near your king.",
                    category="strategic",
                    priority=7,
                    motifs=["king_safety"]
                )

        return None

    def _evaluate_piece_activity(self, board: chess.Board,
                                 color: chess.Color) -> List[CoachComment]:
        """Evaluate piece activity and mobility."""
        comments = []

        # Check for undeveloped pieces in the opening/middlegame
        if board.fullmove_number <= 15:
            undeveloped = []
            back_rank = 0 if color == chess.WHITE else 7

            for file in [1, 2, 5, 6]:  # b, c, f, g files (knights and bishops)
                sq = chess.square(file, back_rank)
                piece = board.piece_at(sq)
                if piece and piece.color == color and piece.piece_type in (chess.KNIGHT, chess.BISHOP):
                    undeveloped.append(chess.piece_name(piece.piece_type))

            if undeveloped:
                pieces_str = ", ".join(undeveloped)
                comments.append(CoachComment(
                    text=f"Develop your {pieces_str}! In the opening, piece development is crucial. Get your pieces to active squares.",
                    category="strategic",
                    priority=6,
                    motifs=["development"]
                ))

        # Check bishop activity (bad bishop)
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if not piece or piece.piece_type != chess.BISHOP or piece.color != color:
                continue

            # Count own pawns on same color squares as bishop
            bishop_color = (chess.square_file(sq) + chess.square_rank(sq)) % 2
            blocked_pawns = 0
            for psq in chess.SQUARES:
                pawn = board.piece_at(psq)
                if (pawn and pawn.piece_type == chess.PAWN and pawn.color == color):
                    pawn_color = (chess.square_file(psq) + chess.square_rank(psq)) % 2
                    if pawn_color == bishop_color:
                        blocked_pawns += 1

            if blocked_pawns >= 4:
                comments.append(CoachComment(
                    text=f"Your bishop on {chess.square_name(sq)} is a 'bad bishop' — it's blocked by your own pawns on the same color. Try to activate it or exchange it.",
                    category="strategic",
                    priority=4,
                    motifs=["bad_bishop"],
                    squares=[chess.square_name(sq)]
                ))

        return comments[:2]

    def _analyze_open_files(self, board: chess.Board,
                            color: chess.Color) -> List[CoachComment]:
        """Find open and semi-open files and their strategic significance."""
        comments = []

        for file in range(8):
            white_pawns = 0
            black_pawns = 0
            for rank in range(8):
                sq = chess.square(file, rank)
                piece = board.piece_at(sq)
                if piece and piece.piece_type == chess.PAWN:
                    if piece.color == chess.WHITE:
                        white_pawns += 1
                    else:
                        black_pawns += 1

            file_name = "abcdefgh"[file]

            if white_pawns == 0 and black_pawns == 0:
                # Fully open file — check if we have a rook/queen to use it
                for rank in range(8):
                    sq = chess.square(file, rank)
                    piece = board.piece_at(sq)
                    if piece and piece.color == color and piece.piece_type in (chess.ROOK, chess.QUEEN):
                        comments.append(CoachComment(
                            text=f"The {file_name}-file is open. Your {chess.piece_name(piece.piece_type)} is well-placed there. Consider doubling rooks on this file.",
                            category="strategic",
                            priority=5,
                            motifs=["open_file"]
                        ))
                        break

            elif (color == chess.WHITE and white_pawns == 0) or \
                 (color == chess.BLACK and black_pawns == 0):
                # Semi-open file for our color
                comments.append(CoachComment(
                    text=f"You have a semi-open {file_name}-file. Place your rook here to create pressure.",
                    category="strategic",
                    priority=4,
                    motifs=["half_open_file"]
                ))

        return comments[:2]

    def _find_outposts(self, board: chess.Board,
                       color: chess.Color) -> List[CoachComment]:
        """Find strong outpost squares for knights."""
        comments = []
        opponent = not color

        # Strong squares are those not attacked by opponent pawns
        for sq in chess.SQUARES:
            rank = chess.square_rank(sq)
            file = chess.square_file(sq)

            # Outposts are in opponent's territory
            if color == chess.WHITE and rank < 4:
                continue
            if color == chess.BLACK and rank > 3:
                continue

            # Check if square is attacked by opponent pawn
            attacked_by_pawn = False
            pawn_attack_ranks = [rank - 1] if color == chess.WHITE else [rank + 1]
            for prank in pawn_attack_ranks:
                if 0 <= prank <= 7:
                    for pfile in [file - 1, file + 1]:
                        if 0 <= pfile <= 7:
                            psq = chess.square(pfile, prank)
                            piece = board.piece_at(psq)
                            if piece and piece.piece_type == chess.PAWN and piece.color == opponent:
                                attacked_by_pawn = True

            if not attacked_by_pawn:
                # Check if one of our knights is near this square
                for nsq in chess.SQUARES:
                    piece = board.piece_at(nsq)
                    if piece and piece.color == color and piece.piece_type == chess.KNIGHT:
                        if chess.square_distance(nsq, sq) <= 2:
                            # Check if we have a pawn supporting this square
                            supported = any(
                                board.piece_at(chess.square(f, r)) and
                                board.piece_at(chess.square(f, r)).piece_type == chess.PAWN and
                                board.piece_at(chess.square(f, r)).color == color
                                for f in [file - 1, file + 1]
                                for r in ([rank - 1] if color == chess.WHITE else [rank + 1])
                                if 0 <= f <= 7 and 0 <= r <= 7
                            )
                            if supported:
                                comments.append(CoachComment(
                                    text=f"The square {chess.square_name(sq)} is a strong outpost for your knight — it cannot be attacked by opponent pawns. Maneuver your knight there.",
                                    category="strategic",
                                    priority=5,
                                    motifs=["outpost"],
                                    squares=[chess.square_name(sq)]
                                ))
                                break

        return comments[:1]

    # ─── Plans and Ideas ─────────────────────────────────────────────────────

    def _suggest_plans(self, board: chess.Board,
                       analysis: Optional[PositionAnalysis],
                       color: chess.Color) -> List[CoachComment]:
        """Suggest concrete plans based on the position."""
        comments = []

        game_phase = self._determine_game_phase(board)

        if game_phase == "opening":
            plans = self._opening_plans(board, color)
        elif game_phase == "middlegame":
            plans = self._middlegame_plans(board, color, analysis)
        else:
            plans = self._endgame_plans(board, color)

        comments.extend(plans)

        # Suggest engine's best move area if analysis available
        if analysis and analysis.best_move_san and self.verbosity == "detailed":
            comments.append(CoachComment(
                text=f"The engine suggests considering {analysis.best_move_san} as a strong continuation.",
                category="plan",
                priority=3
            ))

        return comments

    def _opening_plans(self, board: chess.Board,
                       color: chess.Color) -> List[CoachComment]:
        """Generate opening-phase plans."""
        plans = []
        back_rank = 0 if color == chess.WHITE else 7

        # Check if queen is in center
        queen_sq = None
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if piece and piece.piece_type == chess.QUEEN and piece.color == color:
                queen_sq = sq
                break

        if queen_sq:
            file = chess.square_file(queen_sq)
            rank = chess.square_rank(queen_sq)
            if 2 <= file <= 5 and rank != back_rank:
                plans.append(CoachComment(
                    text="Your queen is in the center early. Be careful — it can be attacked and you'll lose tempo. Consider developing minor pieces first.",
                    category="plan",
                    priority=5
                ))

        # Check castling
        if not board.has_castling_rights(color):
            if board.is_check():
                plans.append(CoachComment(
                    text="Escape the check first, then focus on completing development.",
                    category="plan",
                    priority=9
                ))
        else:
            if board.fullmove_number >= 8:
                plans.append(CoachComment(
                    text="Consider castling soon to connect your rooks and secure your king.",
                    category="plan",
                    priority=6
                ))

        return plans

    def _middlegame_plans(self, board: chess.Board,
                          color: chess.Color,
                          analysis: Optional[PositionAnalysis]) -> List[CoachComment]:
        """Generate middlegame plans."""
        plans = []

        # Check for imbalances
        material = self._count_material(board, color)
        opp_material = self._count_material(board, not color)

        if material > opp_material + 3:
            plans.append(CoachComment(
                text="You have a material advantage. Simplify by exchanging pieces — your advantage grows in simplified positions.",
                category="plan",
                priority=6
            ))
        elif material < opp_material - 3:
            plans.append(CoachComment(
                text="You're down material. Avoid exchanges and create complications — your best chance is in tactical complexity.",
                category="plan",
                priority=6
            ))

        # Rooks on first rank
        rooks_connected = self._are_rooks_connected(board, color)
        if not rooks_connected:
            plans.append(CoachComment(
                text="Connect your rooks by clearing the back rank. Rooks are strongest when they work together.",
                category="plan",
                priority=4
            ))

        return plans

    def _endgame_plans(self, board: chess.Board,
                       color: chess.Color) -> List[CoachComment]:
        """Generate endgame-specific plans."""
        plans = []
        king_sq = board.king(color)

        if king_sq:
            # In endgames, king should be active
            king_file = chess.square_file(king_sq)
            king_rank = chess.square_rank(king_sq)
            in_center = (2 <= king_file <= 5) and (2 <= king_rank <= 5)

            if not in_center:
                plans.append(CoachComment(
                    text="In the endgame, activate your king! The king becomes a powerful fighting piece — march it toward the center.",
                    category="plan",
                    priority=7
                ))

        # Check for pawn endgame
        non_king_pieces = sum(
            1 for sq in chess.SQUARES
            for p in [board.piece_at(sq)]
            if p and p.piece_type not in (chess.KING, chess.PAWN)
        )

        if non_king_pieces == 0:
            plans.append(CoachComment(
                text="Pure pawn endgame! Key factors: king activity, pawn structure, and passed pawns. The opposition and triangulation are crucial techniques.",
                category="plan",
                priority=6
            ))

        return plans

    # ─── Warnings ─────────────────────────────────────────────────────────────

    def _check_warnings(self, board: chess.Board,
                        color: chess.Color) -> List[CoachComment]:
        """Check for immediate threats and dangers."""
        comments = []
        opponent = not color

        # Check if in check
        if board.is_check() and board.turn == color:
            comments.append(CoachComment(
                text="You are in check! You must address the check immediately.",
                category="warning",
                priority=10
            ))

        # Check for hanging pieces
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if not piece or piece.color != color or piece.piece_type == chess.PAWN:
                continue

            attackers = board.attackers(opponent, sq)
            defenders = board.attackers(color, sq)

            if attackers and not defenders:
                comments.append(CoachComment(
                    text=f"Warning: Your {chess.piece_name(piece.piece_type)} on {chess.square_name(sq)} is undefended and under attack! Protect it or move it.",
                    category="warning",
                    priority=8,
                    squares=[chess.square_name(sq)]
                ))

        # Check for threatened checkmate patterns
        opponent_moves = list(board.legal_moves) if board.turn == opponent else []
        for move in opponent_moves[:50]:  # Check first 50 opponent moves for performance
            test_board = board.copy()
            test_board.push(move)
            if test_board.is_checkmate():
                comments.append(CoachComment(
                    text=f"Warning: The opponent threatens checkmate! Watch out for {board.san(move) if board.turn == opponent else '...'}.",
                    category="warning",
                    priority=10
                ))
                break

        return comments[:2]

    # ─── Move-Specific Commentary ─────────────────────────────────────────────

    def _comment_on_quality(self, classification: str, san: str,
                            board: chess.Board, move: chess.Move,
                            analysis: Optional[PositionAnalysis]) -> str:
        """Generate commentary based on move classification."""
        templates = {
            "best": [
                f"Excellent! {san} is the best move.",
                f"Perfect! {san} — the engine agrees.",
                f"Outstanding choice with {san}.",
            ],
            "good": [
                f"Good move! {san} keeps the position solid.",
                f"{san} is a sound continuation.",
                f"Well played with {san}.",
            ],
            "inaccuracy": [
                f"{san} is a slight inaccuracy. There was a stronger option.",
                f"Hmm, {san} isn't quite optimal. You could have done better.",
                f"{san} misses a nuance in the position.",
            ],
            "mistake": [
                f"{san} is a mistake! This gives away your advantage.",
                f"Careful — {san} is not the right plan here.",
                f"{san} overlooks something important.",
            ],
            "blunder": [
                f"Oh no! {san} is a blunder! This dramatically worsens your position.",
                f"That's a serious mistake — {san} loses significant material or position.",
                f"{san} is a critical error. Let's look at what you missed.",
            ],
        }

        options = templates.get(classification, templates["good"])
        return random.choice(options)

    def _detect_move_tactic(self, board_before: chess.Board,
                            move: chess.Move,
                            board_after: chess.Board) -> Optional[str]:
        """Detect if a move executes a tactical motif."""
        piece = board_before.piece_at(move.from_square)
        if not piece:
            return None

        # Check for capture
        if board_before.is_capture(move):
            captured = board_before.piece_at(move.to_square)
            if captured:
                value_diff = (self.PIECE_VALUES.get(captured.piece_type, 0) -
                             self.PIECE_VALUES.get(piece.piece_type, 0))
                if value_diff > 2:
                    return f"Nice material gain! You captured a {chess.piece_name(captured.piece_type)} with your {chess.piece_name(piece.piece_type)}."
                elif value_diff < -2:
                    return f"You sacrificed your {chess.piece_name(piece.piece_type)} for a {chess.piece_name(captured.piece_type)}. Is this sacrifice sound?"

        # Check for check
        if board_after.is_check():
            return f"{board_before.san(move)} gives check! Keep the pressure on."

        # Check for fork after move
        if piece.piece_type == chess.KNIGHT:
            attacks = board_after.attacks(move.to_square)
            attacked_high_value = [
                sq for sq in attacks
                if board_after.piece_at(sq) and
                board_after.piece_at(sq).color != piece.color and
                self.PIECE_VALUES.get(board_after.piece_at(sq).piece_type, 0) >= 3
            ]
            if len(attacked_high_value) >= 2:
                return f"Fork! Your knight on {chess.square_name(move.to_square)} attacks multiple pieces simultaneously."

        return None

    def _comment_on_strategic_impact(self, board_before: chess.Board,
                                     move: chess.Move,
                                     board_after: chess.Board) -> Optional[str]:
        """Comment on the strategic significance of a move."""
        piece = board_before.piece_at(move.from_square)
        if not piece:
            return None

        # Castling
        if board_before.is_castling(move):
            return "Good — you've castled and secured your king. Now connect your rooks!"

        # Pawn to center
        to_file = chess.square_file(move.to_square)
        to_rank = chess.square_rank(move.to_square)
        if (piece.piece_type == chess.PAWN and
                2 <= to_file <= 5 and 2 <= to_rank <= 5 and
                board_before.fullmove_number <= 10):
            return "Occupying the center with your pawn — good opening principle!"

        # Piece to active square
        if piece.piece_type in (chess.KNIGHT, chess.BISHOP) and board_before.fullmove_number <= 12:
            center_dist = min(abs(to_file - 3.5), abs(to_file - 4.5)) + \
                         min(abs(to_rank - 3.5), abs(to_rank - 4.5))
            if center_dist <= 2:
                return f"Developing the {chess.piece_name(piece.piece_type)} to an active central square."

        return None

    def _generic_move_comment(self, board_before: chess.Board,
                              move: chess.Move,
                              board_after: chess.Board) -> str:
        """Fallback generic move comment."""
        phase = self._determine_game_phase(board_before)
        san = board_before.san(move)

        generics = {
            "opening": [
                f"{san} follows opening principles.",
                f"Continuing development with {san}.",
                f"{san} fights for central control.",
            ],
            "middlegame": [
                f"{san} improves piece coordination.",
                f"{san} creates new possibilities.",
                f"Interesting choice with {san}.",
            ],
            "endgame": [
                f"{san} improves your position.",
                f"Precise endgame technique with {san}.",
                f"{san} makes progress.",
            ]
        }

        return random.choice(generics.get(phase, generics["middlegame"]))

    # ─── Game Phase Detection ─────────────────────────────────────────────────

    def _determine_game_phase(self, board: chess.Board) -> str:
        """Determine if we're in the opening, middlegame, or endgame."""
        # Count material
        queens = sum(
            1 for sq in chess.SQUARES
            if board.piece_at(sq) and board.piece_at(sq).piece_type == chess.QUEEN
        )
        total_material = sum(
            self.PIECE_VALUES.get(board.piece_at(sq).piece_type, 0)
            for sq in chess.SQUARES
            if board.piece_at(sq) and board.piece_at(sq).piece_type != chess.KING
        )

        if board.fullmove_number <= 12 and total_material > 60:
            return "opening"
        elif queens == 0 or total_material < 20:
            return "endgame"
        else:
            return "middlegame"

    # ─── Utility Methods ──────────────────────────────────────────────────────

    def _count_material(self, board: chess.Board, color: chess.Color) -> int:
        """Count total material value for a side."""
        return sum(
            self.PIECE_VALUES.get(board.piece_at(sq).piece_type, 0)
            for sq in chess.SQUARES
            if board.piece_at(sq) and board.piece_at(sq).color == color
        )

    def _are_rooks_connected(self, board: chess.Board, color: chess.Color) -> bool:
        """Check if rooks are connected (no pieces between them on the back rank)."""
        back_rank = 0 if color == chess.WHITE else 7
        rook_files = []

        for file in range(8):
            sq = chess.square(file, back_rank)
            piece = board.piece_at(sq)
            if piece and piece.piece_type == chess.ROOK and piece.color == color:
                rook_files.append(file)

        if len(rook_files) < 2:
            return True  # Only one rook, considered "connected" for our purposes

        min_file, max_file = min(rook_files), max(rook_files)
        for file in range(min_file + 1, max_file):
            sq = chess.square(file, back_rank)
            if board.piece_at(sq):
                return False
        return True

    def explain_concept(self, concept: str) -> str:
        """
        Explain a chess concept in clear, educational language.
        Used for the interactive tutorial system.
        """
        concepts = {
            "fork": "A fork is a tactic where one piece attacks two or more enemy pieces simultaneously. Knights are especially good at forking because of their unusual movement.",
            "pin": "A pin is when a piece cannot move without exposing a more valuable piece behind it to attack. Absolute pins are against the king; relative pins target any valuable piece.",
            "skewer": "A skewer is like a reverse pin — a valuable piece is attacked and must move, exposing a less valuable piece behind it.",
            "discovered_attack": "A discovered attack occurs when a piece moves out of the way, revealing an attack by a piece behind it.",
            "back_rank": "The back rank is the first or eighth rank. A back rank checkmate occurs when the king is trapped behind its own pawns by a rook or queen.",
            "outpost": "An outpost is a square deep in the opponent's territory that cannot be attacked by enemy pawns. Knights love outposts!",
            "passed_pawn": "A passed pawn has no opposing pawns in front of it or on adjacent files. Passed pawns are powerful because they can potentially promote.",
            "isolated_pawn": "An isolated pawn has no friendly pawns on adjacent files to support it. It can become a target for the opponent.",
            "fianchetto": "A fianchetto is when a bishop is developed to the second rank on the b or g file, behind the b2/b7 or g2/g7 pawn.",
            "zugzwang": "Zugzwang is when any move made by a player worsens their position — they would prefer to 'pass.' Common in endgames.",
            "tempo": "Tempo refers to a move or 'turn.' Gaining tempo means forcing your opponent to waste moves on defense rather than development.",
            "prophylaxis": "Prophylaxis means preventing your opponent's plans before they can execute them. It's a key concept in positional chess.",
        }
        return concepts.get(concept, f"'{concept}' is an important chess concept worth studying further.")
