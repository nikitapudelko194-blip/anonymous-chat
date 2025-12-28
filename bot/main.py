import asyncio
import logging
import sys
import os

# Добавить родительскую директорию в path для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters.command import Command

from config import BOT_TOKEN, DB_PATH
from database.db import Database
from keyboards.main import get_main_menu, get_gender_keyboard, get_search_category_keyboard
from states.user_states import UserStates
from utils.matching import find_match
from utils.ban import is_user_banned
from utils.notifications import notify_match_found, notify_ban

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Initialize database
db = Database()


async def cmd_start(message: Message, state: FSMContext):
    """
    Команда /start
    """
    try:
        user_id = message.from_user.id
        
        # Проверить бан
        is_banned = await is_user_banned(user_id, db)
        if is_banned:
            user = await db.get_user(user_id)
            ban_info = f"\n⏰ Разблокировка: {user['ban_expires_at']}"
            await message.answer(
                f"🚫 Вы заблокированы\n"
                f"Причина: {user['ban_reason']}{ban_info}\n\n"
                f"💳 Купите премиум для раннего разбана (/premium)"
            )
            return
        
        # Проверить, есть ли в БД
        user = await db.get_user(user_id)
        
        if not user:
            # Новый пользователь - регистрация
            await db.create_user(
                user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name
            )
            
            await message.answer(
                "👋 Привет! Добро пожаловать в Анонимный Чат\n\n"
                "🤨 Давайте заполним ваш профиль"
            )
            
            # Выбор пола
            await message.answer(
                "👥 Какой ваш пол?",
                reply_markup=get_gender_keyboard()
            )
            
            await state.set_state(UserStates.waiting_gender)
        else:
            # Показать основное меню
            await message.answer(
                f"👋 Привет, {user['first_name'] or 'друг'}!",
                reply_markup=get_main_menu()
            )
    except Exception as e:
        logger.error(f"❌ Ошибка в cmd_start: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка. Попробуйте позже."
        )


async def handle_gender_selection(callback: CallbackQuery, state: FSMContext):
    """
    Обработка выбора пола.
    """
    try:
        gender = callback.data.split('_')[1]
        
        await db.update_user(callback.from_user.id, gender=gender)
        await callback.answer()
        
        await callback.message.edit_text(
            "🎂 Сколько вам лет?",
            reply_markup=None
        )
        
        await state.set_state(UserStates.waiting_age)
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_gender_selection: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при выборе пола", show_alert=True)


