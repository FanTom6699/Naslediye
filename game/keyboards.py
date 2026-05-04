from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from game.buildings import BuildingState


def buildings_keyboard(states: list[BuildingState]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for state in states:
        builder.button(
            text=f"Улучшить: {state.name}",
            callback_data=f"bld:up:{state.code}",
        )
        builder.button(
            text=f"Информация: {state.name}",
            callback_data=f"bld:info:{state.code}",
        )

    builder.button(text="Обновить", callback_data="bld:refresh")
    builder.adjust(2, 2, 2, 2, 2, 2, 1)
    return builder.as_markup()


def info_keyboard(code: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Улучшить", callback_data=f"bld:up:{code}")
    builder.button(text="Назад к списку", callback_data="bld:refresh")
    builder.adjust(1)
    return builder.as_markup()
