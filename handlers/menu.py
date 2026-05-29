from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

CALLBACK_HOME = "menu:home"
CALLBACK_STATS = "menu:stats"
CALLBACK_ACTIVE = "menu:active"
CALLBACK_LAST = "menu:last"
CALLBACK_SETTINGS = "menu:settings"


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data=CALLBACK_STATS)],
            [InlineKeyboardButton(text="📈 Активный сигнал", callback_data=CALLBACK_ACTIVE)],
            [InlineKeyboardButton(text="📜 Последние сигналы", callback_data=CALLBACK_LAST)],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data=CALLBACK_SETTINGS)],
        ]
    )


def get_menu_router(app) -> Router:
    router = Router(name="menu")

    @router.callback_query(F.data == CALLBACK_HOME)
    async def cb_home(callback: CallbackQuery) -> None:
        if callback.message is None:
            await callback.answer()
            return

        await callback.message.edit_text(
            app.home_text(),
            reply_markup=main_menu_keyboard(),
        )
        await callback.answer()

    @router.callback_query(F.data == CALLBACK_SETTINGS)
    async def cb_settings(callback: CallbackQuery) -> None:
        if callback.message is None:
            await callback.answer()
            return

        await callback.message.edit_text(
            app.settings_text(),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅ Назад", callback_data=CALLBACK_HOME)]]
            ),
        )
        await callback.answer()

    return router
