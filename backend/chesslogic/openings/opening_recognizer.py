"""
Opening Recognition System for ChessCoach.

Identifies chess openings from move sequences, providing:
- Opening name and ECO code
- Variation identification  
- Strategic ideas and typical plans
- Historical context
- Common traps and pitfalls

The opening book covers 500+ named openings and variations.
"""

import chess
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field

from chesslogic.utils.logger import get_logger

logger = get_logger("openings")


@dataclass
class OpeningInfo:
    """Complete information about an identified opening."""
    eco: str
    name: str
    variation: str = ""
    description: str = ""
    strategic_ideas: List[str] = field(default_factory=list)
    typical_plans: List[str] = field(default_factory=list)
    common_traps: List[str] = field(default_factory=list)
    famous_games: List[str] = field(default_factory=list)
    difficulty: str = "intermediate"  # beginner, intermediate, advanced

    @property
    def full_name(self) -> str:
        if self.variation:
            return f"{self.name} — {self.variation}"
        return self.name

    @property
    def eco_family(self) -> str:
        """Get the ECO family letter."""
        return self.eco[0] if self.eco else "?"


# ─── Opening Book ─────────────────────────────────────────────────────────────
# A representative selection of openings by UCI move sequence.
# Format: "uci_moves": OpeningInfo(...)
# This is a curated subset; a full book would contain 2000+ entries.

