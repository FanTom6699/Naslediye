from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ALLOWED_ACTIONS = {"attack", "scout", "gather"}
MAP_SIZE = 25


@dataclass(frozen=True)
class WebAppAction:
    action: str
    x: int
    y: int


class WorldService:
    def __init__(self, objects_path: str) -> None:
        self.objects_path = Path(objects_path)

    def validate_payload(self, raw_payload: str) -> WebAppAction:
        try:
            data = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise ValueError("Некорректный JSON из WebApp") from exc

        action = str(data.get("action", "")).lower()
        if action not in ALLOWED_ACTIONS:
            raise ValueError("Неизвестное действие")

        x = int(data.get("x"))
        y = int(data.get("y"))
        if x < 0 or x >= MAP_SIZE or y < 0 or y >= MAP_SIZE:
            raise ValueError("Координаты вне карты")

        return WebAppAction(action=action, x=x, y=y)

    def _load_objects(self) -> list[dict[str, Any]]:
        if not self.objects_path.exists():
            return []

        with self.objects_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        objects = data.get("objects", [])
        if not isinstance(objects, list):
            return []
        return objects

    def _find_object(self, x: int, y: int) -> dict[str, Any] | None:
        for obj in self._load_objects():
            if int(obj.get("x", -1)) == x and int(obj.get("y", -1)) == y:
                return obj
        return None

    def handle_action(self, payload: WebAppAction, user_id: int) -> str:
        target = self._find_object(payload.x, payload.y)

        if payload.action == "attack":
            return self._attack_result(payload, target, user_id)
        if payload.action == "scout":
            return self._scout_result(payload, target, user_id)
        if payload.action == "gather":
            return self._gather_result(payload, target, user_id)

        return "Действие не обработано."

    def _attack_result(self, payload: WebAppAction, target: dict[str, Any] | None, user_id: int) -> str:
        if target is None:
            return f"[{user_id}] Атака на ({payload.x}, {payload.y}): цель не найдена."

        target_name = str(target.get("name", "Неизвестный объект"))
        target_type = str(target.get("type", "unknown"))
        return (
            f"[{user_id}] Атака отправлена на {target_name} ({target_type}) "
            f"в точке ({payload.x}, {payload.y})."
        )

    def _scout_result(self, payload: WebAppAction, target: dict[str, Any] | None, user_id: int) -> str:
        if target is None:
            return f"[{user_id}] Разведка ({payload.x}, {payload.y}): местность пуста."

        target_name = str(target.get("name", "Неизвестный объект"))
        owner = str(target.get("owner", "нейтральный"))
        return (
            f"[{user_id}] Разведка завершена: {target_name} в ({payload.x}, {payload.y}), "
            f"владелец: {owner}."
        )

    def _gather_result(self, payload: WebAppAction, target: dict[str, Any] | None, user_id: int) -> str:
        if target is None:
            return f"[{user_id}] Сбор в ({payload.x}, {payload.y}) невозможен: ресурс не найден."

        target_type = str(target.get("type", ""))
        if target_type != "resource":
            return f"[{user_id}] Сбор в ({payload.x}, {payload.y}) невозможен: это не ресурс."

        resource_kind = str(target.get("resource", "ресурс"))
        amount = int(target.get("amount", 0))
        return (
            f"[{user_id}] Сбор выполнен: добыто {amount} ед. ({resource_kind}) "
            f"в точке ({payload.x}, {payload.y})."
        )
