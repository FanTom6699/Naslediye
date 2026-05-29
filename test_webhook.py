from __future__ import annotations

import argparse
import asyncio
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp


@dataclass
class TestConfig:
    base_url: str
    db_path: Path
    batch_window: int
    expiration_seconds: int
    pair_primary: str


class TestRunner:
    def __init__(self, cfg: TestConfig) -> None:
        self.cfg = cfg
        self.failures: list[str] = []

    async def run(self) -> int:
        self._print("Starting webhook e2e tests")
        self._print(f"Endpoint: {self.cfg.base_url}/webhook")
        self._print(f"DB: {self.cfg.db_path}")

        if not self.cfg.db_path.exists():
            self.failures.append(f"DB not found: {self.cfg.db_path}")
            self._report()
            return 1

        self._truncate_tables()
        await self.test_health()

        await self.test_single_long()
        await self.test_batching_best_only()
        await self.test_active_signal_lock()
        await self.test_low_strength()
        await self.test_cooldown_duplicate()
        await self.test_single_short()
        await self.test_outside_active_hours_soft_check()
        await self.test_result_win_loss_draw()
        self.test_command_texts_smoke()

        self._report()
        return 1 if self.failures else 0

    async def post_webhook(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | str]:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{self.cfg.base_url}/webhook", json=payload) as resp:
                try:
                    body: dict[str, Any] | str = await resp.json()
                except Exception:
                    body = await resp.text()
                return resp.status, body

    async def get_health(self) -> tuple[int, dict[str, Any] | str]:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{self.cfg.base_url}/health") as resp:
                try:
                    body: dict[str, Any] | str = await resp.json()
                except Exception:
                    body = await resp.text()
                return resp.status, body

    def _truncate_tables(self) -> None:
        with sqlite3.connect(self.cfg.db_path) as conn:
            conn.execute("DELETE FROM signals")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='signals'")
            conn.execute("DELETE FROM signal_rejections")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='signal_rejections'")
            conn.commit()

    def _fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with sqlite3.connect(self.cfg.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(sql, params).fetchone()

    def _fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with sqlite3.connect(self.cfg.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(sql, params).fetchall()

    async def _wait_for_batch(self) -> None:
        await asyncio.sleep(self.cfg.batch_window + 1)

    async def _wait_for_expire(self) -> None:
        await asyncio.sleep(self.cfg.expiration_seconds + 2)

    async def test_single_long(self) -> None:
        ts0 = int(time.time())
        status, body = await self.post_webhook(
            {
                "pair": self.cfg.pair_primary,
                "direction": "UP",
                "price": "1.2000",
                "strength": "9",
                "time": str(int(time.time())),
            }
        )
        if status != 200:
            self.failures.append(f"single LONG failed: http={status}, body={body}")
            return

        await self._wait_for_batch()
        row = self._fetchone(
            """
            SELECT symbol, direction
            FROM signals
            WHERE symbol = ? AND direction = 'LONG' AND created_at >= ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (self.cfg.pair_primary, ts0),
        )
        if row is None:
            self.failures.append("single LONG not inserted into signals")
            return

        if row["direction"] != "LONG":
            self.failures.append(f"single LONG wrong direction: {dict(row)}")

    async def test_health(self) -> None:
        status, body = await self.get_health()
        if status != 200:
            self.failures.append(f"/health failed: {status} {body}")
            return
        if not isinstance(body, dict):
            self.failures.append(f"/health response is not json: {body}")
            return

        required = {"webhook_status", "database_status", "websocket_status", "bot_status"}
        missing = [item for item in required if item not in body]
        if missing:
            self.failures.append(f"/health missing fields: {missing}")

    async def test_batching_best_only(self) -> None:
        await self._wait_for_expire()
        ts0 = int(time.time())

        payloads = [
            {"pair": "AUDUSD", "direction": "UP", "price": "0.6600", "strength": "7", "time": str(int(time.time()))},
            {"pair": "GBPUSD", "direction": "UP", "price": "1.2500", "strength": "9", "time": str(int(time.time()))},
            {"pair": "EURJPY", "direction": "UP", "price": "168.1000", "strength": "6", "time": str(int(time.time()))},
        ]

        await asyncio.gather(*(self.post_webhook(payload) for payload in payloads))
        await self._wait_for_batch()

        selected = self._fetchall(
            """
            SELECT symbol, strength
            FROM signals
            WHERE created_at >= ? AND symbol IN ('AUDUSD', 'GBPUSD', 'EURJPY')
            ORDER BY id ASC
            """,
            (ts0,),
        )
        if not selected:
            self.failures.append("batching produced no signal")
            return

        if len(selected) != 1:
            self.failures.append(f"batching inserted {len(selected)} signals instead of 1")
            return

        if selected[0]["symbol"] != "GBPUSD":
            self.failures.append(f"batching winner is not GBPUSD: {dict(selected[0])}")

        lost_rows = self._fetchall(
            """
            SELECT pair, reason
            FROM signal_rejections
            WHERE reason = 'batch_lost' AND created_at >= ?
            ORDER BY id DESC
            LIMIT 10
            """,
            (ts0,),
        )
        if len(lost_rows) < 2:
            self.failures.append("batch_lost rejections not recorded for non-winning signals")

    async def test_active_signal_lock(self) -> None:
        status, body = await self.post_webhook(
            {
                "pair": "EURJPY",
                "direction": "UP",
                "price": "168.200",
                "strength": "9",
                "time": str(int(time.time())),
            }
        )
        if status != 200:
            self.failures.append(f"active lock setup failed: {status} {body}")
            return

        await asyncio.sleep(0.3)
        status2, body2 = await self.post_webhook(
            {
                "pair": "AUDUSD",
                "direction": "DOWN",
                "price": "0.6600",
                "strength": "9",
                "time": str(int(time.time())),
            }
        )
        if status2 != 200:
            self.failures.append(f"active lock second webhook failed transport: {status2} {body2}")

        if not isinstance(body2, dict) or body2.get("reason") != "active_signal_exists":
            self.failures.append(f"active_signal_exists not returned: {body2}")

        row = self._fetchone(
            "SELECT reason FROM signal_rejections WHERE reason = 'active_signal_exists' ORDER BY id DESC LIMIT 1"
        )
        if row is None:
            self.failures.append("active_signal_exists was not logged in signal_rejections")

        await self._wait_for_expire()

    async def test_low_strength(self) -> None:
        status, body = await self.post_webhook(
            {
                "pair": "EURUSD",
                "direction": "UP",
                "price": "1.1010",
                "strength": "1",
                "time": str(int(time.time())),
            }
        )
        if status != 200:
            self.failures.append(f"low-strength transport failed: {status} {body}")
            return

        if not isinstance(body, dict) or body.get("accepted") is not False:
            self.failures.append(f"low-strength signal unexpectedly accepted: {body}")

    async def test_cooldown_duplicate(self) -> None:
        first = {
            "pair": "EURUSD",
            "direction": "UP",
            "price": "1.2050",
            "strength": "9",
            "time": str(int(time.time())),
        }
        status, _ = await self.post_webhook(first)
        if status != 200:
            self.failures.append("cooldown first signal post failed")
            return

        await self._wait_for_batch()
        await self._wait_for_expire()

        status2, body2 = await self.post_webhook(first)
        if status2 != 200:
            self.failures.append(f"cooldown second signal transport failed: {status2} {body2}")
            return

        if not isinstance(body2, dict) or not str(body2.get("reason", "")).startswith("cooldown"):
            self.failures.append(f"cooldown reason not returned: {body2}")

    async def test_single_short(self) -> None:
        await self._wait_for_expire()
        ts0 = int(time.time())
        status, body = await self.post_webhook(
            {
                "pair": "BTCUSD",
                "direction": "DOWN",
                "price": "70100",
                "strength": "9",
                "time": str(int(time.time())),
            }
        )
        if status != 200:
            self.failures.append(f"single SHORT failed: {status} {body}")
            return

        await self._wait_for_batch()
        row = self._fetchone(
            """
            SELECT direction
            FROM signals
            WHERE symbol = 'BTCUSD' AND direction = 'SHORT' AND created_at >= ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (ts0,),
        )
        if row is None or row["direction"] != "SHORT":
            self.failures.append(f"single SHORT direction mismatch: {dict(row) if row else None}")

    async def test_outside_active_hours_soft_check(self) -> None:
        status, body = await self.post_webhook(
            {
                "pair": "EURUSD",
                "direction": "UP",
                "price": "1.1070",
                "strength": "9",
                "time": str(int(time.time())),
            }
        )
        if status != 200:
            self.failures.append(f"outside-hours soft check transport failed: {status} {body}")
            return

        if isinstance(body, dict) and body.get("reason") == "outside_active_hours":
            return

        self._print(
            "outside_active_hours scenario skipped: current bot instance appears to run inside active window"
        )

    async def test_result_win_loss_draw(self) -> None:
        await self._wait_for_expire()

        # WIN for LONG
        ts_win = int(time.time())
        status, body = await self.post_webhook(
            {
                "pair": "BTCUSD",
                "direction": "UP",
                "price": "70000",
                "strength": "9",
                "time": str(int(time.time())),
            }
        )
        if status != 200:
            self.failures.append(f"result WIN setup failed: {status} {body}")
            return
        await self._wait_for_batch()
        await self.post_webhook(
            {
                "pair": "BTCUSD",
                "direction": "UP",
                "price": "70100",
                "strength": "9",
                "time": str(int(time.time())),
            }
        )
        await self._wait_for_expire()

        row = self._fetchone(
            """
            SELECT status
            FROM signals
            WHERE symbol = 'BTCUSD' AND direction = 'LONG' AND created_at >= ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (ts_win,),
        )
        if row is None or row["status"] != "WIN":
            self.failures.append(f"WIN check failed: {dict(row) if row else None}")

        # LOSS for LONG
        ts_loss = int(time.time())
        status, body = await self.post_webhook(
            {
                "pair": "EURJPY",
                "direction": "DOWN",
                "price": "168.3000",
                "strength": "9",
                "time": str(int(time.time())),
            }
        )
        if status != 200:
            self.failures.append(f"result LOSS setup failed: {status} {body}")
            return
        await self._wait_for_batch()
        await self.post_webhook(
            {
                "pair": "EURJPY",
                "direction": "DOWN",
                "price": "168.5000",
                "strength": "9",
                "time": str(int(time.time())),
            }
        )
        await self._wait_for_expire()

        row = self._fetchone(
            """
            SELECT status
            FROM signals
            WHERE symbol = 'EURJPY' AND direction = 'SHORT' AND created_at >= ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (ts_loss,),
        )
        if row is None or row["status"] != "LOSS":
            self.failures.append(f"LOSS check failed: {dict(row) if row else None}")

        # DRAW
        ts_draw = int(time.time())
        status, body = await self.post_webhook(
            {
                "pair": "AUDUSD",
                "direction": "DOWN",
                "price": "0.6600",
                "strength": "9",
                "time": str(int(time.time())),
            }
        )
        if status != 200:
            self.failures.append(f"result DRAW setup failed: {status} {body}")
            return
        await self._wait_for_batch()
        await self.post_webhook(
            {
                "pair": "AUDUSD",
                "direction": "DOWN",
                "price": "0.6600",
                "strength": "9",
                "time": str(int(time.time())),
            }
        )
        await self._wait_for_expire()

        row = self._fetchone(
            """
            SELECT status
            FROM signals
            WHERE symbol = 'AUDUSD' AND direction = 'SHORT' AND created_at >= ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (ts_draw,),
        )
        if row is None or row["status"] != "DRAW":
            self.failures.append(f"DRAW check failed: {dict(row) if row else None}")

    def test_command_texts_smoke(self) -> None:
        from bot import BotApp
        from config import Settings
        from database.db import Database
        from services.ai_filter import AIFilter
        from services.market_analyzer import MarketAnalyzer
        from services.quality_filter import SignalQualityFilter
        from services.result_checker import ResultChecker
        from services.signal_selector import SignalSelector
        from services.statistics import StatisticsService

        db = Database(str(self.cfg.db_path))

        class DummyBot:
            pass

        class DummyWsClient:
            def status(self) -> dict[str, Any]:
                return {
                    "mode": "mock",
                    "connected": False,
                    "last_error": "not_connected",
                    "last_message_ts": 0,
                }

        try:
            db.init()
            stats = StatisticsService(db)
            _ = stats.summary_text()
            _ = stats.pairs_text()

            settings = Settings(
                bot_token="x",
                signal_threshold=6.0,
                expiration_seconds=8,
                min_volatility=0.0006,
                rsi_period=14,
                atr_period=14,
                ema_fast=50,
                ema_slow=200,
                ws_url="",
                ws_reconnect_seconds=5,
                ws_auth_token="",
                ws_subscribe_payload="",
                mock_data=True,
                mock_symbols=["EURUSD"],
                webhook_host="127.0.0.1",
                webhook_port=8088,
                webhook_secret="",
                tv_allowed_pairs=["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "EURJPY", "BTCUSD"],
                signal_cooldown_seconds=20,
                signal_batch_window_seconds=2,
                active_hours_start=8,
                active_hours_end=22,
                telegram_chat_id=None,
                log_level="INFO",
                db_path=str(self.cfg.db_path),
            )
            analyzer = MarketAnalyzer(settings)
            selector = SignalSelector()
            selector.start()
            quality = SignalQualityFilter(settings=settings, analyzer=analyzer, ai_filter=AIFilter())
            app = BotApp(
                settings=settings,
                bot=DummyBot(),
                db=db,
                analyzer=analyzer,
                selector=selector,
                result_checker=ResultChecker(),
                statistics=stats,
                quality_filter=quality,
                ws_client=DummyWsClient(),
            )

            _ = app.active_signal_text()
            _ = app.last_signals_text()
            _ = app.debug_text()
        finally:
            db.close()

    def _print(self, msg: str) -> None:
        print(f"[test_webhook] {msg}")

    def _report(self) -> None:
        if self.failures:
            self._print("FAILED")
            for idx, item in enumerate(self.failures, start=1):
                self._print(f"{idx}. {item}")
        else:
            self._print("PASSED")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="E2E webhook test runner")
    parser.add_argument("--base-url", default="http://127.0.0.1:8088", help="Webhook server base URL")
    parser.add_argument("--db-path", default="database/market.db", help="Path to SQLite DB")
    parser.add_argument("--batch-window", type=int, default=2, help="Batch window seconds")
    parser.add_argument("--expiration", type=int, default=12, help="Expiration seconds used by running bot")
    parser.add_argument("--pair", default="EURUSD", help="Primary pair for single-signal checks")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = TestConfig(
        base_url=args.base_url.rstrip("/"),
        db_path=Path(args.db_path),
        batch_window=max(1, args.batch_window),
        expiration_seconds=max(2, args.expiration),
        pair_primary=args.pair,
    )
    runner = TestRunner(cfg)
    return asyncio.run(runner.run())


if __name__ == "__main__":
    raise SystemExit(main())
