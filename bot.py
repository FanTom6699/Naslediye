from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aiogram import Dispatcher

from game.database import GameDatabase
from game.service import BuildingService
from game.world_service import WorldService
from handlers.buildings import get_buildings_router
from handlers.world import WorldWebAppConfig, get_world_router


async def upgrades_worker(service: BuildingService, interval_seconds: int = 5) -> None:
    # Background loop finalizes upgrades when their timers expire.
    while True:
        service.process_due_upgrades_for_all()
        await asyncio.sleep(interval_seconds)


@dataclass
class BuildingsModule:
    db: GameDatabase
    service: BuildingService
    worker_task: asyncio.Task[None] | None = None

    async def on_startup(self) -> None:
        if self.worker_task is None or self.worker_task.done():
            self.worker_task = asyncio.create_task(upgrades_worker(self.service))

    async def on_shutdown(self) -> None:
        if self.worker_task is not None:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        self.db.close()


def register_buildings_module(dispatcher: Dispatcher, db_path: str = "game.db") -> BuildingsModule:
    """
    Register buildings feature into an existing aiogram Dispatcher.

    This function does not create Bot/Dispatcher instances and is safe
    for integration in an already deployed project.
    """
    db = GameDatabase(db_path)
    db.init()
    service = BuildingService(db)

    dispatcher.include_router(get_buildings_router(service))
    module = BuildingsModule(db=db, service=service)
    dispatcher.startup.register(module.on_startup)
    dispatcher.shutdown.register(module.on_shutdown)
    return module


def register_world_module(
    dispatcher: Dispatcher,
    webapp_url: str,
    world_objects_path: str = "webapp/world_objects.json",
) -> None:
    """
    Register world WebApp feature into an existing aiogram Dispatcher.

    Parameters:
    - webapp_url: public HTTPS URL to webapp/index.html served on your VPS.
    - world_objects_path: JSON data source used by bot-side action resolver.
    """
    service = WorldService(objects_path=world_objects_path)
    config = WorldWebAppConfig(webapp_url=webapp_url)
    dispatcher.include_router(get_world_router(service, config))
