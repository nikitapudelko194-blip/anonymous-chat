# 💬 Обработка чата - НОВОЕ ОБНОВЛЕНиЕ

## 🚀 Что ановено

🌟 **Обмен сообщениями** между пользователями  
🟶 **Кнопки действий** в чате (оценка, жалоба, завершение)  
💾 **Сохранение данных** в SQLite базе  

---

## 👥 Архитектура Обмена

### Цыкл обмена:

```
Пользователь 1 (Пишет)
    ↓
Внести сообщение
    ↓
Сохранить в БД
    ↓
Отправить Пользователю 2
    ↓
Пользователь 2 (Получает + Кнопки)
```

### Код доставки:

```python
async def handle_chat_message(message: Message, state: FSMContext):
    # 1. Получить данные сессии
    data = await state.get_data()
    chat_id = data.get('chat_id')
    partner_id = data.get('partner_id')
    
    # 2. Сохранить в БД
    db.save_message(chat_id, message.from_user.id, message.text)
    
    # 3. Отправить собеседнику
    await message.bot.send_message(
        partner_id,
        f"💬 **Собеседник:** {message.text}",
        reply_markup=get_chat_actions_keyboard()  # НОВО!
    )
```

---

## ⭐ Кнопки действия в чате

### Дизайн:

```
Каждое сообщение от собеседника + 3 кнопки:

💬 **Собеседник:** Привет, как дела?
[⭐ Оценить]
[🚫 Жалоба]
[🛑 Завершить чат]
```

### Код клавиатуры:

```python
def get_chat_actions_keyboard():
    """Кнопки активности в чате"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Оценить", callback_data="rate_user")],
        [InlineKeyboardButton(text="🚫 Жалоба", callback_data="report_user")],
        [InlineKeyboardButton(text="🛑 Завершить чат", callback_data="end_chat")],
    ])
```

---

## ⭐ Оценка собеседника

### Флоу:

```
Пользователь нажымает ⭐ Оценить
    ↓
Диалог выбора рейтинга (1-5 звезд)
    ↓
Оценка сохраняется в памяти
    ↓
Чат автоматически завершается
    ↓
Вернуться на основное меню
```

### Код:

```python
async def handle_rate_user(callback: CallbackQuery, state: FSMContext):
    """Обработать клик на кнопку оценки"""
    # Показываем опции 1-5 звезд
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data="rating_5")],
        [InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data="rating_4")],
        [InlineKeyboardButton(text="⭐⭐⭐", callback_data="rating_3")],
        [InlineKeyboardButton(text="⭐⭐", callback_data="rating_2")],
        [InlineKeyboardButton(text="⭐", callback_data="rating_1")],
    ])
    
    await callback.message.edit_text(
        "⭐ Оцените общение:",
        reply_markup=kb
    )
```

---

## 🚫 Жалоба на собеседника

### Причины:

```
[🚫 Спам]
[😤 Оскорбление]
[🔞 Неприличный контент]
[😠 Домогательство]
[❌ Другое]
```

### После отправки:

```python
async def handle_report_reason(callback: CallbackQuery, state: FSMContext):
    # 1. Сохранить жалобу в БД
    db.save_report(
        chat_id,
        reporter_id,      # Кто стукал
        reported_user_id, # На кого
        reason            # Почему
    )
    
    # 2. Дорнуть чат
    db.end_chat(chat_id)
    
    # 3. Вернуть на главное меню
    await callback.message.edit_text(
        "✅ Жалоба дошла",
        reply_markup=get_main_menu()
    )
```

---

## 🛑 Завершение чата

### Процесс:

```python
async def handle_end_chat(callback: CallbackQuery, state: FSMContext):
    # 1. Маркировать как 'ended'
    db.end_chat(chat_id)
    
    # 2. Очистить FSM стейт
    await state.clear()
    
    # 3. Показать главное меню
    await callback.message.edit_text(
        "Хотите найти нового собеседника?",
        reply_markup=get_main_menu()
    )
```

---

## 💾 База данных

### Таблицы:

#### `messages`
```sql
id          INTEGER PRIMARY KEY
chat_id     TEXT            -- "усер_1_user_2"
sender_id   INTEGER         -- Кто писал
ресснент      TEXT            -- "Привет!"
created_at  DATETIME        -- 2025-12-28 13:06:00
```

#### `chats`
```sql
chat_id    TEXT PRIMARY KEY  -- "user1_user2"
user1_id   INTEGER           -- 123
user2_id   INTEGER           -- 456
category   TEXT              -- "random"
status     TEXT              -- "active" / "ended"
created_at DATETIME          -- Когда начался
ended_at   DATETIME          -- Когда закончился
```

#### `reports`
```sql
id                INTEGER PRIMARY KEY
chat_id           TEXT       -- "усер_1_user_2"
reporter_id       INTEGER    -- Кто стукал
reported_user_id  INTEGER    -- На кого
reason            TEXT       -- "spam", "abuse", etc
created_at        DATETIME   -- Когда жалоба
```

---

## 🚀 Запуск и тестирование

### Старт:

```bash
python -m bot.main
```

### Проверка:

```bash
python test_imports.py
```

### Тест с двумя учетными записями:

1. Откройте Telegram и нажмите /start в разных аккаунтах
2. Заполните профили
3. Нажмите "🔍 Найти собеседника"
4. Напишите сообщение
5. Должно прийти к другому
6. Оцените / наржалуйте / закончите

---

## 📨 Гайды

📝 [FEATURES.md](FEATURES.md) - Основные функции
🔧 [RUN_FROM_ROOT.md](RUN_FROM_ROOT.md) - Как запустить
🧪 [test_imports.py](test_imports.py) - Проверка модулей
🔌 [IMPORT_FIX_SUMMARY.md](IMPORT_FIX_SUMMARY.md) - Отладка

---

## 🌟 Конфигурация

Если вы хотите изменить кнопки:

1. Откройте `bot/main.py`
2. Найдите `def get_chat_actions_keyboard()`
3. Обновите текст или нажмите `callback_data`
4. Обновите обработчики та же и добавьте `dp.callback_query.register(handler, F.data == "...")`

---

✅ **Архитектура готова к выпуску!**
