# Telegram Subscription Tracker Bot

Личный Telegram-бот для учёта платных подписок: напоминания о списаниях, история
платежей, сводка расходов по валютам и категориям, экспорт CSV и резервные копии
SQLite-базы. Реализация следует техническому заданию
`telegram_subscription_tracker_bot_spec.md`.

## Возможности

- ➕ Добавление подписки через пошаговый диалог (FSM).
- 📋 Список с фильтрами по статусу (`active` / `paused` / `cancelled` / `archived`)
  и пагинацией.
- 📅 Ближайшие списания на 30 дней.
- 📊 Сводка: эквивалент в месяц и в год по каждой валюте, разбивка по категориям.
- 💳 Отметка оплаты: автоматический сдвиг даты списания для периодических
  подписок; для `вручную` — запрос новой даты.
- 🕘 История платежей по подписке.
- ⏸ / ❌ / 📦 Приостановка, отмена и архивирование.
- ✏ Редактирование любого поля через инлайн-меню.
- ⏰ Ежедневные напоминания за N дней до списания + оповещения о просрочке.
  Дедупликация через таблицу `reminder_logs`.
- 🗂 Категории (ИИ / работа / видео / музыка / VPN / облако / хостинг / игры /
  образование / другое).
- 📤 Экспорт CSV: подписки и платежи.
- 📦 Резервная копия базы данных (файл `subscriptions_YYYY-MM-DD_HH-MM.db`).
- ⚙ Просмотр настроек (`TIMEZONE`, `REMINDER_DAYS`, `LOG_LEVEL`, …).
- 🔐 Доступ только владельцу (`ADMIN_TELEGRAM_ID`).

## Стек

- Python 3.12+
- aiogram 3 (long polling)
- SQLAlchemy 2 + SQLite
- APScheduler (AsyncIOScheduler)
- pydantic + pydantic-settings
- uv (менеджер пакетов)
- pytest, ruff — тесты и линтер

## Структура проекта

```text
app/
  main.py                     # точка входа
  config/settings.py          # .env → pydantic Settings
  logging/setup.py            # rotating file logger + token masking
  database/                   # engine, модели, репозитории
  services/                   # subscription / payment / reminder / report / export / backup
  scheduler/jobs.py           # APScheduler cron @ 09:00 local TZ
  bot/
    filters.py                # AdminFilter
    handlers/                 # start, subscriptions, payments, settings, reports, export
    keyboards/                # reply и inline клавиатуры
    states/                   # FSM-состояния
  utils/                      # dates, money, validators, formatters
data/    logs/    exports/    backups/   (runtime-артефакты, в git не коммитятся)
tests/                        # pytest (63 теста)
```

## Установка и запуск на Windows 11

### 1. Установите `uv` (один раз)

```powershell
pip install uv
# или, если установлен winget:
winget install --id=astral-sh.uv
```

### 2. Склонируйте репозиторий и подготовьте `.env`

```powershell
git clone https://github.com/perejaslav/telegram_subscription_tracker_bot.git
cd telegram_subscription_tracker_bot
Copy-Item .env.example .env
notepad .env
```

Заполните в `.env`:

```env
BOT_TOKEN=1234567890:AAF...               # выдаёт @BotFather в Telegram
ADMIN_TELEGRAM_ID=123456789               # свой числовой Telegram ID
TIMEZONE=Europe/Istanbul                  # ваш IANA TZ
REMINDER_DAYS=1,3,7                       # за сколько дней слать напоминания
DATABASE_URL=sqlite:///data/subscriptions.db
LOG_LEVEL=INFO
```

> Чтобы узнать свой Telegram ID, напишите боту
> [@userinfobot](https://t.me/userinfobot) или [@RawDataBot](https://t.me/RawDataBot).

### 3. Установите зависимости

```powershell
uv sync
```

`uv` сам подтянет интерпретатор, указанный в `.python-version`, и создаст
`.venv/`.

### 4. Запустите бота

```powershell
uv run python -m app.main
```

В Telegram напишите боту `/start` — появится главное меню.

Чтобы остановить бота, нажмите `Ctrl+C` в окне терминала.

## Сценарии использования

| Действие | Кнопка в меню |
|---|---|
| Добавить подписку | ➕ Добавить подписку |
| Посмотреть список | 📋 Мои подписки (фильтры по статусам) |
| Отметить оплату | 💳 Отметить оплату → выбор подписки → подтверждение |
| Посмотреть историю | 🕘 История платежей → выбор подписки |
| Ближайшие списания | 📅 Ближайшие списания |
| Сводка расходов | 📊 Сводка |
| Категории | 🗂 Категории → выбор категории |
| Архив | 📦 Архив |
| Настройки | ⚙ Настройки |
| Экспорт | 📤 Экспорт → Подписки / Платежи / Бэкап |

## Запуск тестов

```powershell
uv run pytest
```

Покрытие:

- `tests/test_validators.py` — валидация полей, `shift_date` для месяца/года/недели/квартала, граничные даты (31 января → 28/29 февраля).
- `tests/test_subscription_service.py` — CRUD, валидация, смена статуса, удаление.
- `tests/test_payment_service.py` — отметка оплаты, сдвиг даты для всех периодов, архивная защита, история.
- `tests/test_reminder_service.py` — окно напоминаний, дедуп, просрочка, игнор `paused`.
- `tests/test_report_service.py` — сводка по валютам и категориям, ближайшие списания, экспорт CSV, разрешение коллизий имён.

## Стиль кода

```powershell
uv run ruff check .
uv run ruff format .
```

## Хранение данных

- `data/subscriptions.db` — SQLite база.
- `logs/app.log` — логи (ротация 1 МБ × 3, токен и приватные URL маскируются).
- `exports/subscriptions_YYYY-MM-DD.csv` — экспорт подписок.
- `exports/payments_YYYY-MM-DD.csv` — экспорт платежей.
- `backups/subscriptions_YYYY-MM-DD_HH-MM.db` — резервные копии.

Все эти каталоги создаются автоматически и не коммитятся (см. `.gitignore`).

## Безопасность

- Токен бота и `ADMIN_TELEGRAM_ID` хранятся в `.env` и не попадают в логи.
- Любой пользователь, чей Telegram ID не совпадает с `ADMIN_TELEGRAM_ID`,
  получает сообщение «⛔ Доступ запрещён» и не может читать данные.
- В логах маскируются `bot:<TOKEN>` и приватные query-параметры URL
  (`token=`, `access_token=`, `sid=`, `api_key=`, `password=`).

## Лицензия

Личный проект; используйте на свой страх и риск. Бот не хранит банковские
реквизиты и не имеет доступа к платёжным системам.