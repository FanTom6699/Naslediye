from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from handlers.menu import CALLBACK_ACTIVE, CALLBACK_HOME, CALLBACK_LAST, CALLBACK_STATS


def get_stats_router(app) -> Router:
    router = Router(name="stats")

    @router.callback_query(F.data == CALLBACK_STATS)
    async def cb_stats(callback: CallbackQuery) -> None:
        if callback.message is None:
            await callback.answer()
            return

        await callback.message.edit_text(
            app.statistics.summary_text(),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅ Назад", callback_data=CALLBACK_HOME)]]
            ),
        )
        await callback.answer()

    @router.callback_query(F.data == CALLBACK_ACTIVE)
    async def cb_active(callback: CallbackQuery) -> None:
        if callback.message is None:
            await callback.answer()
            return

        await callback.message.edit_text(
            app.active_signal_text(),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅ Назад", callback_data=CALLBACK_HOME)]]
            ),
        )
        await callback.answer()

    @router.callback_query(F.data == CALLBACK_LAST)
    async def cb_last(callback: CallbackQuery) -> None:
        if callback.message is None:
            await callback.answer()
            return

        await callback.message.edit_text(
            app.last_signals_text(),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅ Назад", callback_data=CALLBACK_HOME)]]
            ),
        )
        await callback.answer()

    return router
