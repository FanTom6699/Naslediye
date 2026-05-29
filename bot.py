from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

from aiogram import Bot, Dispatcher

from config import Settings, load_settings
from database.db import Database
from handlers.commands import get_commands_router
from handlers.menu import get_menu_router
from handlers.start import get_start_router
from handlers.stats import get_stats_router
from logger import setup_logging
from services.ai_filter import AIFilter
from services.market_analyzer import Candle, MarketAnalyzer
from services.quality_filter import SignalQualityFilter
from services.result_checker import ResultChecker
from services.signal_selector import SignalCandidate, SignalSelector
from services.statistics import StatisticsService
from services.webhook_server import TradingViewSignal, TradingViewWebhookServer
from services.websocket_client import PocketOptionWebSocketClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvaluatedWebhookSignal:
    pair: str
    direction: str
    direction_human: str
    price: float
    score: float
    reasons: list[str]
    webhook_strength: float


@dataclass
class BotApp:
    settings: Settings
    bot: Bot
    db: Database
    analyzer: MarketAnalyzer
    selector: SignalSelector
    result_checker: ResultChecker
    statistics: StatisticsService
    quality_filter: SignalQualityFilter
    ws_client: PocketOptionWebSocketClient
    webhook_server: TradingViewWebhookServer | None = None
    ws_task: asyncio.Task[None] | None = None
    engine_task: asyncio.Task[None] | None = None
    batch_task: asyncio.Task[None] | None = None
    signal_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    pending_signals: list[EvaluatedWebhookSignal] = field(default_factory=list)
    last_webhook_price: dict[str, float] = field(default_factory=dict)
    started: bool = False
    started_at: int = 0

    def home_text(self) -> str:
        return (
            "TradingView Webhook Scanner\n\n"
            "Основной источник: TradingView Webhook.\n"
            "Резервный источник: WebSocket market feed (только данные).\n"
            "Авто-сделки и управление аккаунтом отключены.\n\n"
            "Режим: информационные сигналы."
        )

    def settings_text(self) -> str:
        s = self.settings
        return (
            "⚙️ Настройки анализа\n\n"
            f"SIGNAL_THRESHOLD: {s.signal_threshold}\n"
            f"EXPIRATION_SECONDS: {s.expiration_seconds}\n"
            f"MIN_VOLATILITY: {s.min_volatility}\n"
            f"RSI_PERIOD: {s.rsi_period}\n"
            f"ATR_PERIOD: {s.atr_period}\n"
            f"EMA_FAST: {s.ema_fast}\n"
            f"EMA_SLOW: {s.ema_slow}\n"
            f"MOCK_DATA: {s.mock_data}\n"
            f"WEBHOOK: {s.webhook_host}:{s.webhook_port}\n"
            f"WS_URL: {s.ws_url}\n"
            f"COOLDOWN: {s.signal_cooldown_seconds} сек\n"
            f"ACTIVE_HOURS: {s.active_hours_start:02d}:00-{s.active_hours_end:02d}:00\n"
            f"BATCH_WINDOW: {s.signal_batch_window_seconds} сек"
        )

    def active_signal_text(self) -> str:
        active = self.selector.active_signal
        if active is None:
            db_active = self.db.get_active_signal()
            if db_active is None:
                return "📈 Активный сигнал: нет"

            return (
                "📈 Активный сигнал\n\n"
                f"ID: {db_active['id']}\n"
                f"Пара: {db_active['symbol']}\n"
                f"Направление: {'ВВЕРХ' if db_active['direction'] == 'LONG' else 'ВНИЗ'}\n"
                f"Цена входа: {db_active['entry_price']}\n"
                f"Сила: {db_active['strength']}/10"
            )

        return (
            "📈 Активный сигнал\n\n"
            f"ID: {active.signal_id}\n"
            f"Пара: {active.symbol}\n"
            f"Направление: {'ВВЕРХ' if active.direction == 'LONG' else 'ВНИЗ'}\n"
            f"Цена входа: {active.entry_price:.6f}\n"
            f"Сила: {active.strength:.2f}/10\n"
            f"Экспирация: {max(0, active.expires_at - int(time.time()))} сек"
        )

    def last_signals_text(self, limit: int = 10) -> str:
        items = self.db.get_last_signals(limit=limit)
        if not items:
            return "📜 Последние сигналы: пусто"

        lines = ["📜 Последние сигналы", ""]
        for item in items:
            status = item.get("status") or "ACTIVE"
            lines.append(
                f"#{item['id']} {item['symbol']} {'ВВЕРХ' if item['direction'] == 'LONG' else 'ВНИЗ'} "
                f"| S={float(item['strength']):.2f} | {status}"
            )
        return "\n".join(lines)

    async def ingest_tradingview_signal(self, signal: TradingViewSignal) -> dict:
        async with self.signal_lock:
            pair = signal.pair.upper().strip()
            self.last_webhook_price[pair] = float(signal.price)
            if pair not in self.settings.tv_allowed_pairs:
                self._log_rejection(pair, "UNKNOWN", signal.strength, "Пара не разрешена", "TV_ALLOWED_PAIRS")
                return {"accepted": False, "reason": "Pair is not allowed"}

            direction_raw = signal.direction.upper().strip()
            if direction_raw in {"UP", "LONG", "BUY"}:
                direction = "LONG"
                direction_human = "ВВЕРХ"
            elif direction_raw in {"DOWN", "SHORT", "SELL"}:
                direction = "SHORT"
                direction_human = "ВНИЗ"
            else:
                self._log_rejection(pair, "UNKNOWN", signal.strength, "Неверное направление", signal.direction)
                return {"accepted": False, "reason": "Direction must be UP/DOWN"}

            if self.selector.has_active_signal():
                self._log_rejection(pair, direction, signal.strength, "active_signal_exists", "active_lock")
                return {"accepted": False, "reason": "active_signal_exists"}

            if not self._is_active_hours():
                self._log_rejection(pair, direction, signal.strength, "outside_active_hours", "time_filter")
                return {"accepted": False, "reason": "outside_active_hours"}

            cooldown_left = self._cooldown_left_seconds(pair, direction)
            if cooldown_left > 0:
                self._log_rejection(
                    pair,
                    direction,
                    signal.strength,
                    "cooldown",
                    f"remain={cooldown_left}s",
                )
                return {"accepted": False, "reason": f"cooldown:{cooldown_left}s"}

            quality = await self.quality_filter.evaluate(
                pair=pair,
                direction=direction,
                strength=signal.strength,
            )
            if not quality.accepted:
                self._log_rejection(pair, direction, quality.score, quality.reason, "; ".join(quality.reasons))
                return {"accepted": False, "reason": quality.reason}

            evaluated = EvaluatedWebhookSignal(
                pair=pair,
                direction=direction,
                direction_human=direction_human,
                price=signal.price,
                score=quality.score,
                reasons=quality.reasons,
                webhook_strength=signal.strength,
            )
            self.pending_signals.append(evaluated)

            if self.batch_task is None or self.batch_task.done():
                self.batch_task = asyncio.create_task(self._flush_pending_signals(), name="signal-batch-flush")

            return {
                "accepted": True,
                "queued": True,
                "pair": pair,
                "direction": direction,
                "score": quality.score,
                "pending": len(self.pending_signals),
            }

    async def _flush_pending_signals(self) -> None:
        await asyncio.sleep(max(1, self.settings.signal_batch_window_seconds))

        async with self.signal_lock:
            if not self.pending_signals:
                return

            if self.selector.has_active_signal():
                for candidate in self.pending_signals:
                    self._log_rejection(
                        candidate.pair,
                        candidate.direction,
                        candidate.score,
                        "active_signal_exists",
                        "batch_dropped",
                    )
                self.pending_signals.clear()
                return

            best = max(
                self.pending_signals,
                key=lambda item: (item.score, item.webhook_strength),
            )

            for candidate in self.pending_signals:
                if candidate is best:
                    continue
                self._log_rejection(
                    candidate.pair,
                    candidate.direction,
                    candidate.score,
                    "batch_lost",
                    f"winner={best.pair}:{best.score:.2f}",
                )

            self.pending_signals.clear()

        await self._publish_signal(best)

    async def _publish_signal(self, best: EvaluatedWebhookSignal) -> None:
        signal_id = self.db.insert_signal(
            source="TRADINGVIEW",
            symbol=best.pair,
            direction=best.direction,
            strength=best.score,
            reasons="; ".join(best.reasons),
            entry_price=best.price,
            expires_at=int(time.time()) + self.settings.expiration_seconds,
        )

        candidate = SignalCandidate(
            symbol=best.pair,
            direction=best.direction,
            strength=best.score,
            reasons=best.reasons,
            confidence_flags={"quality": True},
        )
        active = self.selector.activate(
            signal_id=signal_id,
            candidate=candidate,
            entry_price=best.price,
            expiration_seconds=self.settings.expiration_seconds,
        )

        reasons_lines = "\n".join(f"✅ {reason}" for reason in best.reasons[:6])
        if not reasons_lines:
            reasons_lines = "✅ Композитный рейтинг"

        await self.broadcast(
            "📊 Новый сигнал\n\n"
            f"Пара: {best.pair}\n"
            f"Направление: {best.direction_human}\n"
            f"Цена входа: {best.price}\n"
            f"Сила сигнала: {best.score:.2f}/10\n\n"
            "Причины:\n"
            f"{reasons_lines}"
        )

        logger.info(
            "Signal published id=%s pair=%s dir=%s score=%.2f expires_at=%s",
            signal_id,
            best.pair,
            best.direction,
            best.score,
            active.expires_at,
        )

    def _is_active_hours(self) -> bool:
        start = max(0, min(23, self.settings.active_hours_start))
        end = max(0, min(24, self.settings.active_hours_end))
        now_hour = datetime.now().hour

        if start == end:
            return True
        if start < end:
            return start <= now_hour < end
        return now_hour >= start or now_hour < end

    def _cooldown_left_seconds(self, pair: str, direction: str) -> int:
        if self.settings.signal_cooldown_seconds <= 0:
            return 0
        last_ts = self.db.get_last_signal_time(pair, direction)
        if last_ts is None:
            return 0
        elapsed = int(time.time()) - int(last_ts)
        remain = self.settings.signal_cooldown_seconds - elapsed
        return max(0, remain)

    def _log_rejection(self, pair: str, direction: str, strength: float, reason: str, details: str) -> None:
        self.db.insert_rejection(pair, direction, strength, reason, details)
        logger.info(
            "Signal rejected pair=%s direction=%s strength=%.2f reason=%s details=%s",
            pair,
            direction,
            strength,
            reason,
            details,
        )

    def debug_text(self) -> str:
        active = self.active_signal_text()
        latest_symbols = self.analyzer.get_symbols()
        last_symbol = latest_symbols[-1] if latest_symbols else "N/A"
        last_price = self.analyzer.get_price(last_symbol) if latest_symbols else None
        ws = self.ws_client.status()
        rejections = self.db.get_last_rejections(limit=5)

        lines = [
            "🧪 Debug",
            "",
            active,
            "",
            f"Последняя пара market feed: {last_symbol}",
            f"Последняя цена: {last_price if last_price is not None else 'N/A'}",
            f"WS connected: {ws.get('connected')}",
            f"WS mode: {ws.get('mode')}",
            f"WS last_message_ts: {ws.get('last_message_ts')}",
            f"Pending batch signals: {len(self.pending_signals)}",
            f"Фильтр времени: {self.settings.active_hours_start:02d}:00-{self.settings.active_hours_end:02d}:00",
            f"Cooldown: {self.settings.signal_cooldown_seconds} сек",
            "",
            "Последние отклонения:",
        ]
        if not rejections:
            lines.append("нет")
        else:
            for item in rejections:
                lines.append(
                    f"- {item['pair']} {item['direction']} | {item['reason']} | s={float(item['strength']):.2f}"
                )

        return "\n".join(lines)

    def health_snapshot(self) -> dict:
        ws = self.ws_client.status()
        return {
            "database_status": "up" if self.db.ping() else "down",
            "websocket_status": "up" if bool(ws.get("connected")) else "down",
            "bot_status": "running" if self.started else "stopped",
            "ws_mode": ws.get("mode"),
            "ws_last_message_ts": ws.get("last_message_ts"),
        }

    async def broadcast(self, text: str) -> None:
        chat_ids = set(self.db.get_subscribers())
        if self.settings.telegram_chat_id is not None:
            chat_ids.add(self.settings.telegram_chat_id)

        for chat_id in chat_ids:
            try:
                user_cfg = self.db.get_user_settings(chat_id)
                if user_cfg is not None and int(user_cfg.get("is_enabled", 1)) == 0:
                    continue
                await self.bot.send_message(chat_id, text)
            except Exception:
                logger.exception("Failed to send message to chat_id=%s", chat_id)

    async def run_engine(self) -> None:
        while True:
            try:
                await self._engine_tick()
            except Exception:
                logger.exception("Signal engine tick failed")
            await asyncio.sleep(1)

    async def _engine_tick(self) -> None:
        active = self.selector.active_signal
        now = int(time.time())

        if active is not None:
            if now < active.expires_at:
                return

            close_price = self.analyzer.get_price(active.symbol)
            if close_price is None:
                close_price = self.last_webhook_price.get(active.symbol)
            if close_price is None:
                self._log_rejection(
                    active.symbol,
                    active.direction,
                    active.strength,
                    "close_price_unavailable",
                    "ws_and_webhook_price_missing",
                )
                return

            status = self.result_checker.evaluate(active, close_price)
            self.db.close_signal(active.signal_id, close_price, status)
            await self.broadcast(
                "Результат сигнала\n"
                f"Пара: {active.symbol}\n"
                f"Направление: {'ВВЕРХ' if active.direction == 'LONG' else 'ВНИЗ'}\n"
                f"Цена входа: {active.entry_price:.6f}\n"
                f"Цена закрытия: {close_price:.6f}\n"
                f"Итог: {'WIN ✅' if status == 'WIN' else 'LOSS ❌' if status == 'LOSS' else 'DRAW ➖'}"
            )
            self.selector.clear_active()
            return

    async def startup(self) -> None:
        self.started = True
        self.started_at = int(time.time())
        logger.info("bot started")
        self.ws_task = asyncio.create_task(self.ws_client.run(), name="ws-client")
        self.engine_task = asyncio.create_task(self.run_engine(), name="signal-engine")
        if self.webhook_server is not None:
            await self.webhook_server.start()
            logger.info("webhook server started")
        logger.info("database connected")
        logger.info(
            "runtime settings: active_hours=%02d:00-%02d:00 cooldown=%ss batch_window=%ss",
            self.settings.active_hours_start,
            self.settings.active_hours_end,
            self.settings.signal_cooldown_seconds,
            self.settings.signal_batch_window_seconds,
        )
        logger.info("allowed pairs: %s", ",".join(self.settings.tv_allowed_pairs))
        logger.info(
            "webhook endpoint: http://%s:%s/webhook",
            self.settings.webhook_host,
            self.settings.webhook_port,
        )
        logger.info("Background services started")

    async def shutdown(self) -> None:
        await self.ws_client.stop()
        tasks = [task for task in (self.ws_task, self.engine_task) if task is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

        if self.webhook_server is not None:
            await self.webhook_server.stop()

        self.started = False

        self.db.close()
        await self.bot.session.close()
        logger.info("Application shutdown complete")


async def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    db = Database(settings.db_path)
    db.init()

    bot = Bot(token=settings.bot_token)
    analyzer = MarketAnalyzer(settings)
    selector = SignalSelector()
    selector.start()
    result_checker = ResultChecker()
    statistics = StatisticsService(db)
    ai_filter = AIFilter()
    quality_filter = SignalQualityFilter(settings=settings, analyzer=analyzer, ai_filter=ai_filter)

    async def on_candle(candle: Candle) -> None:
        analyzer.update_candle(candle)

    app = BotApp(
        settings=settings,
        bot=bot,
        db=db,
        analyzer=analyzer,
        selector=selector,
        result_checker=result_checker,
        statistics=statistics,
        quality_filter=quality_filter,
        ws_client=PocketOptionWebSocketClient(settings, on_candle=on_candle),
    )

    app.webhook_server = TradingViewWebhookServer(
        host=settings.webhook_host,
        port=settings.webhook_port,
        webhook_secret=settings.webhook_secret,
        on_signal=app.ingest_tradingview_signal,
        on_health=app.health_snapshot,
    )

    dp = Dispatcher()
    dp.include_router(get_start_router(app))
    dp.include_router(get_menu_router(app))
    dp.include_router(get_stats_router(app))
    dp.include_router(get_commands_router(app))

    async def on_startup(**_: object) -> None:
        await app.startup()

    async def on_shutdown(**_: object) -> None:
        await app.shutdown()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting bot polling")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
