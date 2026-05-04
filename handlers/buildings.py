from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from game.keyboards import buildings_keyboard, info_keyboard
from game.service import BuildingService


def get_buildings_router(service: BuildingService) -> Router:
    router = Router(name="buildings")

    @router.message(Command("buildings"))
    async def cmd_buildings(message: Message) -> None:
        if message.from_user is None:
            return

        text, states = service.get_overview_text(message.from_user.id)
        await message.answer(text, reply_markup=buildings_keyboard(states))

    @router.callback_query(F.data == "bld:refresh")
    async def cb_refresh(callback: CallbackQuery) -> None:
        if callback.from_user is None or callback.message is None:
            await callback.answer()
            return

        text, states = service.get_overview_text(callback.from_user.id)
        await callback.message.edit_text(text, reply_markup=buildings_keyboard(states))
        await callback.answer("Список обновлен")

    @router.callback_query(F.data.startswith("bld:info:"))
    async def cb_info(callback: CallbackQuery) -> None:
        if callback.from_user is None or callback.message is None or callback.data is None:
            await callback.answer()
            return

        code = callback.data.split(":", 2)[2]
        info_text = service.get_building_info_text(callback.from_user.id, code)
        await callback.message.edit_text(info_text, reply_markup=info_keyboard(code))
        await callback.answer()

    @router.callback_query(F.data.startswith("bld:up:"))
    async def cb_upgrade(callback: CallbackQuery) -> None:
        if callback.from_user is None or callback.message is None or callback.data is None:
            await callback.answer()
            return

        code = callback.data.split(":", 2)[2]
        result = service.start_upgrade(callback.from_user.id, code)

        text, states = service.get_overview_text(callback.from_user.id)
        await callback.message.edit_text(text, reply_markup=buildings_keyboard(states))
        await callback.answer(result.message, show_alert=not result.success)

    return router
