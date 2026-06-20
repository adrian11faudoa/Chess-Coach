"""
Database Manager for ChessCoach.
Handles all SQLite operations for game history, puzzles, progress tracking.
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from chesslogic.utils.logger import get_logger

logger = get_logger("database")


class DatabaseManager:
    """
    Manages all persistence for ChessCoach.
    
    Tables:
    - games: Complete game records with PGN
    - game_moves: Individual move analysis data
    - positions: FEN positions with evaluations  
    - puzzles: Tactical puzzles
    - puzzle_attempts: User puzzle history
    - openings: Opening book data
    - user_stats: Aggregate player statistics
    - training_sessions: Training history
    """

    SCHEMA_VERSION = 3

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def initialize(self):
        """Initialize database, create tables if needed, run migrations."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._get_conn() as conn:
            self._create_tables(conn)
            self._run_migrations(conn)
        logger.info(f"Database initialized at {self.db_path}")

    @contextmanager
    def _get_conn(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _create_tables(self, conn: sqlite3.Connection):
        """Create all database tables."""
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                white_player TEXT DEFAULT 'Player',
                black_player TEXT DEFAULT 'Engine',
                white_elo INTEGER,
                black_elo INTEGER,
                result TEXT,
                time_control TEXT,
                opening_eco TEXT,
                opening_name TEXT,
                pgn TEXT NOT NULL,
                final_fen TEXT,
                accuracy_white REAL,
                accuracy_black REAL,
                blunders_white INTEGER DEFAULT 0,
                blunders_black INTEGER DEFAULT 0,
                mistakes_white INTEGER DEFAULT 0,
                mistakes_black INTEGER DEFAULT 0,
                inaccuracies_white INTEGER DEFAULT 0,
                inaccuracies_black INTEGER DEFAULT 0,
                game_mode TEXT DEFAULT 'vs_engine',
                notes TEXT,
                tags TEXT DEFAULT '[]',
                analyzed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS game_moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                move_number INTEGER NOT NULL,
                color TEXT NOT NULL,
                uci_move TEXT NOT NULL,
                san_move TEXT NOT NULL,
                fen_before TEXT,
                fen_after TEXT,
                evaluation REAL,
                best_move TEXT,
                best_eval REAL,
                move_accuracy REAL,
                classification TEXT,
                engine_comment TEXT,
                tactical_motifs TEXT DEFAULT '[]',
                time_spent INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fen TEXT UNIQUE NOT NULL,
                evaluation REAL,
                best_move TEXT,
                depth INTEGER,
                lines TEXT DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS puzzles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                puzzle_id TEXT UNIQUE,
                fen TEXT NOT NULL,
                moves TEXT NOT NULL,
                rating INTEGER,
                rating_deviation INTEGER DEFAULT 100,
                themes TEXT DEFAULT '[]',
                opening_tags TEXT DEFAULT '[]',
                game_url TEXT,
                difficulty TEXT DEFAULT 'medium'
            );

            CREATE TABLE IF NOT EXISTS puzzle_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                puzzle_id INTEGER REFERENCES puzzles(id),
                solved INTEGER NOT NULL,
                time_seconds INTEGER,
                rating_before INTEGER,
                rating_after INTEGER,
                attempted_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stat_date TEXT NOT NULL,
                games_played INTEGER DEFAULT 0,
                games_won INTEGER DEFAULT 0,
                games_drawn INTEGER DEFAULT 0,
                games_lost INTEGER DEFAULT 0,
                puzzles_solved INTEGER DEFAULT 0,
                puzzles_attempted INTEGER DEFAULT 0,
                avg_accuracy REAL,
                time_played_seconds INTEGER DEFAULT 0,
                estimated_elo INTEGER DEFAULT 1200
            );

            CREATE TABLE IF NOT EXISTS openings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                eco TEXT NOT NULL,
                name TEXT NOT NULL,
                variation TEXT,
                pgn TEXT,
                fen TEXT,
                moves_uci TEXT,
                description TEXT,
                strategic_ideas TEXT,
                typical_plans TEXT,
                common_traps TEXT
            );

            CREATE TABLE IF NOT EXISTS training_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_type TEXT NOT NULL,
                duration_seconds INTEGER,
                items_completed INTEGER DEFAULT 0,
                score REAL,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS annotations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER REFERENCES games(id) ON DELETE CASCADE,
                move_number INTEGER,
                color TEXT,
                arrow_from TEXT,
                arrow_to TEXT,
                highlight_square TEXT,
                highlight_color TEXT,
                comment TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_games_date ON games(date);
            CREATE INDEX IF NOT EXISTS idx_games_opening ON games(opening_eco);
            CREATE INDEX IF NOT EXISTS idx_game_moves_game ON game_moves(game_id);
            CREATE INDEX IF NOT EXISTS idx_positions_fen ON positions(fen);
            CREATE INDEX IF NOT EXISTS idx_puzzles_rating ON puzzles(rating);
            CREATE INDEX IF NOT EXISTS idx_puzzle_attempts_puzzle ON puzzle_attempts(puzzle_id);
        """)

    def _run_migrations(self, conn: sqlite3.Connection):
        """Run any needed schema migrations."""
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        current = row["version"] if row else 0

        if current < self.SCHEMA_VERSION:
            conn.execute("DELETE FROM schema_version")
            conn.execute("INSERT INTO schema_version VALUES (?)", (self.SCHEMA_VERSION,))

    # ─── Game Operations ─────────────────────────────────────────────────────

    def save_game(self, game_data: Dict[str, Any]) -> int:
        """Save a completed game and return its ID."""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO games (
                    date, white_player, black_player, white_elo, black_elo,
                    result, time_control, opening_eco, opening_name, pgn,
                    final_fen, accuracy_white, accuracy_black,
                    blunders_white, blunders_black, mistakes_white, mistakes_black,
                    inaccuracies_white, inaccuracies_black, game_mode, notes, tags
                ) VALUES (
                    :date, :white_player, :black_player, :white_elo, :black_elo,
                    :result, :time_control, :opening_eco, :opening_name, :pgn,
                    :final_fen, :accuracy_white, :accuracy_black,
                    :blunders_white, :blunders_black, :mistakes_white, :mistakes_black,
                    :inaccuracies_white, :inaccuracies_black, :game_mode, :notes, :tags
                )
            """, game_data)
            return cursor.lastrowid

    def save_game_moves(self, game_id: int, moves: List[Dict[str, Any]]):
        """Save analyzed moves for a game."""
        with self._get_conn() as conn:
            for move in moves:
                move["game_id"] = game_id
                conn.execute("""
                    INSERT INTO game_moves (
                        game_id, move_number, color, uci_move, san_move,
                        fen_before, fen_after, evaluation, best_move, best_eval,
                        move_accuracy, classification, engine_comment,
                        tactical_motifs, time_spent
                    ) VALUES (
                        :game_id, :move_number, :color, :uci_move, :san_move,
                        :fen_before, :fen_after, :evaluation, :best_move, :best_eval,
                        :move_accuracy, :classification, :engine_comment,
                        :tactical_motifs, :time_spent
                    )
                """, move)

    def get_games(self, limit: int = 50, offset: int = 0,
                  mode: Optional[str] = None) -> List[Dict]:
        """Retrieve game history."""
        with self._get_conn() as conn:
            query = "SELECT * FROM games"
            params = []
            if mode:
                query += " WHERE game_mode = ?"
                params.append(mode)
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_game(self, game_id: int) -> Optional[Dict]:
        """Get a single game by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM games WHERE id = ?", (game_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_game_moves(self, game_id: int) -> List[Dict]:
        """Get all analyzed moves for a game."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM game_moves WHERE game_id = ? ORDER BY move_number, color",
                (game_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_game_analyzed(self, game_id: int):
        """Mark a game as analyzed."""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE games SET analyzed = 1 WHERE id = ?", (game_id,)
            )

    # ─── Position Cache ───────────────────────────────────────────────────────

    def cache_position(self, fen: str, evaluation: float, best_move: str,
                       depth: int, lines: List):
        """Cache engine evaluation for a position."""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO positions (fen, evaluation, best_move, depth, lines)
                VALUES (?, ?, ?, ?, ?)
            """, (fen, evaluation, best_move, depth, json.dumps(lines)))

    def get_cached_position(self, fen: str, min_depth: int = 15) -> Optional[Dict]:
        """Retrieve cached position evaluation."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM positions WHERE fen = ? AND depth >= ?",
                (fen, min_depth)
            ).fetchone()
            return dict(row) if row else None

    # ─── Puzzle Operations ────────────────────────────────────────────────────

    def add_puzzles(self, puzzles: List[Dict]):
        """Bulk insert puzzles into the database."""
        with self._get_conn() as conn:
            for p in puzzles:
                conn.execute("""
                    INSERT OR IGNORE INTO puzzles
                    (puzzle_id, fen, moves, rating, themes, opening_tags, difficulty)
                    VALUES (:puzzle_id, :fen, :moves, :rating, :themes, :opening_tags, :difficulty)
                """, p)

    def get_puzzle(self, rating_target: int = 1500,
                   themes: Optional[List[str]] = None) -> Optional[Dict]:
        """Get a puzzle matching the given criteria."""
        with self._get_conn() as conn:
            query = """
                SELECT * FROM puzzles
                WHERE rating BETWEEN ? AND ?
                ORDER BY RANDOM() LIMIT 1
            """
            row = conn.execute(
                query, (rating_target - 200, rating_target + 200)
            ).fetchone()
            return dict(row) if row else None

    def record_puzzle_attempt(self, puzzle_id: int, solved: bool,
                               time_seconds: int, rating_before: int,
                               rating_after: int):
        """Record a puzzle attempt."""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO puzzle_attempts
                (puzzle_id, solved, time_seconds, rating_before, rating_after)
                VALUES (?, ?, ?, ?, ?)
            """, (puzzle_id, int(solved), time_seconds, rating_before, rating_after))

    # ─── Statistics ───────────────────────────────────────────────────────────

    def get_player_stats(self) -> Dict:
        """Get aggregate player statistics."""
        with self._get_conn() as conn:
            games = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN result = '1-0' AND white_player = 'Player' THEN 1
                             WHEN result = '0-1' AND black_player = 'Player' THEN 1
                             ELSE 0 END) as wins,
                    SUM(CASE WHEN result = '1/2-1/2' THEN 1 ELSE 0 END) as draws,
                    AVG(accuracy_white) as avg_accuracy,
                    AVG(blunders_white + blunders_black) as avg_blunders
                FROM games
            """).fetchone()

            puzzles = conn.execute("""
                SELECT
                    COUNT(*) as attempted,
                    SUM(solved) as solved,
                    AVG(CASE WHEN solved = 1 THEN time_seconds END) as avg_time
                FROM puzzle_attempts
            """).fetchone()

            return {
                "games": dict(games) if games else {},
                "puzzles": dict(puzzles) if puzzles else {},
            }

    def get_opening_stats(self) -> List[Dict]:
        """Get performance statistics per opening."""
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT
                    opening_eco,
                    opening_name,
                    COUNT(*) as games,
                    AVG(accuracy_white) as avg_accuracy,
                    SUM(CASE WHEN result = '1-0' AND white_player = 'Player' THEN 1
                             WHEN result = '0-1' AND black_player = 'Player' THEN 1
                             ELSE 0 END) as wins
                FROM games
                WHERE opening_eco IS NOT NULL
                GROUP BY opening_eco
                ORDER BY games DESC
                LIMIT 20
            """).fetchall()
            return [dict(row) for row in rows]

    # ─── Opening Database ─────────────────────────────────────────────────────

    def add_opening(self, opening: Dict):
        """Add an opening to the database."""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO openings
                (eco, name, variation, pgn, fen, moves_uci,
                 description, strategic_ideas, typical_plans, common_traps)
                VALUES
                (:eco, :name, :variation, :pgn, :fen, :moves_uci,
                 :description, :strategic_ideas, :typical_plans, :common_traps)
            """, opening)

    def find_opening_by_moves(self, moves_uci: str) -> Optional[Dict]:
        """Find an opening matching a sequence of UCI moves."""
        with self._get_conn() as conn:
            # Try exact match first
            row = conn.execute(
                "SELECT * FROM openings WHERE moves_uci = ? LIMIT 1",
                (moves_uci,)
            ).fetchone()
            if row:
                return dict(row)

            # Try prefix match (position is within a known opening)
            rows = conn.execute(
                "SELECT * FROM openings WHERE ? LIKE moves_uci || '%' ORDER BY LENGTH(moves_uci) DESC LIMIT 1",
                (moves_uci,)
            ).fetchone()
            return dict(rows) if rows else None

    def get_opening_by_eco(self, eco: str) -> Optional[Dict]:
        """Get opening details by ECO code."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM openings WHERE eco = ? LIMIT 1", (eco,)
            ).fetchone()
            return dict(row) if row else None

    # ─── Annotations ─────────────────────────────────────────────────────────

    def save_annotation(self, annotation: Dict) -> int:
        """Save a board annotation (arrow, highlight, comment)."""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO annotations
                (game_id, move_number, color, arrow_from, arrow_to,
                 highlight_square, highlight_color, comment)
                VALUES
                (:game_id, :move_number, :color, :arrow_from, :arrow_to,
                 :highlight_square, :highlight_color, :comment)
            """, annotation)
            return cursor.lastrowid

    def get_annotations(self, game_id: int) -> List[Dict]:
        """Get all annotations for a game."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM annotations WHERE game_id = ? ORDER BY move_number",
                (game_id,)
            ).fetchall()
            return [dict(row) for row in rows]
