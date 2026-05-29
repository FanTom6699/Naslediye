from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from handlers.menu import main_menu_keyboard


def get_start_router(app) -> Router:
    router = Router(name="start")

    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        app.db.add_subscriber(message.chat.id)
        await message.answer(app.home_text(), reply_markup=main_menu_keyboard())

    return router
