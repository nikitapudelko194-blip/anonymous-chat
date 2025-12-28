# 🚀 Быстрый настарт Анонимного Чата

📋 Соержание (3 минуты)

## 1️⃣ Клонирование репозитория

```bash
git clone https://github.com/nikitapudelko194-blip/anonymous-chat.git
cd anonymous-chat
```

## 2️⃣ Создание файла .env

Составьте файл `.env` в корне попки:

```bash
echo "BOT_TOKEN=8557377406:AAEcdfAaA0R5L41NB5-kpCOxtPWXfBPDh-U" > .env
echo "DATABASE_PATH=chat_bot.db" >> .env
echo "ADMIN_ID=" >> .env
echo "SUBSCRIPTION_COST_MONTHLY=99" >> .env
echo "SUBSCRIPTION_COST_LIFETIME=499" >> .env
```

или отредактируйте `.env.example` и переименуйте в `.env`:

```bash
cp .env.example .env
```

## 3️⃣ Установка зависимостей

```bash
pip install -r requirements.txt
```

## 4️⃣ Запуск бота

```bash
python -m bot.main
```

если вы увидите в логах:

```
🚀 БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ!
💬 Ожидание входящих сообщений...
```

То все работает! ✨

---

## ♔️ Проверка работы

1. Напишите боту в Telegram: **[@anonymous_chat_bot](https://t.me/anonymous_chat_bot)** (нимли @YourBotName)
2. Напишите `/start`
3. Прокодите регистрацию
4. Начните поиск собеседника

---

## ❌ Ошибки при запуске?

### Ошибка: `TokenValidationError: Token is invalid`

Убедитесь, что:
- Файл `.env` создан в корне проекта
- BOT_TOKEN действительный токен вашего бота

### Ошибка: `ModuleNotFoundError: No module named 'aiogram'`

Установите зависимости:

```bash
pip install -r requirements.txt
```

### Ошибка: `ModuleNotFoundError: No module named 'bot'`

Обычно остановите бот (Ctrl+C) и запустите его нового:

```bash
python -m bot.main
```

---

## 📖 Дополнительная информация

- Полная документация: [README.md](README.md)
- Архитектура: [Посмотреть](docs/ARCHITECTURE.md)
- АПИ: [Посмотреть](docs/API.md)

---

**Отводать вопросы**  
Открытие [Issues](https://github.com/nikitapudelko194-blip/anonymous-chat/issues) и [Discussions](https://github.com/nikitapudelko194-blip/anonymous-chat/discussions)
