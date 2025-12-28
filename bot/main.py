import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters.command import Command

from bot.config import BOT_TOKEN, DB_PATH
from bot.database.db import Database
from bot.keyboards.main import get_main_menu, get_gender_keyboard, get_search_category_keyboard
from bot.states.user_states import UserStates
from bot.utils.matching import find_match
from bot.utils.ban import is_user_banned
from bot.utils.notifications import notify_match_found, notify_ban

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Initialize database
db = Database()


async def cmd_start(message: Message, state: FSMContext):
    """
    Команда /start
    """
    user_id = message.from_user.id
    
    # Проверить бан
    is_banned = await is_user_banned(user_id, db)
    if is_banned:
        user = await db.get_user(user_id)
        ban_info = f"\n⏰ Она-блокировка: {user['ban_expires_at']}"
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
            "👋 Надорвитесь, это вип проект\n\n"
            "🤨 Надо полнить профиль"
        )
        
        # Какое это на ум
        await message.answer(
            "👥 Какой оно у нас\u0433о?",
            reply_markup=get_gender_keyboard()
        )
        
        await state.set_state(UserStates.waiting_gender)
    else:
        # Показать основное меню
        await message.answer(
            f"👋 Ладно, {user['first_name'] or 'Оно'}!",
            reply_markup=get_main_menu()
        )


async def handle_gender_selection(callback: CallbackQuery, state: FSMContext):
    """
    Обработка выбора пола.
    """
    gender = callback.data.split('_')[1]
    
    await db.update_user(callback.from_user.id, gender=gender)
    await callback.answer()
    
    await callback.message.edit_text(
        "🎂 Всюту мне возраст?",
        reply_markup=None
    )
    
    await state.set_state(UserStates.waiting_age)


async def handle_age_input(message: Message, state: FSMContext):
    """
    Обработка ввода возраста.
    """
    try:
        age = int(message.text)
        if age < 13 or age > 120:
            await message.answer("❌ Возраст должен быть от 13 до 120")
            return
        
        await db.update_user(message.from_user.id, age=age)
        
        await message.answer(
            "🌟 Какие о тебя интересы?\n\n"
            "напиши выкорми чем дели (раздели запятою)",
        )
        
        await state.set_state(UserStates.waiting_interests)
    except ValueError:
        await message.answer("❌ Конный возраст, нужно число")


async def handle_interests_input(message: Message, state: FSMContext):
    """
    Обработка ввода интересов.
    """
    interests = message.text
    
    await db.update_user(message.from_user.id, interests=interests)
    
    await message.answer(
        "📕 Напиши о себе что-нибудь",
    )
    
    await state.set_state(UserStates.waiting_bio)


async def handle_bio_input(message: Message, state: FSMContext):
    """
    Обработка ввода био.
    """
    bio = message.text
    
    await db.update_user(message.from_user.id, bio=bio)
    
    await message.answer(
        "✅ Порфиль выполнен! Это на це\n\n",
        reply_markup=get_main_menu()
    )
    
    await state.clear()


async def cmd_search(callback: CallbackQuery, state: FSMContext):
    """
    Начать поиск.
    """
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
        "🔍 Выберите категорию поиска:",
        reply_markup=get_search_category_keyboard()
    )
    
    await state.set_state(UserStates.choosing_category)


async def handle_category_selection(callback: CallbackQuery, state: FSMContext):
    """
    Обработка выбора категории.
    """
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
            "😟 Собеседников не найдено. Попробуйте позже.",
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
        "🎆 Матч найден! Начинайте насным сообщениями!"
    )
    
    await state.set_state(UserStates.in_chat)
    await state.update_data(current_chat=chat_id, other_user=match_id)


async def main():
    """
    Основная функция запуска бота.
    """
    # Инициализация БД
    await db.init_db()
    
    # Создание бота
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.MARKDOWN
        )
    )
    
    # Создание диспетчера
    dp = Dispatcher()
    
    # регистрация обработчиков
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_age_input, UserStates.waiting_age)
    dp.message.register(handle_interests_input, UserStates.waiting_interests)
    dp.message.register(handle_bio_input, UserStates.waiting_bio)
    
    dp.callback_query.register(handle_gender_selection, F.data.startswith("gender_"))
    dp.callback_query.register(cmd_search, F.data == "search_start")
    dp.callback_query.register(handle_category_selection, F.data.startswith("category_"))
    
    # запуск поллинга
    try:
        logger.info("🚀 Бот запущен")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
