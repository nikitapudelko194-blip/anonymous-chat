import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен в переменных окружения!")
    print("📝 Создайте файл .env в корне проекта с содержимым:")
    print("BOT_TOKEN=your_token_here")
    sys.exit(1)

BOT_NAME = 'Anonymous Chat'
ADMIN_ID = os.getenv('ADMIN_ID', None)

# Database
DATABASE_URL = 'sqlite:///chat_bot.db'
DB_PATH = os.getenv('DATABASE_PATH', 'chat_bot.db')

# Проверка пути БД
try:
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
except Exception as e:
    print(f"⚠️ Ошибка при создании директории БД: {e}")

# Подписка (AnonRuBot Style)
SUBSCRIPTION_COST_MONTHLY = int(os.getenv('SUBSCRIPTION_COST_MONTHLY', 79))  # Telegram Stars за месяц
SUBSCRIPTION_COST_LIFETIME = int(os.getenv('SUBSCRIPTION_COST_LIFETIME', 699))  # Telegram Stars навсегда

# Платные функции (только фильтр по полу)
PREMIUM_FEATURES = {
    'gender_filter': True,  # Требует обязательную подписку
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
