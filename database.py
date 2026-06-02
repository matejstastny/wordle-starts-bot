import sqlite3
from datetime import date

DB_FILE = "wordle.db"


def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id   TEXT NOT NULL,
                player_name TEXT NOT NULL,
                guesses     INTEGER NOT NULL,
                game_date   TEXT NOT NULL,
                year_month  TEXT NOT NULL,
                UNIQUE(player_id, game_date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS posted_months (
                year_month TEXT PRIMARY KEY
            )
        """)


def add_score(player_id: str, player_name: str, guesses: int, game_date: date) -> bool:
    """Insert a score. Returns False if already recorded (duplicate ignored)."""
    year_month = game_date.strftime("%Y-%m")
    with sqlite3.connect(DB_FILE) as conn:
        try:
            conn.execute(
                "INSERT INTO scores (player_id, player_name, guesses, game_date, year_month) VALUES (?, ?, ?, ?, ?)",
                (player_id, player_name, guesses, game_date.isoformat(), year_month),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def get_leaderboard(year_month: str, min_games: int = 5, top_n: int = 7) -> list:
    """Return top_n players for year_month sorted by lowest average guesses."""
    with sqlite3.connect(DB_FILE) as conn:
        return conn.execute(
            """
            SELECT player_name, ROUND(AVG(guesses), 2), COUNT(*)
            FROM scores
            WHERE year_month = ?
            GROUP BY player_id
            HAVING COUNT(*) >= ?
            ORDER BY AVG(guesses) ASC
            LIMIT ?
            """,
            (year_month, min_games, top_n),
        ).fetchall()


def has_been_posted(year_month: str) -> bool:
    with sqlite3.connect(DB_FILE) as conn:
        return conn.execute(
            "SELECT 1 FROM posted_months WHERE year_month = ?", (year_month,)
        ).fetchone() is not None


def mark_posted(year_month: str):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO posted_months (year_month) VALUES (?)", (year_month,)
        )
