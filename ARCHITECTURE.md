# Архитектура Telegram Бота "Анонимный Чат" (AnonRuBot Style)

## 📋 Структура проекта

```
anonymous-chat-telegram/
├── bot/
│   ├── __init__.py
│   ├── main.py                    # Точка входа бота
│   ├── config.py                  # Конфигурация и константы
│   ├── database/
│   │   ├── __init__.py
│   │   ├── db.py                  # Управление БД
│   │   └── models.py              # ORM модели
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py               # Стартовые команды
│   │   ├── auth.py                # Минимальная регистрация
│   │   ├── chat.py                # Основной чат
│   │   ├── subscription.py        # Подписка и платежи
│   │   └── admin.py               # Админ функции
│   ├── states/
│   │   ├── __init__.py
│   │   └── user_states.py         # FSM состояния
│   ├── keyboards/
│   │   ├── __init__.py
│   │   └── main.py                # Основные кнопки
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── matching.py            # Алгоритм поиска собеседника
│   │   ├── payment.py             # Работа с платежами (Telegram Stars)
│   │   ├── ban.py                 # Система банов
│   │   └── notifications.py       # Уведомления
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── logging.py             # Логирование
│   └── filters/
│       ├── __init__.py
│       └── custom_filters.py      # Пользовательские фильтры
├── logs/
│   └── bot.log
├── requirements.txt
├── .env.example
└── README.md
```

## 📦 Необходимые библиотеки

```
aiogram==3.4.1
python-dotenv==1.0.0
aiohttp==3.9.0
sqlalchemy==2.0.25
```

## 🗄️ Структура БД (SQLite)

### Таблица: users

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,  -- Telegram ID
    username TEXT,
    first_name TEXT,
    gender TEXT,  -- 'male', 'female', 'other'
    age INTEGER,
    is_premium BOOLEAN DEFAULT 0,
    premium_expires_at DATETIME,
    
    -- Статистика
    chats_count INTEGER DEFAULT 0,
    reports_count INTEGER DEFAULT 0,
    
    -- Бан
    is_banned BOOLEAN DEFAULT 0,
    ban_reason TEXT,
    ban_expires_at DATETIME,
    
    -- Статус
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Таблица: chats

```sql
CREATE TABLE chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT UNIQUE NOT NULL,
    user1_id INTEGER NOT NULL,
    user2_id INTEGER NOT NULL,
    
    category TEXT,  -- 'random', 'gender'
    
    status TEXT DEFAULT 'active',  -- 'active', 'ended', 'reported'
    reports_count INTEGER DEFAULT 0,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME
);
```

### Таблица: messages

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NOT NULL,
    
    content TEXT NOT NULL,
    message_type TEXT DEFAULT 'text',  -- 'text', 'photo', 'video'
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(chat_id)
);
```

### Таблица: subscriptions

```sql
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    subscription_type TEXT,  -- 'monthly', 'lifetime'
    
    purchase_amount REAL,  -- в рублях или Telegram Stars
    payment_method TEXT,  -- 'telegram_stars', 'card'
    
    purchased_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
```

### Таблица: bans_log

```sql
CREATE TABLE bans_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    
    ban_type TEXT,  -- 'report_based', 'admin', 'violation'
    reason TEXT,
    reports_count INTEGER,  -- Количество жалоб
    
    ban_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
```

### Таблица: reports

```sql
CREATE TABLE reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL,
    
    reporter_id INTEGER NOT NULL,  -- Кто пожаловался
    reported_user_id INTEGER NOT NULL,  -- На кого пожаловались
    
    reason TEXT,  -- 'spam', 'abuse', 'harassment', 'inappropriate'
    description TEXT,
    
    status TEXT DEFAULT 'pending',  -- 'pending', 'reviewed', 'resolved'
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (chat_id) REFERENCES chats(chat_id)
);
```

## ⚙️ Основной конфиг (config.py)

```python
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
BOT_TOKEN = os.getenv('BOT_TOKEN')
BOT_NAME = 'Anonymous Chat'

# Database
DATABASE_URL = 'sqlite:///chat_bot.db'
DB_PATH = 'chat_bot.db'

# Подписка (как в AnonRuBot)
SUBSCRIPTION_COST_MONTHLY = 79  # Telegram Stars за месяц
SUBSCRIPTION_COST_LIFETIME = 699  # Telegram Stars навсегда

# Платные функции
PREMIUM_FEATURES = {
    'gender_filter': True,  # ДЛЯ ВСЕХ (нужна подписка)
}

# Системные константы
MAX_REPORTS_FOR_BAN = 5  # Количество жалоб для автоматического бана
BAN_DURATION = 7 * 24 * 3600  # 7 дней в секундах

# Категории поиска (только 2)
CATEGORIES = [
    ('🎲 Случайный', 'random'),
    ('👥 По полу (💎 премиум)', 'gender'),
]

# Причины жалоб
REPORT_REASONS = [
    ('🚫 Спам', 'spam'),
    ('😤 Оскорбление', 'abuse'),
    ('🔞 Неприличный контент', 'inappropriate'),
    ('😠 Домогательство', 'harassment'),
    ('❌ Другое', 'other'),
]

# Полы
GENDERS = [
    ('👨 Мужчина', 'male'),
    ('👩 Женщина', 'female'),
    ('🤷 Другое', 'other'),
]
```

## 🔐 Система состояний (states/user_states.py)

```python
from aiogram.fsm.state import State, StatesGroup

class UserStates(StatesGroup):
    # Регистрация (минимальная)
    waiting_gender = State()
    waiting_age = State()
    
    # Поиск собеседника
    choosing_category = State()
    searching = State()
    
    # Чат
    in_chat = State()
    
    # Жалоба
    report_reason = State()
