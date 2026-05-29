from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TradingViewPayload(BaseModel):
    pair: str = Field(min_length=3)
    direction: str = Field(min_length=2)
    price: str | float
    strength: str | float
    time: str


@dataclass(frozen=True)
class TradingViewSignal:
    pair: str
    direction: str
    price: float
    strength: float
    time: str


WebhookHandler = Callable[[TradingViewSignal], Awaitable[dict]]
HealthHandler = Callable[[], Awaitable[dict] | dict]


class TradingViewWebhookServer:
    def __init__(
        self,
        host: str,
        port: int,
        webhook_secret: str,
        on_signal: WebhookHandler,
        on_health: HealthHandler | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.webhook_secret = webhook_secret
        self.on_signal = on_signal
        self.on_health = on_health

        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self.app = FastAPI(title="TradingView Webhook", version="1.0")

        @self.app.post("/webhook")
        async def webhook(payload: TradingViewPayload, x_webhook_secret: str | None = Header(default=None)) -> dict:
            if self.webhook_secret and x_webhook_secret != self.webhook_secret:
                raise HTTPException(status_code=401, detail="Invalid webhook secret")

            try:
                signal = TradingViewSignal(
                    pair=payload.pair.upper().strip(),
                    direction=payload.direction.upper().strip(),
                    price=float(payload.price),
                    strength=float(payload.strength),
                    time=str(payload.time),
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid numeric payload") from exc

            result = await self.on_signal(signal)
            return result

        @self.app.get("/health")
        async def health() -> dict:
            details: dict = {}
            if self.on_health is not None:
                maybe = self.on_health()
                if asyncio.iscoroutine(maybe):
                    details = await maybe
                elif isinstance(maybe, dict):
                    details = maybe

            return {
                "webhook_status": "up" if self._running else "starting",
                **details,
            }

    async def start(self) -> None:
        logger.info("Starting webhook server on %s:%s", self.host, self.port)
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            loop="asyncio",
        )
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve(), name="webhook-server")
        await asyncio.sleep(0.25)
        self._running = True

    async def stop(self) -> None:
        self._running = False
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    @property
    def is_running(self) -> bool:
        return self._running
