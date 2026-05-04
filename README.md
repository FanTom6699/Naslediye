# Система зданий для существующего Telegram MMO-бота

Модуль реализован на **Python + aiogram** с хранением данных в **SQLite**.

## Что реализовано

- Архитектура на модулях (модели зданий, сервис логики, БД, Telegram handlers).
- Все здания из ТЗ:
  - Ратуша
  - Казарма
  - Конюшня
  - Академия магов
  - Склад
  - Караульная башня
  - Центр разведки
  - Военный штаб
  - Школа магии
  - Кузница
  - Каменотёс
- Для каждого здания есть:
  - название
  - стартовый уровень (1)
  - максимальный уровень
  - стоимость улучшения (дерево/камень/железо/еда)
  - время улучшения
  - описание
- Поведение:
  - улучшение здания
  - проверка ресурсов
  - списание ресурсов при старте улучшения
  - таймер улучшения
  - повышение уровня после таймера
  - сохранение состояния в SQLite
- Telegram интерфейс:
  - команда `/buildings`
  - список зданий
  - кнопки `[Улучшить]` и `[Информация]`

## Установка зависимостей

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Создайте `.env` на основе `.env.example`:

```env
BOT_TOKEN=ваш_токен_бота
```

## Подключение в уже существующий проект

В точке инициализации, где у вас уже есть `Dispatcher`, подключите модуль:

```python
from bot import register_buildings_module

# dp - уже существующий Dispatcher
register_buildings_module(dp, db_path="game.db")
```

Подключение WebApp-карты:

```python
from bot import register_world_module

# dp - уже существующий Dispatcher
register_world_module(
  dp,
  webapp_url="https://your-domain.example/webapp/index.html",
  world_objects_path="webapp/world_objects.json",
)
```

Важно:
- Новый экземпляр `Bot` не создается.
- Новый экземпляр `Dispatcher` не создается.
- Фоновый воркер таймеров стартует и останавливается через `dispatcher.startup/shutdown`.

## WebApp-кнопка "🌍 Мир"

Кнопка создается в модуле [handlers/world.py](handlers/world.py) через `KeyboardButton` + `WebAppInfo`.

## Файлы карты

- `webapp/index.html` - разметка WebApp.
- `webapp/styles.css` - стили интерфейса и сетки 25x25.
- `webapp/app.js` - рендер объектов, обработка кликов, `Telegram.WebApp.sendData()`.
- `webapp/world_objects.json` - данные объектов карты (координаты и типы).
- `webapp/assets/map-bg.svg` - фоновая карта.

## Формат данных из WebApp

WebApp отправляет JSON в бот:

```json
{
  "action": "attack",
  "x": 10,
  "y": 5
}
```

Поддерживаемые действия: `attack`, `scout`, `gather`.

## Структура

- `bot.py` - функция `register_buildings_module(...)` для встраивания в текущий `Dispatcher`.
- `game/buildings.py` - объектная модель зданий и формулы стоимости/времени.
- `game/database.py` - слой SQLite.
- `game/service.py` - игровая логика (апгрейд, проверки, завершение таймеров).
- `game/keyboards.py` - inline-клавиатуры.
- `handlers/buildings.py` - `/buildings` и callback-обработчики.
- `handlers/world.py` - `/world`, кнопка WebApp и прием данных из WebApp.
- `game/world_service.py` - валидация payload и обработка действий по объекту карты.

## Как расширять

- Добавить новое здание: запись в `BUILDINGS` и код в `BUILDINGS_ORDER`.
- Добавить эффекты зданий: расширить `BuildingService` (например, бонусы к добыче/армии).
- Перейти на JSON-хранилище: реализовать новый класс БД с тем же интерфейсом, что `GameDatabase`.
