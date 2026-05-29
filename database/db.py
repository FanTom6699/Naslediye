from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, db_path: str) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def init(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                created_at INTEGER NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL DEFAULT 'TRADINGVIEW',
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                strength REAL NOT NULL,
                reasons TEXT NOT NULL,
                entry_price REAL NOT NULL,
                close_price REAL,
                status TEXT,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                closed_at INTEGER
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_rejections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair TEXT NOT NULL,
                direction TEXT NOT NULL,
                strength REAL NOT NULL,
                reason TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                chat_id INTEGER PRIMARY KEY,
                is_enabled INTEGER NOT NULL DEFAULT 1,
                min_strength REAL,
                pairs_csv TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )

        columns = self.conn.execute("PRAGMA table_info(signals)").fetchall()
        names = {str(row["name"]) for row in columns}
        if "source" not in names:
            self.conn.execute("ALTER TABLE signals ADD COLUMN source TEXT NOT NULL DEFAULT 'TRADINGVIEW'")

        self.conn.commit()

    def ping(self) -> bool:
        try:
            self.conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def close(self) -> None:
        self.conn.close()

    def add_subscriber(self, chat_id: int) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO subscribers(chat_id, created_at) VALUES(?, ?)",
            (chat_id, int(time.time())),
        )
        self.conn.execute(
            """
            INSERT OR IGNORE INTO user_settings(chat_id, is_enabled, min_strength, pairs_csv, created_at, updated_at)
            VALUES(?, 1, NULL, NULL, ?, ?)
            """,
            (chat_id, int(time.time()), int(time.time())),
        )
        self.conn.commit()

    def remove_subscriber(self, chat_id: int) -> None:
        self.conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))
        self.conn.commit()

    def get_subscribers(self) -> list[int]:
        rows = self.conn.execute("SELECT chat_id FROM subscribers").fetchall()
        return [int(row["chat_id"]) for row in rows]

    def get_user_settings(self, chat_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM user_settings WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        return dict(row) if row else None

    def set_user_settings(self, chat_id: int, *, is_enabled: bool, min_strength: float | None, pairs_csv: str | None) -> None:
        now = int(time.time())
        self.conn.execute(
            """
            INSERT INTO user_settings(chat_id, is_enabled, min_strength, pairs_csv, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                is_enabled = excluded.is_enabled,
                min_strength = excluded.min_strength,
                pairs_csv = excluded.pairs_csv,
                updated_at = excluded.updated_at
            """,
            (chat_id, 1 if is_enabled else 0, min_strength, pairs_csv, now, now),
        )
        self.conn.commit()

    def insert_signal(
        self,
        source: str,
        symbol: str,
        direction: str,
        strength: float,
        reasons: str,
        entry_price: float,
        expires_at: int,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO signals(source, symbol, direction, strength, reasons, entry_price, created_at, expires_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (source, symbol, direction, strength, reasons, entry_price, int(time.time()), expires_at),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def get_signal(self, signal_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM signals WHERE id = ?",
            (signal_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_last_signals(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_active_signal(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM signals
            WHERE status IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None

    def get_last_signal_time(self, symbol: str, direction: str) -> int | None:
        row = self.conn.execute(
            """
            SELECT created_at
            FROM signals
            WHERE symbol = ? AND direction = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (symbol, direction),
        ).fetchone()
        if row is None:
            return None
        return int(row["created_at"])

    def insert_rejection(self, pair: str, direction: str, strength: float, reason: str, details: str) -> None:
        self.conn.execute(
            """
            INSERT INTO signal_rejections(pair, direction, strength, reason, details, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (pair, direction, strength, reason, details, int(time.time())),
        )
        self.conn.commit()

    def get_last_rejections(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM signal_rejections
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def close_signal(self, signal_id: int, close_price: float, status: str) -> None:
        self.conn.execute(
            """
            UPDATE signals
            SET close_price = ?, status = ?, closed_at = ?
            WHERE id = ?
            """,
            (close_price, status, int(time.time()), signal_id),
        )
        self.conn.commit()

    def stats_summary(self) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'WIN' THEN 1 ELSE 0 END) AS win,
                SUM(CASE WHEN status = 'LOSS' THEN 1 ELSE 0 END) AS loss,
                SUM(CASE WHEN status = 'DRAW' THEN 1 ELSE 0 END) AS draw,
                AVG(CASE WHEN status = 'WIN' THEN strength END) AS avg_win_strength,
                AVG(CASE WHEN status = 'LOSS' THEN strength END) AS avg_loss_strength
            FROM signals
            """
        ).fetchone()

        total = int(row["total"] or 0)
        win = int(row["win"] or 0)
        loss = int(row["loss"] or 0)
        draw = int(row["draw"] or 0)
        winrate = (win / total * 100.0) if total else 0.0

        return {
            "total": total,
            "win": win,
            "loss": loss,
            "draw": draw,
            "winrate": winrate,
            "avg_win_strength": float(row["avg_win_strength"] or 0.0),
            "avg_loss_strength": float(row["avg_loss_strength"] or 0.0),
        }

    def stats_by_pair(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                symbol,
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'WIN' THEN 1 ELSE 0 END) AS win,
                SUM(CASE WHEN status = 'LOSS' THEN 1 ELSE 0 END) AS loss,
                SUM(CASE WHEN status = 'DRAW' THEN 1 ELSE 0 END) AS draw,
                AVG(strength) AS avg_strength
            FROM signals
            GROUP BY symbol
            ORDER BY total DESC, symbol ASC
            """
        ).fetchall()

        out: list[dict[str, Any]] = []
        for row in rows:
            total = int(row["total"] or 0)
            win = int(row["win"] or 0)
            out.append(
                {
                    "symbol": str(row["symbol"]),
                    "total": total,
                    "win": win,
                    "loss": int(row["loss"] or 0),
                    "draw": int(row["draw"] or 0),
                    "winrate": (win / total * 100.0) if total else 0.0,
                    "avg_strength": float(row["avg_strength"] or 0.0),
                }
            )
        return out

    def pair_leaderboard(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                symbol,
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'WIN' THEN 1 ELSE 0 END) AS win,
                SUM(CASE WHEN status = 'LOSS' THEN 1 ELSE 0 END) AS loss,
                SUM(CASE WHEN status = 'DRAW' THEN 1 ELSE 0 END) AS draw,
                AVG(strength) AS avg_strength
            FROM signals
            GROUP BY symbol
            ORDER BY
                CASE WHEN COUNT(*) > 0
                    THEN CAST(SUM(CASE WHEN status = 'WIN' THEN 1 ELSE 0 END) AS REAL) / COUNT(*)
                    ELSE 0 END DESC,
                AVG(strength) DESC,
                COUNT(*) DESC,
                symbol ASC
            """
        ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            total = int(row["total"] or 0)
            win = int(row["win"] or 0)
            result.append(
                {
                    "symbol": str(row["symbol"]),
                    "total": total,
                    "win": win,
                    "loss": int(row["loss"] or 0),
                    "draw": int(row["draw"] or 0),
                    "winrate": (win / total * 100.0) if total else 0.0,
                    "avg_strength": float(row["avg_strength"] or 0.0),
                }
            )
        return result