```

## 🔄 Алгоритм поиска собеседника (utils/matching.py)

```python
import random
from typing import Optional
from database.db import Database

async def find_match(
    user_id: int,
    category: str,
    gender_filter: Optional[str] = None
) -> Optional[int]:
    """
    Поиск собеседника по категории (упрощённый).
    
    Args:
        user_id: ID пользователя
        category: 'random' или 'gender'
        gender_filter: Предпочитаемый пол (для премиум)
    
    Returns:
        ID найденного собеседника или None
    """
    db = Database()
    user_profile = await db.get_user(user_id)
    
    if not user_profile:
        return None
    
    # Получить всех активных пользователей
    all_users = await db.get_all_active_users(exclude_id=user_id)
    
    if not all_users:
        return None
    
    candidates = all_users
    
    if category == 'random':
        # Полностью случайный выбор
        return random.choice(candidates)['user_id']
    
    elif category == 'gender' and gender_filter:
        # Фильтр по полу (платная функция)
        candidates = [
            u for u in candidates 
            if u['gender'] == gender_filter
        ]
        if not candidates:
            return None
        return random.choice(candidates)['user_id']
    
    return None
```

## 💰 Система платежей (utils/payment.py)

```python
from aiogram.types import LabeledPrice
from config import SUBSCRIPTION_COST_MONTHLY, SUBSCRIPTION_COST_LIFETIME

def get_subscription_invoice(
    subscription_type: str,
    chat_id: int
) -> tuple[list[LabeledPrice], int]:
    """
    Получить детали счета для подписки.
    
    Args:
        subscription_type: 'monthly' или 'lifetime'
        chat_id: ID чата для платежа
    
    Returns:
        Кортеж (цены, итоговая сумма в копейках)
    """
    
    if subscription_type == 'monthly':
        prices = [
            LabeledPrice(label="Подписка на месяц", amount=SUBSCRIPTION_COST_MONTHLY * 100)
        ]
        total = SUBSCRIPTION_COST_MONTHLY * 100
    
    elif subscription_type == 'lifetime':
        prices = [
            LabeledPrice(label="Пожизненная подписка", amount=SUBSCRIPTION_COST_LIFETIME * 100)
        ]
        total = SUBSCRIPTION_COST_LIFETIME * 100
    
    else:
        return [], 0
    
    return prices, total
```

## 🚫 Система банов (utils/ban.py)

```python
from datetime import datetime, timedelta
from config import BAN_DURATION
from database.db import Database

async def check_and_apply_ban(user_id: int, db: Database):
    """Проверить количество жалоб и применить бан если нужно."""
    
    user = await db.get_user(user_id)
    
    if user['reports_count'] >= 5:
        # Бан на неделю
        ban_expires = datetime.now() + timedelta(seconds=BAN_DURATION)
        await db.ban_user(
            user_id,
            reason='Слишком много жалоб',
            expires_at=ban_expires
        )
        return True
    
    return False

async def auto_unban_expired(db: Database):
    """Автоматически разбанить пользователей по истечению времени."""
    expired_bans = await db.get_expired_bans()
    
    for ban in expired_bans:
        await db.unban_user(ban['user_id'])
```

## 🔔 Система уведомлений (utils/notifications.py)

```python
from aiogram import Bot
from config import BOT_TOKEN

async def notify_match_found(
    user1_id: int,
    user2_id: int,
    user1_profile: dict,
    user2_profile: dict
):
    """Уведомить обоих пользователей о найденном матче."""
    bot = Bot(token=BOT_TOKEN)
    
    msg1 = f"""
🎉 Вы нашли собеседника!

👤 {user2_profile['first_name']}, {user2_profile['age']} лет

💬 Можете начать писать сообщения
    """
    
    msg2 = f"""
🎉 Вы нашли собеседника!

👤 {user1_profile['first_name']}, {user1_profile['age']} лет

💬 Можете начать писать сообщения
    """
    
    await bot.send_message(user1_id, msg1)
    await bot.send_message(user2_id, msg2)

async def notify_ban(user_id: int, reason: str, expires_at: str):
    """Уведомить пользователя о бане."""
    bot = Bot(token=BOT_TOKEN)
    
    msg = f"""
🚫 Вы заблокированы

**Причина:** {reason}
**Разблокировка:** {expires_at}

Чтобы разблокироваться раньше, купите премиум подписку ✨
    """
    
    await bot.send_message(user_id, msg)
```

## 🔑 Ключевые функции

### ✅ Реализованные функции (AnonRuBot Style)
- ✨ Минимальная регистрация (пол + возраст)
- 🔍 Поиск собеседника по 2 категориям (случайный, по полу)
- 💬 Анонимный чат между пользователями
- 💳 Платная подписка (фильтр по полу требует премиум)
- 📊 Отслеживание статистики (только чаты и жалобы)
- 🚫 Система жалоб с автоматическим баном после 5 жалоб
- ⏰ Бан на 7 дней с возможностью разбана через премиум подписку
- 🔐 Система модерации и безопасности

### 🎯 Денежные потоки (AnonRuBot Style)
1. **Премиум подписка** (Telegram Stars):
   - Месячная: 79 Stars (~€0.80)
   - Пожизненная: 699 Stars (~€7.00)

2. **Включенные преимущества:**
   - ✨ Поиск по полу собеседника
   - ⚡ Больше ничего (максимальная простота)

3. **Разбан при автоматическом бане:**
   - Ждать 7 дней
   - ИЛИ купить премиум подписку

## 📈 Масштабируемость

- **Асинхронная архитектура** (asyncio)
- **FSM для управления состояниями**
- **Модульная структура** для легкого расширения
- **Готовность к миграции на PostgreSQL**

---

**Архитектура переработана под AnonRuBot style: максимальная простота и минимальный функционал.**