async def handle_age_input(message: Message, state: FSMContext):
    """
    Обработка ввода возраста.
    """
    try:
        age = int(message.text)
        if age < 13 or age > 120:
            await message.answer("❌ Возраст должен быть от 13 до 120 лет")
            return
        
        await db.update_user(message.from_user.id, age=age)
        
        await message.answer(
            "🌟 Какие ваши интересы?\n\n"
            "Напишите интересы через запятую (например: IT, спорт, кино)",
        )
        
        await state.set_state(UserStates.waiting_interests)
    except ValueError:
        await message.answer(
            "❌ Некорректный возраст, нужно число от 13 до 120"
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_age_input: {e}", exc_info=True)
        await message.answer("❌ Ошибка при обработке возраста")


async def handle_interests_input(message: Message, state: FSMContext):
    """
    Обработка ввода интересов.
    """
    try:
        interests = message.text
        
        await db.update_user(message.from_user.id, interests=interests)
        
        await message.answer(
            "📝 Напишите краткую биографию о себе (опционально)",
        )
        
        await state.set_state(UserStates.waiting_bio)
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_interests_input: {e}", exc_info=True)
        await message.answer("❌ Ошибка при обработке интересов")


async def handle_bio_input(message: Message, state: FSMContext):
    """
    Обработка ввода био.
    """
    try:
        bio = message.text
        
        await db.update_user(message.from_user.id, bio=bio)
        
        await message.answer(
            "✅ Профиль успешно заполнен!\n\n",
            reply_markup=get_main_menu()
        )
        
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_bio_input: {e}", exc_info=True)
        await message.answer("❌ Ошибка при сохранении биографии")


async def cmd_search(callback: CallbackQuery, state: FSMContext):
    """
    Начать поиск собеседника.
    """
    try:
        user_id = callback.from_user.id
        
        # Проверить бан
        is_banned = await is_user_banned(user_id, db)
        if is_banned:
            await callback.answer(
                "🚫 Вы заблокированы!",
                show_alert=True
            )
            return
        
        await callback.answer()
        await callback.message.edit_text(
            "🔍 Выберите категорию поиска собеседника:",
            reply_markup=get_search_category_keyboard()
        )
        
        await state.set_state(UserStates.choosing_category)
    except Exception as e:
        logger.error(f"❌ Ошибка в cmd_search: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при начале поиска", show_alert=True)


async def handle_category_selection(callback: CallbackQuery, state: FSMContext):
    """
    Обработка выбора категории поиска.
    """
    try:
        category = callback.data.split('_')[1]
        
        await callback.answer()
        await callback.message.edit_text(
            "🔍 Ищем собеседника..."
        )
        
        # Найти матч
        match_id = await find_match(
            callback.from_user.id,
            category,
            gender_filter=None
        )
        
        if not match_id:
            await callback.message.edit_text(
                "😔 Собеседников не найдено. Попробуйте позже.",
                reply_markup=get_main_menu()
            )
            await state.clear()
            return
        
        # Сохранить идентификатор чата
        chat_id = f"{callback.from_user.id}_{match_id}"
        await db.create_chat(callback.from_user.id, match_id, category)
        
        # Уведомить обоих
        user1_profile = await db.get_user(callback.from_user.id)
        user2_profile = await db.get_user(match_id)
        
        bot = callback.bot
        await notify_match_found(
            bot,
            callback.from_user.id,
            match_id,
            user1_profile,
            user2_profile
        )
        
        # Обновить статистику
        await db.increment_chats_count(callback.from_user.id)
        await db.increment_chats_count(match_id)
        
        await callback.message.edit_text(
            "🎉 Собеседник найден! Начинайте общаться через сообщения!"
        )
        
        await state.set_state(UserStates.in_chat)
        await state.update_data(current_chat=chat_id, other_user=match_id)
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_category_selection: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при поиске собеседника", show_alert=True)


async def main():
    """
    Основная функция запуска бота.
    """
    try:
        logger.info("🚀 Инициализация бота 'Анонимный Чат'...")
        
        # Инициализация БД
        logger.info("📁 Инициализация базы данных...")
        await db.init_db()
        logger.info("✅ База данных инициализирована успешно")
        
        # Проверка BOT_TOKEN
        if not BOT_TOKEN:
            logger.error("❌ BOT_TOKEN не установлен!")
            raise ValueError("BOT_TOKEN не найден в переменных окружения")
        
        # Создание бота
        logger.info("🤖 Создание экземпляра бота...")
        bot = Bot(
            token=BOT_TOKEN,
            default=DefaultBotProperties(
                parse_mode=ParseMode.MARKDOWN
            )
        )
        logger.info("✅ Бот создан успешно")
        
        # Создание диспетчера
        logger.info("📡 Создание диспетчера...")
        dp = Dispatcher()
        
        # Регистрация обработчиков
        logger.info("🔌 Подключение роутеров...")
        dp.message.register(cmd_start, Command("start"))
        dp.message.register(handle_age_input, UserStates.waiting_age)
        dp.message.register(handle_interests_input, UserStates.waiting_interests)
        dp.message.register(handle_bio_input, UserStates.waiting_bio)
        
        dp.callback_query.register(handle_gender_selection, F.data.startswith("gender_"))
        dp.callback_query.register(cmd_search, F.data == "search_start")
        dp.callback_query.register(handle_category_selection, F.data.startswith("category_"))
        logger.info("  ✓ Все обработчики подключены")
        
        # Запуск поллинга
        logger.info("🚀 БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ!")
        logger.info("💬 Ожидание входящих сообщений...")
        
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        print(f"\n❌ ОШИБКА ЗАПУСКА: {e}")
        print("\n📋 Проверьте:")
        print("  1. Создан ли файл .env в корне проекта")
        print("  2. Указан ли правильный BOT_TOKEN")
        print("  3. Установлены ли все зависимости: pip install -r requirements.txt")
        sys.exit(1)
    finally:
        logger.info("🛑 Закрытие соединения с ботом...")
        await bot.session.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️  Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}", exc_info=True)
        sys.exit(1)
