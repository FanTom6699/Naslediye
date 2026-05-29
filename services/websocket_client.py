from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import websockets

from config import Settings
from services.market_analyzer import Candle

logger = logging.getLogger(__name__)

MarketCallback = Callable[[Candle], Awaitable[None]]


@dataclass(frozen=True)
class WsPayload:
    symbol: str
    close: float
    ts: int
    open: float
    high: float
    low: float
    volume: float


class PocketOptionWebSocketClient:
    def __init__(self, settings: Settings, on_candle: MarketCallback) -> None:
        self.settings = settings
        self.on_candle = on_candle
        self._stop_event = asyncio.Event()
        self._connected = False
        self._last_error = ""
        self._last_message_ts = 0

    async def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self.settings.mock_data:
                    await self._run_mock_stream()
                else:
                    await self._run_real_stream()
            except Exception:
                self._connected = False
                self._last_error = "worker_crash"
                logger.exception("WebSocket worker crashed")

            if self._stop_event.is_set():
                break
            await asyncio.sleep(self.settings.ws_reconnect_seconds)

    async def stop(self) -> None:
        self._stop_event.set()

    async def _run_real_stream(self) -> None:
        if not self.settings.ws_url:
            raise RuntimeError("WS_URL is empty")

        logger.info("Connecting to WebSocket: %s", self.settings.ws_url)
        headers: dict[str, str] | None = None
        if self.settings.ws_auth_token:
            headers = {"Authorization": f"Bearer {self.settings.ws_auth_token}"}

        async with websockets.connect(
            self.settings.ws_url,
            ping_interval=15,
            ping_timeout=15,
            additional_headers=headers,
        ) as ws:
            self._connected = True
            self._last_error = ""
            subscribe_msg = {
                "type": "subscribe",
                "symbols": self.settings.mock_symbols,
            }
            if self.settings.ws_subscribe_payload:
                try:
                    raw = json.loads(self.settings.ws_subscribe_payload)
                    if isinstance(raw, dict):
                        subscribe_msg = raw
                except json.JSONDecodeError:
                    logger.warning("WS_SUBSCRIBE_PAYLOAD has invalid JSON, using default subscribe message")

            await ws.send(json.dumps(subscribe_msg))

            async for message in ws:
                if self._stop_event.is_set():
                    self._connected = False
                    return

                try:
                    payload = self._parse_message(message)
                except ValueError:
                    continue

                if payload is None:
                    continue

                await self._dispatch_payload(payload)

        self._connected = False

    async def _run_mock_stream(self) -> None:
        logger.info("Mock data mode enabled. Symbols: %s", ", ".join(self.settings.mock_symbols))
        self._connected = True
        self._last_error = ""

        prices = {symbol: random.uniform(1.0, 2.0) for symbol in self.settings.mock_symbols}
        while not self._stop_event.is_set():
            for symbol in self.settings.mock_symbols:
                drift = random.uniform(-0.002, 0.002)
                vol = random.uniform(0.0002, 0.0018)
                prev = prices[symbol]
                close = max(0.2, prev + drift)
                high = max(prev, close) + vol
                low = min(prev, close) - vol
                open_price = prev
                prices[symbol] = close

                payload = WsPayload(
                    symbol=symbol,
                    close=close,
                    ts=int(time.time()),
                    open=open_price,
                    high=high,
                    low=low,
                    volume=random.uniform(1.0, 9.0),
                )
                await self._dispatch_payload(payload)

            await asyncio.sleep(1)

        self._connected = False

    async def _dispatch_payload(self, payload: WsPayload) -> None:
        self._last_message_ts = int(time.time())
        candle = Candle(
            symbol=payload.symbol,
            ts=payload.ts,
            open=payload.open,
            high=payload.high,
            low=payload.low,
            close=payload.close,
            volume=payload.volume,
        )
        await self.on_candle(candle)

    def _parse_message(self, message: str) -> WsPayload | None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        # Flexible parser for different provider payload styles.
        symbol = str(data.get("symbol") or data.get("pair") or "").strip()
        if not symbol:
            return None

        close = data.get("close", data.get("price"))
        if close is None:
            return None

        try:
            close_f = float(close)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid close value") from exc

        open_f = float(data.get("open", close_f))
        high_f = float(data.get("high", max(open_f, close_f)))
        low_f = float(data.get("low", min(open_f, close_f)))
        ts = int(data.get("ts", data.get("timestamp", time.time())))
        volume = float(data.get("volume", 1.0))

        return WsPayload(
            symbol=symbol,
            close=close_f,
            ts=ts,
            open=open_f,
            high=high_f,
            low=low_f,
            volume=volume,
        )

    def status(self) -> dict[str, object]:
        return {
            "mode": "mock" if self.settings.mock_data else "real",
            "connected": self._connected,
            "last_error": self._last_error,
            "last_message_ts": self._last_message_ts,
        }
