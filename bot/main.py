import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import BOT_TOKEN, DB_PATH
from bot.database.db import Database
from bot.middleware.antispam import AntiSpamMiddleware
from bot.middleware.subscription import SubscriptionMiddleware

from bot.handlers.admin import router as admin_router
from bot.handlers.user import router as user_router
from bot.handlers.chat import router as chat_router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler('bot.log', encoding='utf-8')]
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("🚀 Запуск Anonymous Chat Bot")
    
    db = Database(DB_PATH)
    await db.init_db()
    
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    
    # Регистрация базы данных во все хендлеры
    dp.workflow_data.update({"db": db})
    
    # Подключение middleware
    dp.message.middleware(AntiSpamMiddleware(db=db))
    dp.update.middleware(SubscriptionMiddleware(db=db, bot=bot))
    
    # Подключение роутеров
    dp.include_router(admin_router)
    dp.include_router(user_router)
    dp.include_router(chat_router)
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
