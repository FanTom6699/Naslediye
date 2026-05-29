from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message


def get_commands_router(app) -> Router:
    router = Router(name="commands")

    @router.message(Command("stats"))
    async def cmd_stats(message: Message) -> None:
        await message.answer(app.statistics.summary_text())

    @router.message(Command("active"))
    async def cmd_active(message: Message) -> None:
        await message.answer(app.active_signal_text())

    @router.message(Command("last"))
    async def cmd_last(message: Message) -> None:
        await message.answer(app.last_signals_text())

    @router.message(Command("pairs"))
    async def cmd_pairs(message: Message) -> None:
        await message.answer(app.statistics.pairs_text())

    @router.message(Command("debug"))
    async def cmd_debug(message: Message) -> None:
        await message.answer(app.debug_text())

    return router