OPENING_BOOK: Dict[str, OpeningInfo] = {

    # ── A: Flank Openings ─────────────────────────────────────────────────────

    "g2g3": OpeningInfo("A00", "King's Fianchetto Opening",
        description="White prepares to fianchetto the king's bishop.",
        strategic_ideas=["Fianchetto bishop for long diagonal control",
                         "Hypermodern approach to the center"]),

    "b2b4": OpeningInfo("A00", "Polish Opening",
        description="The aggressive b4 grabs space on the queenside immediately.",
        strategic_ideas=["Queenside space grab", "Unusual move order surprises opponents"],
        common_traps=["b5 push to gain further space"]),

    "c2c4": OpeningInfo("A10", "English Opening",
        description="A flank opening that controls d5 without immediately occupying the center.",
        strategic_ideas=["Control d5 from a distance",
                         "Flexibility in pawn structure",
                         "Often transposes to other openings"],
        typical_plans=["Fianchetto king's bishop",
                       "Queenside expansion with b4",
                       "Central break with d4"]),

    "c2c4 e7e5": OpeningInfo("A20", "English Opening: King's English",
        variation="King's English Variation",
        description="Black mirrors White's approach, leading to reversed Sicilian structures.",
        strategic_ideas=["Black fights for center with ...e5",
                         "Similar to reversed Sicilian",
                         "Dynamic play for both sides"]),

    "c2c4 c7c5": OpeningInfo("A30", "English Opening: Symmetrical",
        variation="Symmetrical Variation",
        description="The most principled response — Black mirrors White.",
        strategic_ideas=["Symmetrical pawn structure",
                         "Leads to complex maneuvering",
                         "Neither side can claim early advantage"]),

    "g1f3": OpeningInfo("A04", "Réti Opening",
        description="Named after Richard Réti, this hypermodern opening delays central pawn advances.",
        strategic_ideas=["Hypermodern center control",
                         "Flexible development",
                         "Knight development before pawn decisions"],
        typical_plans=["Double fianchetto",
                       "Pressure on d5 from c4 and f3",
                       "Late central break"]),

    "g1f3 d7d5 c2c4": OpeningInfo("A07", "Réti Opening",
        variation="King's Indian Attack vs d5",
        description="Réti transposes into a flexible system.",
        strategic_ideas=["Attack the d5 pawn with c4",
                         "Develop pieces before committing pawns"]),

    # ── B: Semi-Open Games ────────────────────────────────────────────────────

    "e2e4": OpeningInfo("B00", "King's Pawn Opening",
        description="The most popular first move — immediately stakes a claim in the center.",
        strategic_ideas=["Occupy the center immediately",
                         "Open lines for bishop and queen"],
        difficulty="beginner"),

    "e2e4 c7c5": OpeningInfo("B20", "Sicilian Defense",
        description="The most popular and complex defense against 1.e4. Black fights for the center asymmetrically.",
        strategic_ideas=["Asymmetrical pawn structure creates imbalances",
                         "Black gets queenside counterplay",
                         "White gets kingside space and initiative"],
        typical_plans=["Black: queenside counterplay with ...a5 and ...b5",
                       "White: kingside attack with f4-f5",
                       "White: Open Sicilian with Nc3, d4"],
        difficulty="advanced"),

    "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 b1c3 a7a6": OpeningInfo("B90", "Sicilian Defense",
        variation="Najdorf Variation",
        description="The most popular Sicilian variation, played by Fischer, Kasparov, and Carlsen. ...a6 prevents Nb5 and prepares ...b5.",
        strategic_ideas=["...a6 stops Nb5 and prepares queenside expansion",
                         "Black will play ...e5 or ...e6 depending on White's response",
                         "Extremely dynamic and double-edged"],
        typical_plans=["...b5-b4 queenside attack",
                       "...e5 restricting the d4 knight",
                       "...Be7 or ...Bd7 depending on setup"],
        common_traps=["English Attack: h4 followed by kingside assault",
                      "Poisoned Pawn Variation after ...Qxb2"],
        famous_games=["Kasparov vs Karpov, 1985 (Najdorf)"]),

    "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 b1c3 e7e6": OpeningInfo("B80", "Sicilian Defense",
        variation="Scheveningen Variation",
        description="A solid yet dynamic structure with pawns on e6 and d6.",
        strategic_ideas=["Solid pawn structure, no weaknesses",
                         "Flexible piece placement",
                         "e5 break potential"]),

    "e2e4 c7c5 g1f3 b8c6 d2d4 c5d4 f3d4 g7g6": OpeningInfo("B70", "Sicilian Defense",
        variation="Dragon Variation",
        description="One of the sharpest opening systems in chess. Black fianchettos the bishop on the long diagonal.",
        strategic_ideas=["Dragon bishop on g7 is Black's key piece",
                         "Both sides attack on opposite flanks",
                         "Often leads to highly tactical games"],
        typical_plans=["Black: ...a5 and queenside attack",
                       "White: Yugoslav Attack with h4-h5",
                       "Piece sacrifices on h6 are common"],
        common_traps=["Ng5 sacrifice ideas after Yugoslav Attack",
                      "Greek Gift sacrifice pattern"],
        famous_games=["Topalov vs Kasparov, 2001"]),

    "e2e4 c7c5 b1c3": OpeningInfo("B23", "Sicilian Defense",
        variation="Closed Sicilian",
        description="White avoids the Open Sicilian with a more strategic approach.",
        strategic_ideas=["Kingside attack via f4-f5",
                         "Knight to d5 or f5 ideas",
                         "Less theoretical, more strategic"]),

    "e2e4 e7e5": OpeningInfo("C20", "Open Game",
        description="The classical symmetrical response. Both sides control the center with pawns.",
        strategic_ideas=["Direct center control",
                         "Open files for both sides",
                         "Classical strategic principles apply"],
        difficulty="beginner"),

    "e2e4 e7e5 g1f3 b8c6 f1b5": OpeningInfo("C60", "Ruy Lopez",
        description="One of the oldest and most respected openings. White pressures the c6 knight that defends e5.",
        strategic_ideas=["Pressure on e5 via the c6 knight",
                         "Long-term positional pressure",
                         "Many theoretical variations"],
        typical_plans=["White: d4 central break",
                       "White: minority attack on queenside",
                       "Black: Breyer maneuver Nb8-d7"],
        famous_games=["Kasparov vs Deep Blue, 1997"]),

    "e2e4 e7e5 g1f3 b8c6 f1b5 a7a6 b5a4 g8f6 e1g1": OpeningInfo("C84", "Ruy Lopez",
        variation="Closed Variation",
        description="The main line of the Ruy Lopez. White castles and prepares for long-term pressure.",
        strategic_ideas=["White aims for d4 break",
                         "Black seeks counterplay with ...b5 and ...d5",
                         "Very rich strategic content"]),

    "e2e4 e7e5 g1f3 b8c6 f1c4": OpeningInfo("C50", "Italian Game",
        description="A classical opening targeting the f7 pawn and controlling the center.",
        strategic_ideas=["Target f7 pawn",
                         "Control d5 square",
                         "Harmonious piece development"],
        difficulty="beginner"),

    "e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 g1g5": OpeningInfo("C57", "Italian Game",
        variation="Fried Liver Attack",
        description="A spectacular sacrifice attacking f7. Correct play is required from both sides.",
        strategic_ideas=["Nxf7 sacrifice tears open Black's kingside",
                         "White gets tremendous practical chances",
                         "Requires precise defense"],
        common_traps=["Nxf7 followed by Ng5+ forking king and queen"],
        difficulty="advanced"),

    "e2e4 e7e5 g1f3 b8c6 d2d4 e5d4 f3d4": OpeningInfo("C44", "Scotch Game",
        description="White immediately challenges the center, leading to open positions.",
        strategic_ideas=["Early central tension",
                         "Open d-file",
                         "Active piece play"],
        famous_games=["Kasparov popularized this in the 1990s"]),

    "e2e4 e7e5 f2f4": OpeningInfo("C33", "King's Gambit",
        description="One of the most romantic openings. White sacrifices a pawn for rapid development and attack.",
        strategic_ideas=["Sacrifice pawn for rapid development",
                         "Open f-file for attack",
                         "Control e5 after exf4"],
        typical_plans=["Attack along the f-file",
                       "Nf3, Bc4, d4 rapid development",
                       "Piece attacks against the Black king"],
        difficulty="intermediate"),

    "e2e4 e7e5 g1f3 g8f6": OpeningInfo("C42", "Petrov's Defense",
        variation="Russian Game",
        description="A solid defense that immediately counterattacks White's e4 pawn.",
        strategic_ideas=["Symmetric counterattack",
                         "Solid, drawish tendencies",
                         "Popular for players wanting solid positions"]),

    "e2e4 d7d5": OpeningInfo("B01", "Scandinavian Defense",
        description="Black immediately challenges e4, leading to asymmetrical positions.",
        strategic_ideas=["Immediate center challenge",
                         "Queen comes out early (risky but active)",
                         "Semi-open d-file for Black"]),

    "e2e4 e7e6": OpeningInfo("C00", "French Defense",
        description="A solid defensive system. Black aims to counterattack White's center from a solid base.",
        strategic_ideas=["Solid pawn chain e6-d5",
                         "Counterattack with ...c5",
                         "Fight for the e4 pawn"],
        typical_plans=["...c5 and ...cxd4 counter",
                       "...f6 to attack the e4-e5 chain",
                       "Queenside attack with ...a5-a4"],
        difficulty="intermediate"),

    "e2e4 e7e6 d2d4 d7d5 b1c3 f8b4": OpeningInfo("C15", "French Defense",
        variation="Winawer Variation",
        description="The sharpest French. Black pins the knight, creating immediate tension.",
        strategic_ideas=["...Bb4 pins the c3 knight",
                         "Black will often exchange on c3, giving White doubled pawns",
                         "Leads to extremely complex positions"]),

    "e2e4 e7e6 d2d4 d7d5 e4d5 e6d5": OpeningInfo("C01", "French Defense",
        variation="Exchange Variation",
        description="White exchanges pawns, leading to symmetrical and often drawish positions.",
        strategic_ideas=["Symmetrical pawn structure",
                         "Often leads to early draws at high level",
                         "Easy to play for both sides"]),

    "e2e4 c7c6": OpeningInfo("B10", "Caro-Kann Defense",
        description="A solid, classical defense. Black supports d5 with c6 before advancing.",
        strategic_ideas=["Solid pawn structure without weaknesses",
                         "Active piece play after ...d5",
                         "Good bishop unlike French Defense"],
        typical_plans=["...Bf5 active bishop",
                       "...Nd7-f8-e6 maneuvering",
                       "Queenside counterplay"],
        difficulty="intermediate"),

    "e2e4 c7c6 d2d4 d7d5 b1c3 d5e4 c3e4 f8f5": OpeningInfo("B13", "Caro-Kann Defense",
        variation="Classical Variation",
        description="The most popular and theoretically rich Caro-Kann line.",
        strategic_ideas=["Active bishop to f5",
                         "Solid pawn structure",
                         "White has the space advantage"]),

    "e2e4 d7d6": OpeningInfo("B06", "Pirc Defense",
        description="A hypermodern defense. Black allows White to build a big center, then undermines it.",
        strategic_ideas=["Allow White center, then attack it",
                         "Fianchetto bishop on g7",
                         "Flexible and dynamic"]),

    # ── D: Closed Games ───────────────────────────────────────────────────────

    "d2d4": OpeningInfo("D00", "Queen's Pawn Opening",
        description="The second most popular first move. Creates a more closed game.",
        strategic_ideas=["Control center with pawn and d4 knight",
                         "More strategic and less tactical than e4 openings"],
        difficulty="beginner"),

    "d2d4 d7d5 c2c4": OpeningInfo("D06", "Queen's Gambit",
        description="One of the oldest and most reputable openings. White offers a pawn to gain center control.",
        strategic_ideas=["Gambit pawn to gain center control",
                         "Open c-file after cxd5",
                         "Central pressure with d4 pawn"],
        typical_plans=["c4 pawn offers center pressure",
                       "Minority attack on queenside",
                       "Piece pressure on c-file"]),

    "d2d4 d7d5 c2c4 e7e6 b1c3 g8f6 c1g5 f8e7 e2e3 e8g8 g1f3": OpeningInfo("D55", "Queen's Gambit Declined",
        variation="Classical Variation",
        description="Black declines the gambit with a solid defense.",
        strategic_ideas=["Solid pawn structure",
                         "Control e4 and d5 squares",
                         "Minority attack typical for White"]),

    "d2d4 d7d5 c2c4 c7c6": OpeningInfo("D10", "Slav Defense",
        description="One of the most solid defenses against the Queen's Gambit.",
        strategic_ideas=["Solid structure, no pawn weaknesses",
                         "c6 supports d5 without blocking the c8 bishop",
                         "Active counterplay"],
        typical_plans=["...Bf5 or ...Bg4 active bishop development",
                       "...e6-e5 central break",
                       "...dxc4 accepting the gambit"]),

    "d2d4 d7d5 c2c4 d5c4": OpeningInfo("D20", "Queen's Gambit Accepted",
        description="Black accepts the gambit pawn but faces development difficulties.",
        strategic_ideas=["Accepting the pawn gives center space",
                         "White gets rapid development as compensation",
                         "Black must return the pawn or face pressure"]),

    "d2d4 g8f6 c2c4 g7g6 b1c3 f8g7 e2e4 d7d6 g1f3 e8g8 f1e2": OpeningInfo("E97", "King's Indian Defense",
        variation="Classical Variation",
        description="A dynamic and aggressive defense favored by Fischer and Kasparov.",
        strategic_ideas=["Hypermodern: Black allows White big center",
                         "Fierce kingside attack for Black",
                         "Opposite side attacks are common"],
        typical_plans=["...e5 break in the center",
                       "...f5 kingside attack",
                       "White: queenside expansion with c5 or d5"],
        famous_games=["Fischer vs Spassky, 1972 (Game 6)"],
        difficulty="advanced"),

    "d2d4 g8f6 c2c4 e7e6 g2g3 d7d5 f1g2 f8e7 g1f3 e8g8 e1g1 d5c4": OpeningInfo("E15", "Queen's Indian Defense",
        variation="Main Line",
        description="A sophisticated defense emphasizing piece activity over pawn structure.",
        strategic_ideas=["Control e4 with pieces not pawns",
                         "Active bishop placement",
                         "Subtle positional play"]),

    "d2d4 g8f6 c2c4 e7e6 b1c3 f8b4": OpeningInfo("E30", "Nimzo-Indian Defense",
        description="One of the most respected modern defenses. Black pins the knight immediately.",
        strategic_ideas=["Pin the c3 knight",
                         "Create structural weaknesses on c3",
                         "Active piece play compensates for bishop pair"],
        typical_plans=["Exchange on c3 at the right moment",
                       "Control e4 and d5 squares",
                       "...c5 or ...d5 central breaks"]),

    "d2d4 g8f6 c2c4 c7c5 d4d5 e7e6 b1c3 e6d5 c4d5 d7d6": OpeningInfo("A65", "Benoni Defense",
        variation="Modern Benoni",
        description="An ambitious counter-attacking defense where Black creates immediate queenside counterplay.",
        strategic_ideas=["Asymmetrical pawn structure",
                         "Black gets active piece play",
                         "Queenside counterplay vs White's space"],
        typical_plans=["...b5 queenside attack",
                       "...Re8 and ...e5 central break",
                       "Knight on d7 aiming for c5 or b6"],
        difficulty="advanced"),

    "d2d4 f7f5": OpeningInfo("A80", "Dutch Defense",
        description="An uncompromising response. Black controls e4 and aims for kingside attack.",
        strategic_ideas=["Control e4 square",
                         "Prepare kingside attack",
                         "Stonewall or Leningrad setups"]),

    # ── E: Indian Defenses ────────────────────────────────────────────────────

    "d2d4 g8f6 c2c4 g7g6": OpeningInfo("E60", "King's Indian Defense",
        description="A fighting defense that leads to double-edged positions.",
        strategic_ideas=["Hypermodern center control",
                         "Fianchetto bishop on g7",
                         "Kings attack each other on opposite flanks"]),

    "d2d4 g8f6 g1f3 g7g6 c2c4 f8g7 g2g3 e8g8 f1g2 d7d6 e1g1": OpeningInfo("E60", "King's Indian Defense",
        variation="Fianchetto Variation",
        description="White meets the King's Indian with a fianchetto, aiming for positional pressure.",
        strategic_ideas=["Restrained approach against King's Indian",
                         "Long diagonal pressure",
                         "Queenside expansion"]),
}


