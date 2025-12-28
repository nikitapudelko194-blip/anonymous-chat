# 🐧 Руководство для разработчиков

## Структура проекта

```
anonymous-chat/
├── bot/
│   ├── __init__.py
│   ├── main.py                    # Основной энтрипойнт бота
│   ├── config.py                  # Конфигурация
│   ├── database/                  # Обработка базы данных
│   ├── handlers/                  # Обработчики команд
│   ├── states/                    # FSM состояния
│   ├── keyboards/                 # Насткатыками
│   ├── utils/                     # Вспомогательные функции
│   ├── middleware/                # Мидлвейры
│   └── filters/                   # Фильтры
├── .env                       # Данные всер (НО учитывать в git)
├── .env.example               # Например .env
├── requirements.txt           # Зависимости
├── README.md                  # Основная документация
├── INSTALLATION.md            # Объявы по инсталлации
└── DEVELOPMENT.md            # Руководство разработчика
```

## Основные модули

### `database/db.py`
Основной класс для работы с SQLite:

```python
from bot.database.db import Database

# Пример использования
db = Database()

# Проинициализировать базу
await db.init_db()

# Получить пользователя
user = await db.get_user(user_id=123456)

# Сохранить сообщение
await db.save_message(
    chat_id="123456_789101",
    sender_id=123456,
    receiver_id=789101,
    content="Привет!",
    message_type="text"
)
```

### `utils/matching.py`

Алгоритм поиска собеседника:

```python
from bot.utils.matching import find_match

# Отыскать собеседника
match_id = await find_match(
    user_id=123456,
    category="random",  # или 'gender', 'interests', 'age'
    gender_filter=None
)

if match_id:
    print(f"Найден собеседник: {match_id}")
else:
    print("Никого не найдено")
```

### `utils/ban.py`

Обработка банов:

```python
from bot.utils.ban import is_user_banned, check_and_apply_ban
from bot.database.db import Database

db = Database()

# Проверить, банен ли пользователь
if await is_user_banned(user_id=123456, db=db):
    print("Пользователь забанен")

# Проверить нарушения и банить если нужно
should_ban = await check_and_apply_ban(user_id=123456, db=db)
```

### `utils/notifications.py`

Отправка уведомлений:

```python
from bot.utils.notifications import notify_match_found, notify_ban
from aiogram import Bot

bot = Bot(token="YOUR_TOKEN")

# Отправить уведомление о найденном матче
await notify_match_found(
    bot=bot,
    user1_id=123456,
    user2_id=789101,
    user1_profile={"first_name": "Олег", "age": 25, ...},
    user2_profile={"first_name": "Виктор", "age": 28, ...}
)

# Отправить уведомление о бане
await notify_ban(
    bot=bot,
    user_id=123456,
    reason="Слишком много жалоб",
    expires_at="через 7 дней"
)
```

## Добавление нового обработчика

### 1. Создать файл `bot/handlers/my_handler.py`

```python
from aiogram import Router, F
from aiogram.types import CallbackQuery

router = Router()

@router.callback_query(F.data == "my_action")
async def handle_my_action(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("Отлично!")
```

### 2. Подключить рамарт в main.py

```python
# В конце bot/main.py

from bot.handlers.my_handler import router as my_router

# Подключить в main():
dp.include_router(my_router)
```

## Вытестирование

### Локальное тестирование

1. Откройте Telegram
2. Найдите вашего бота
3. Напишите `/start`
4. Полоните данные
5. Потестируйте кнопки и жалобы

### Написание unit-тестов

```python
# Например, в tests/test_db.py

import pytest
from bot.database.db import Database

@pytest.mark.asyncio
async def test_create_user():
    db = Database(":memory:")  # в памятя
    await db.init_db()
    
    result = await db.create_user(
        user_id=123456,
        username="test_user",
        first_name="Тест"
    )
    
    assert result == True
    
    user = await db.get_user(123456)
    assert user["user_id"] == 123456
```

## Общие советы

1. **Асинхронность**: Все функци бывают async, не забудьте await

2. **Обработка ошибок**: Всегда снимайте исключения

3. **Логирование**: Оставляйте высокоуровневые данные в логах

4. **Наменование**: Пользуйте snake_case для переменных и функций

5. **Комментария**: Написывайте комментарии на русском
