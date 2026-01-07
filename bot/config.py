import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Bot token from .env
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Database path
DB_PATH = os.getenv('DATABASE_PATH', 'chat_bot.db')

# Admin ID (optional)
ADMIN_ID = os.getenv('ADMIN_ID')

# Subscription costs (in rubles)
SUBSCRIPTION_COST_MONTHLY = int(os.getenv('SUBSCRIPTION_COST_MONTHLY', 99))
SUBSCRIPTION_COST_LIFETIME = int(os.getenv('SUBSCRIPTION_COST_LIFETIME', 499))

# Validate configuration
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен в .env файле!")

print("✅ Конфигурация загружена успешно")
