from __future__ import annotations

import time
from dataclasses import dataclass

from game.buildings import (
    BUILDINGS,
    BUILDINGS_ORDER,
    BuildingState,
    calculate_upgrade_cost,
    calculate_upgrade_minutes,
    format_cost,
    format_duration,
)
from game.database import GameDatabase


@dataclass(frozen=True)
class UpgradeResult:
    success: bool
    message: str


class BuildingService:
    def __init__(self, db: GameDatabase) -> None:
        self.db = db

    def ensure_player(self, user_id: int) -> None:
        self.db.ensure_player(user_id)

    def _build_state(self, row: dict[str, int | str | None]) -> BuildingState:
        code = str(row["code"])
        level = int(row["level"])
        upgrade_end_ts = int(row["upgrade_end_ts"]) if row["upgrade_end_ts"] else None
        definition = BUILDINGS[code]

        if level >= definition.max_level:
            next_cost = None
            next_minutes = None
        else:
            next_cost = calculate_upgrade_cost(definition, level)
            next_minutes = calculate_upgrade_minutes(definition, level)

        return BuildingState(
            code=code,
            name=definition.name,
            level=level,
            max_level=definition.max_level,
            description=definition.description,
            next_upgrade_cost=next_cost,
            next_upgrade_minutes=next_minutes,
            upgrade_end_ts=upgrade_end_ts,
        )

    def process_due_upgrades_for_user(self, user_id: int) -> list[str]:
        now_ts = int(time.time())
        completed: list[str] = []

        for row in self.db.get_buildings(user_id):
            upgrade_end_ts = row["upgrade_end_ts"]
            if not upgrade_end_ts:
                continue
            if int(upgrade_end_ts) > now_ts:
                continue

            code = str(row["code"])
            current_level = int(row["level"])
            definition = BUILDINGS[code]
            new_level = min(current_level + 1, definition.max_level)
            self.db.complete_upgrade(user_id, code, new_level)
            completed.append(f"{definition.name} -> {new_level} ур.")

        return completed

    def process_due_upgrades_for_all(self) -> None:
        now_ts = int(time.time())
        for user_id in self.db.users_with_due_upgrades(now_ts):
            self.process_due_upgrades_for_user(user_id)

    def get_overview_text(self, user_id: int) -> tuple[str, list[BuildingState]]:
        self.ensure_player(user_id)
        completed = self.process_due_upgrades_for_user(user_id)
        resources = self.db.get_resources(user_id)

        states_by_code = {
            str(row["code"]): self._build_state(row)
            for row in self.db.get_buildings(user_id)
        }

        lines = [
            "Ваши здания:",
            "",
            f"Ресурсы: дерево={resources['wood']}, камень={resources['stone']}, железо={resources['iron']}, еда={resources['food']}",
            "",
        ]

        if completed:
            lines.append("Завершены улучшения:")
            lines.extend([f"- {item}" for item in completed])
            lines.append("")

        ordered_states: list[BuildingState] = []
        now_ts = int(time.time())
        for code in BUILDINGS_ORDER:
            state = states_by_code[code]
            ordered_states.append(state)
            status = f"{state.level}/{state.max_level}"
            if state.upgrade_end_ts:
                remaining = max(0, state.upgrade_end_ts - now_ts)
                status += f" (улучшение: {format_duration(remaining)})"
            lines.append(f"{state.name}: {status}")

        return "\n".join(lines), ordered_states

    def get_building_info_text(self, user_id: int, code: str) -> str:
        self.ensure_player(user_id)
        self.process_due_upgrades_for_user(user_id)

        row = self.db.get_building(user_id, code)
        if row is None:
            return "Здание не найдено."

        state = self._build_state(row)
        lines = [
            f"{state.name}",
            f"Уровень: {state.level}/{state.max_level}",
            f"Описание: {state.description}",
        ]

        if state.level >= state.max_level:
            lines.append("Достигнут максимальный уровень.")
        else:
            assert state.next_upgrade_cost is not None
            assert state.next_upgrade_minutes is not None
            lines.append(f"Стоимость улучшения: {format_cost(state.next_upgrade_cost)}")
            lines.append(f"Время улучшения: {state.next_upgrade_minutes} мин")

        if state.upgrade_end_ts:
            remaining = max(0, state.upgrade_end_ts - int(time.time()))
            lines.append(f"Сейчас улучшается. Осталось: {format_duration(remaining)}")

        return "\n".join(lines)

    def start_upgrade(self, user_id: int, code: str) -> UpgradeResult:
        self.ensure_player(user_id)
        self.process_due_upgrades_for_user(user_id)

        row = self.db.get_building(user_id, code)
        if row is None:
            return UpgradeResult(False, "Здание не найдено.")

        state = self._build_state(row)

        if state.upgrade_end_ts:
            remaining = max(0, state.upgrade_end_ts - int(time.time()))
            return UpgradeResult(False, f"Улучшение уже идет. Осталось: {format_duration(remaining)}")

        if state.level >= state.max_level:
            return UpgradeResult(False, "Это здание уже максимального уровня.")

        assert state.next_upgrade_cost is not None
        assert state.next_upgrade_minutes is not None

        finish_ts = int(time.time()) + state.next_upgrade_minutes * 60
        success = self.db.try_start_upgrade(user_id, code, state.next_upgrade_cost, finish_ts)
        if not success:
            return UpgradeResult(False, "Недостаточно ресурсов или здание уже улучшается.")

        return UpgradeResult(
            True,
            f"Запущено улучшение: {state.name} до {state.level + 1} ур. Время: {state.next_upgrade_minutes} мин.",
        )
