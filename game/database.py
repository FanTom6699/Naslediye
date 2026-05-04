from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from game.buildings import BUILDINGS_ORDER


class GameDatabase:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(Path(db_path))
        self.conn.row_factory = sqlite3.Row

    def init(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                wood INTEGER NOT NULL,
                stone INTEGER NOT NULL,
                iron INTEGER NOT NULL,
                food INTEGER NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS buildings (
                user_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                level INTEGER NOT NULL,
                upgrade_end_ts INTEGER,
                PRIMARY KEY (user_id, code),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def ensure_player(self, user_id: int) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO users (user_id, wood, stone, iron, food)
            VALUES (?, 2500, 2500, 2500, 2500)
            """,
            (user_id,),
        )
        for code in BUILDINGS_ORDER:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO buildings (user_id, code, level, upgrade_end_ts)
                VALUES (?, ?, 1, NULL)
                """,
                (user_id, code),
            )
        self.conn.commit()

    def get_resources(self, user_id: int) -> dict[str, int]:
        row = self.conn.execute(
            "SELECT wood, stone, iron, food FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise ValueError("Player not found")
        return {
            "wood": row["wood"],
            "stone": row["stone"],
            "iron": row["iron"],
            "food": row["food"],
        }

    def get_buildings(self, user_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT code, level, upgrade_end_ts
            FROM buildings
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_building(self, user_id: int, code: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT code, level, upgrade_end_ts
            FROM buildings
            WHERE user_id = ? AND code = ?
            """,
            (user_id, code),
        ).fetchone()
        return dict(row) if row else None

    def complete_upgrade(self, user_id: int, code: str, new_level: int) -> None:
        self.conn.execute(
            """
            UPDATE buildings
            SET level = ?, upgrade_end_ts = NULL
            WHERE user_id = ? AND code = ?
            """,
            (new_level, user_id, code),
        )
        self.conn.commit()

    def users_with_due_upgrades(self, now_ts: int) -> list[int]:
        rows = self.conn.execute(
            """
            SELECT DISTINCT user_id
            FROM buildings
            WHERE upgrade_end_ts IS NOT NULL AND upgrade_end_ts <= ?
            """,
            (now_ts,),
        ).fetchall()
        return [int(row["user_id"]) for row in rows]

    def try_start_upgrade(
        self,
        user_id: int,
        code: str,
        cost: dict[str, int],
        finish_ts: int,
    ) -> bool:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            resources_updated = self.conn.execute(
                """
                UPDATE users
                SET wood = wood - ?, stone = stone - ?, iron = iron - ?, food = food - ?
                WHERE user_id = ?
                  AND wood >= ?
                  AND stone >= ?
                  AND iron >= ?
                  AND food >= ?
                """,
                (
                    cost["wood"],
                    cost["stone"],
                    cost["iron"],
                    cost["food"],
                    user_id,
                    cost["wood"],
                    cost["stone"],
                    cost["iron"],
                    cost["food"],
                ),
            ).rowcount

            if resources_updated == 0:
                self.conn.execute("ROLLBACK")
                return False

            upgraded = self.conn.execute(
                """
                UPDATE buildings
                SET upgrade_end_ts = ?
                WHERE user_id = ? AND code = ? AND upgrade_end_ts IS NULL
                """,
                (finish_ts, user_id, code),
            ).rowcount

            if upgraded == 0:
                self.conn.execute("ROLLBACK")
                return False

            self.conn.execute("COMMIT")
            return True
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
