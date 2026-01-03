#!/usr/bin/env python3
"""Entry point для запуска бота."""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from bot.config import BOT_TOKEN
from bot.handlers.start import router as start_router
from bot.handlers.chat import router as chat_router
from bot.middleware.throttle import ThrottleMiddleware

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def set_commands(bot: Bot):
    """Установить команды бота."""
    commands = [
        BotCommand(command="start", description="🚀 Начать"),
        BotCommand(command="help", description="ℹ️ Помощь"),
        BotCommand(command="stop", description="🛑 Остановить чат"),
    ]
    await bot.set_my_commands(commands)

async def main():
    """Главная функция запуска."""
    # Инициализация бота и диспетчера
    bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
    dp = Dispatcher()
    
    # Регистрация middleware
    dp.message.middleware(ThrottleMiddleware())
    
    # Регистрация роутеров
    dp.include_router(start_router)
    dp.include_router(chat_router)
    
    # Установка команд
    await set_commands(bot)
    
    logger.info("🚀 Бот запущен")
    
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("🛑 Бот остановлен")

if __name__ == "__main__":
    asyncio.run(main())