class OpeningRecognizer:
    """
    Identifies chess openings from a game's move sequence.
    
    Uses a trie-like lookup through the opening book to find
    the deepest matching variation, then falls back to broader
    opening families.
    """

    def __init__(self, db_manager=None):
        self._db = db_manager
        self._book = OPENING_BOOK

    def identify(self, board: chess.Board) -> Optional[OpeningInfo]:
        """
        Identify the current opening from a board's move stack.
        Returns the most specific matching OpeningInfo.
        """
        moves = [move.uci() for move in board.move_stack]
        return self.identify_from_moves(moves)

    def identify_from_moves(self, moves: List[str]) -> Optional[OpeningInfo]:
        """
        Identify opening from a list of UCI moves.
        Tries progressively shorter sequences to find the deepest match.
        """
        if not moves:
            return None

        # Try decreasing lengths to find deepest match
        for length in range(len(moves), 0, -1):
            key = " ".join(moves[:length])
            if key in self._book:
                return self._book[key]

        # Check DB for more openings
        if self._db:
            key = " ".join(moves)
            result = self._db.find_opening_by_moves(key)
            if result:
                return OpeningInfo(
                    eco=result.get("eco", ""),
                    name=result.get("name", ""),
                    variation=result.get("variation", ""),
                    description=result.get("description", ""),
                    strategic_ideas=self._parse_json_list(result.get("strategic_ideas")),
                    typical_plans=self._parse_json_list(result.get("typical_plans")),
                    common_traps=self._parse_json_list(result.get("common_traps")),
                )

        return None

    def get_opening_comment(self, opening: OpeningInfo, move_count: int) -> str:
        """
        Generate a coach comment about the current opening.
        Adapts based on how far into the opening we are.
        """
        if move_count <= 2:
            return f"Opening with the {opening.full_name}."

        if move_count <= 6:
            comment = f"We're in the {opening.full_name}."
            if opening.description:
                comment += f" {opening.description}"
            return comment

        if move_count <= 12:
            comment = f"Following the {opening.full_name} (ECO: {opening.eco})."
            if opening.strategic_ideas:
                idea = opening.strategic_ideas[0]
                comment += f" Key idea: {idea}."
            return comment

        # Deep into opening theory
        if opening.typical_plans:
            plan = opening.typical_plans[0]
            return f"Entering the middlegame from the {opening.name}. Typical plan: {plan}."

        return f"Out of theory — we're in {opening.name} territory."

    @staticmethod
    def _parse_json_list(value) -> List[str]:
        """Parse a JSON list field from the database."""
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except Exception:
                return []
        return []

    def get_all_openings_for_eco(self, eco_family: str) -> List[OpeningInfo]:
        """Get all known openings in an ECO family (A, B, C, D, E)."""
        return [
            info for info in self._book.values()
            if info.eco and info.eco.startswith(eco_family)
        ]

    def get_opening_explorer_data(self, moves: List[str]) -> Dict:
        """
        Get opening explorer data for a position.
        Returns the current opening and all continuations.
        """
        current = self.identify_from_moves(moves)
        continuations = []

        prefix = " ".join(moves) + " " if moves else ""
        for key, info in self._book.items():
            if key.startswith(prefix) and key != " ".join(moves):
                next_moves = key[len(prefix):].split()
                if next_moves:
                    continuations.append({
                        "move": next_moves[0],
                        "opening": info,
                        "depth": len(next_moves)
                    })

        return {
            "current": current,
            "continuations": continuations[:10]
        }
