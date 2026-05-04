from __future__ import annotations

from dataclasses import dataclass

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo

from game.world_service import WorldService


@dataclass(frozen=True)
class WorldWebAppConfig:
    webapp_url: str


def world_keyboard(config: WorldWebAppConfig) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="🌍 Мир",
                    web_app=WebAppInfo(url=config.webapp_url),
                )
            ]
        ],
        resize_keyboard=True,
    )


def get_world_router(service: WorldService, config: WorldWebAppConfig) -> Router:
    router = Router(name="world")

    @router.message(Command("world"))
    async def cmd_world(message: Message) -> None:
        if message.chat.type != "private":
            await message.answer("Карта доступна только в личных сообщениях с ботом.")
            return

        await message.answer(
            "Откройте карту через кнопку ниже.",
            reply_markup=world_keyboard(config),
        )

    @router.message(F.web_app_data)
    async def webapp_data_handler(message: Message) -> None:
        if message.web_app_data is None:
            return

        try:
            payload = service.validate_payload(message.web_app_data.data)
            result = service.handle_action(payload, message.from_user.id if message.from_user else 0)
        except ValueError as exc:
            await message.answer(f"Ошибка данных WebApp: {exc}")
            return

        await message.answer(result)

    return router
