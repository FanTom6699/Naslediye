from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


ResourceCost = Dict[str, int]


@dataclass(frozen=True)
class BuildingDefinition:
    code: str
    name: str
    max_level: int
    base_upgrade_cost: ResourceCost
    base_upgrade_minutes: int
    description: str


@dataclass(frozen=True)
class BuildingState:
    code: str
    name: str
    level: int
    max_level: int
    description: str
    next_upgrade_cost: ResourceCost | None
    next_upgrade_minutes: int | None
    upgrade_end_ts: int | None


BUILDINGS_ORDER = (
    "townhall",
    "barracks",
    "stable",
    "mage_academy",
    "warehouse",
    "watchtower",
    "scout_center",
    "war_hq",
    "magic_school",
    "forge",
    "mason",
)


BUILDINGS: dict[str, BuildingDefinition] = {
    "townhall": BuildingDefinition(
        code="townhall",
        name="Ратуша",
        max_level=25,
        base_upgrade_cost={"wood": 120, "stone": 90, "iron": 70, "food": 80},
        base_upgrade_minutes=2,
        description="Главное административное здание. Открывает развитие города.",
    ),
    "barracks": BuildingDefinition(
        code="barracks",
        name="Казарма",
        max_level=20,
        base_upgrade_cost={"wood": 110, "stone": 80, "iron": 90, "food": 100},
        base_upgrade_minutes=3,
        description="Подготовка и усиление пехотных войск.",
    ),
    "stable": BuildingDefinition(
        code="stable",
        name="Конюшня",
        max_level=20,
        base_upgrade_cost={"wood": 130, "stone": 85, "iron": 75, "food": 110},
        base_upgrade_minutes=4,
        description="Тренировка кавалерии и ускорение конных отрядов.",
    ),
    "mage_academy": BuildingDefinition(
        code="mage_academy",
        name="Академия магов",
        max_level=15,
        base_upgrade_cost={"wood": 90, "stone": 120, "iron": 80, "food": 100},
        base_upgrade_minutes=5,
        description="Обучение магов и расширение магических возможностей.",
    ),
    "warehouse": BuildingDefinition(
        code="warehouse",
        name="Склад",
        max_level=30,
        base_upgrade_cost={"wood": 140, "stone": 95, "iron": 60, "food": 70},
        base_upgrade_minutes=2,
        description="Увеличивает емкость хранения ресурсов.",
    ),
    "watchtower": BuildingDefinition(
        code="watchtower",
        name="Караульная башня",
        max_level=18,
        base_upgrade_cost={"wood": 95, "stone": 130, "iron": 85, "food": 75},
        base_upgrade_minutes=4,
        description="Улучшает оборону и раннее обнаружение атак.",
    ),
    "scout_center": BuildingDefinition(
        code="scout_center",
        name="Центр разведки",
        max_level=18,
        base_upgrade_cost={"wood": 100, "stone": 90, "iron": 100, "food": 85},
        base_upgrade_minutes=4,
        description="Усиливает разведку и повышает точность отчетов.",
    ),
    "war_hq": BuildingDefinition(
        code="war_hq",
        name="Военный штаб",
        max_level=20,
        base_upgrade_cost={"wood": 120, "stone": 120, "iron": 120, "food": 95},
        base_upgrade_minutes=5,
        description="Координация армии, тактические и боевые бонусы.",
    ),
    "magic_school": BuildingDefinition(
        code="magic_school",
        name="Школа магии",
        max_level=18,
        base_upgrade_cost={"wood": 80, "stone": 110, "iron": 90, "food": 100},
        base_upgrade_minutes=4,
        description="Развивает магические навыки и доступные заклинания.",
    ),
    "forge": BuildingDefinition(
        code="forge",
        name="Кузница",
        max_level=22,
        base_upgrade_cost={"wood": 90, "stone": 100, "iron": 140, "food": 80},
        base_upgrade_minutes=4,
        description="Улучшает оружие и броню для всех типов войск.",
    ),
    "mason": BuildingDefinition(
        code="mason",
        name="Каменотёс",
        max_level=18,
        base_upgrade_cost={"wood": 70, "stone": 140, "iron": 85, "food": 70},
        base_upgrade_minutes=3,
        description="Увеличивает добычу и эффективность обработки камня.",
    ),
}


def calculate_upgrade_cost(definition: BuildingDefinition, current_level: int) -> ResourceCost:
    # Cost scales by current level, making late upgrades progressively more expensive.
    factor = 1.35 ** (current_level - 1)
    return {
        "wood": int(definition.base_upgrade_cost["wood"] * factor),
        "stone": int(definition.base_upgrade_cost["stone"] * factor),
        "iron": int(definition.base_upgrade_cost["iron"] * factor),
        "food": int(definition.base_upgrade_cost["food"] * factor),
    }


def calculate_upgrade_minutes(definition: BuildingDefinition, current_level: int) -> int:
    factor = 1.25 ** (current_level - 1)
    return int(definition.base_upgrade_minutes * factor)


def format_cost(cost: ResourceCost) -> str:
    return (
        f"Дерево: {cost['wood']} | Камень: {cost['stone']} | "
        f"Железо: {cost['iron']} | Еда: {cost['food']}"
    )


def format_duration(seconds: int) -> str:
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}ч {minutes}м {secs}с"
    if minutes:
        return f"{minutes}м {secs}с"
    return f"{secs}с"
