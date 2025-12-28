import asyncio
import logging
import sys
import os
from collections import defaultdict

# Добавить родительскую директорию в path для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters.command import Command
from datetime import datetime
import sqlite3

from config import BOT_TOKEN, DB_PATH

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

# 🔄 Глобальная очередь для поиска пара
waiting_users = defaultdict(list)  # category -> [user_ids]
active_chats = {}  # user_id -> {partner_id, chat_id}

# Initialize database
class Database:
    def __init__(self):
        self.db_path = DB_PATH
    
    async def init_db(self):
        """Инициализировать базу данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Создать таблицу пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    gender TEXT,
                    age INTEGER,
                    interests TEXT,
                    bio TEXT,
                    is_premium BOOLEAN DEFAULT 0,
                    is_banned BOOLEAN DEFAULT 0,
                    ban_reason TEXT,
                    ban_expires_at DATETIME,
                    chats_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Создать таблицу чатов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id TEXT PRIMARY KEY,
                    user1_id INTEGER NOT NULL,
                    user2_id INTEGER NOT NULL,
                    category TEXT,
                    status TEXT DEFAULT 'active',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    ended_at DATETIME
                )
            ''')
            
            # Создать таблицу сообщений
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    sender_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chat_id) REFERENCES chats(chat_id)
                )
            ''')
            
            # Создать таблицу жалоб
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    reporter_id INTEGER NOT NULL,
                    reported_user_id INTEGER NOT NULL,
                    reason TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("✅ База данных инициализирована успешно")
        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации БД: {e}", exc_info=True)
    
    def create_user(self, user_id, username, first_name, last_name):
        """Создать нового пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Ошибка при создании пользователя: {e}")
    
    def get_user(self, user_id):
        """Получить пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            user = cursor.fetchone()
            conn.close()
            return dict(user) if user else None
        except Exception as e:
            logger.error(f"❌ Ошибка при получении пользователя: {e}")
            return None
    
    def update_user(self, user_id, **kwargs):
        """Обновить данные пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            fields = ', '.join([f"{k} = ?" for k in kwargs.keys()])
            values = list(kwargs.values()) + [user_id]
            
            cursor.execute(f'UPDATE users SET {fields} WHERE user_id = ?', values)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении пользователя: {e}")
    
    def create_chat(self, user1_id, user2_id, category):
        """Создать новый чат"""
        try:
            chat_id = f"{min(user1_id, user2_id)}_{max(user1_id, user2_id)}"
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO chats (chat_id, user1_id, user2_id, category, status)
                VALUES (?, ?, ?, ?, 'active')
            ''', (chat_id, user1_id, user2_id, category))
            conn.commit()
            conn.close()
            return chat_id
        except Exception as e:
            logger.error(f"❌ Ошибка при создании чата: {e}")
            return None
    
    def save_message(self, chat_id, sender_id, content):
        """Сохранить сообщение в БД"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages (chat_id, sender_id, content)
                VALUES (?, ?, ?)
            ''', (chat_id, sender_id, content))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении сообщения: {e}")
    
    def end_chat(self, chat_id):
        """Завершить чат"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE chats SET status = 'ended', ended_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            ''', (chat_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Ошибка при завершении чата: {e}")
    
    def save_report(self, chat_id, reporter_id, reported_user_id, reason):
        """Сохранить жалобу"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO reports (chat_id, reporter_id, reported_user_id, reason)
                VALUES (?, ?, ?, ?)
            ''', (chat_id, reporter_id, reported_user_id, reason))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении жалобы: {e}")

# States
class UserStates(StatesGroup):
    waiting_gender = State()
    waiting_age = State()
    waiting_interests = State()
    waiting_bio = State()
    choosing_category = State()
    searching = State()
    in_chat = State()

# Initialize
db = Database()
bot_instance = None

# 🔄 Функция поиска пары
async def find_partner(user_id: int, category: str, bot: Bot):
    """Найти партнера для пользователя"""
    global waiting_users, active_chats
    
    # Если уже есть в системе ожидания - удалить
    for cat in waiting_users:
        if user_id in waiting_users[cat]:
            waiting_users[cat].remove(user_id)
    
    # Проверить очередь ожидания для этой категории
    if waiting_users[category]:
        # Есть ожидающие пользователи!
        partner_id = waiting_users[category].pop(0)
        
        # Создать чат
        chat_id = db.create_chat(user_id, partner_id, category)
        
        # Сохранить в активные чаты
        active_chats[user_id] = {'partner_id': partner_id, 'chat_id': chat_id}
        active_chats[partner_id] = {'partner_id': user_id, 'chat_id': chat_id}
        
        logger.info(f"✅ Матч найден: {user_id} <-> {partner_id}")
        
        # Уведомить партнера
        try:
            await bot.send_message(
                partner_id,
                "🎉 Собеседник найден!\n🎉 Можете начать общение:",
                reply_markup=get_chat_actions_keyboard()
            )
        except Exception as e:
            logger.error(f"❌ Не смог уведомить партнера {partner_id}: {e}")
        
        return partner_id
    else:
        # Добавить в очередь ожидания
        waiting_users[category].append(user_id)
        logger.info(f"⏳ {user_id} добавлен в очередь {category}. В очереди: {len(waiting_users[category])}")
        return None

# Keyboards
def get_main_menu():
    """Главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Найти собеседника", callback_data="search_start")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="💎 Премиум", callback_data="premium")],
    ])

def get_search_category_keyboard():
    """Выбор категории поиска"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Случайный", callback_data="category_random")],
        [InlineKeyboardButton(text="👥 По полу", callback_data="category_gender")],
        [InlineKeyboardButton(text="❤️ По интересам", callback_data="category_interests")],
        [InlineKeyboardButton(text="🎂 По возрасту", callback_data="category_age")],
    ])

def get_chat_actions_keyboard():
    """Кнопки действий в чате (БЕЗ РЕЙТИНГА!)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Жалоба", callback_data="report_user")],
        [InlineKeyboardButton(text="🚪 Завершить чат", callback_data="end_chat")],
    ])

def get_report_reasons_keyboard():
    """Кнопки выбора причины жалобы"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Спам", callback_data="report_spam")],
        [InlineKeyboardButton(text="😤 Оскорбление", callback_data="report_abuse")],
        [InlineKeyboardButton(text="🔞 Контент", callback_data="report_inappropriate")],
        [InlineKeyboardButton(text="😠 Домогательство", callback_data="report_harassment")],
        [InlineKeyboardButton(text="❌ Другое", callback_data="report_other")],
    ])

# Handlers
async def cmd_start(message: Message, state: FSMContext):
    """Команда /start"""
    try:
        user_id = message.from_user.id
        user = db.get_user(user_id)
        
        if not user:
            # Создать нового пользователя
            db.create_user(
                user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name
            )
            logger.info(f"✨ Новый пользователь создан: {user_id}")
        
        # Отправить главное меню (без регистрации!)
        await message.answer(
            f"👋 Привет, {message.from_user.first_name or 'друг'}!\n\n"
            "🎉 Добро пожаловать в Анонимный Чат!\n\n"
            "Найди интересного собеседника и начни общение 📬",
            reply_markup=get_main_menu()
        )
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка в cmd_start: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")

async def handle_profile(callback: CallbackQuery, state: FSMContext):
    """Показать профиль пользователя"""
    try:
        user_id = callback.from_user.id
        user = db.get_user(user_id)
        
        if user:
            profile_text = (
                f"👤 **Ваш профиль:**\n\n"
                f"**Имя:** {user['first_name'] or 'Не указано'}\n"
                f"**Пол:** {user['gender'] or 'Не указано'}\n"
                f"**Возраст:** {user['age'] or 'Не указано'}\n"
                f"**Интересы:** {user['interests'] or 'Не указаны'}\n"
                f"**О себе:** {user['bio'] or 'Не указано'}\n\n"
                f"**Чатов:** {user['chats_count']}"
            )
        else:
            profile_text = "❌ Профиль не найден"
        
        await callback.message.edit_text(
            profile_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Редактировать профиль", callback_data="edit_profile")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
            ])
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

async def handle_edit_profile(callback: CallbackQuery, state: FSMContext):
    """Редактировать профиль"""
    try:
        await callback.message.edit_text(
            "📝 Редактирование профиля\n\n"
            "Выберите, что хотите изменить:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👨 Пол", callback_data="edit_gender")],
                [InlineKeyboardButton(text="🎂 Возраст", callback_data="edit_age")],
                [InlineKeyboardButton(text="❤️ Интересы", callback_data="edit_interests")],
                [InlineKeyboardButton(text="📝 О себе", callback_data="edit_bio")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
            ])
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_edit_gender(callback: CallbackQuery, state: FSMContext):
    """Изменить пол"""
    try:
        await callback.message.edit_text(
            "👨 Выберите ваш пол:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👨 Мужчина", callback_data="set_gender_male")],
                [InlineKeyboardButton(text="👩 Женщина", callback_data="set_gender_female")],
                [InlineKeyboardButton(text="🤷 Другое", callback_data="set_gender_other")],
            ])
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_set_gender(callback: CallbackQuery, state: FSMContext):
    """Установить пол"""
    try:
        gender = callback.data.split('_')[2]
        db.update_user(callback.from_user.id, gender=gender)
        
        await callback.message.edit_text(
            f"✅ Пол установлен: {gender}\n\n"
            "Что дальше?",
            reply_markup=get_main_menu()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_edit_age(callback: CallbackQuery, state: FSMContext):
    """Изменить возраст"""
    try:
        await callback.message.edit_text("🎂 Напишите ваш возраст:")
        await state.set_state(UserStates.waiting_age)
        await callback.answer()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_age_input(message: Message, state: FSMContext):
    """Обработать ввод возраста"""
    try:
        age = int(message.text)
        if age < 13 or age > 120:
            await message.answer("❌ Возраст должен быть от 13 до 120 лет")
            return
        
        db.update_user(message.from_user.id, age=age)
        await message.answer(
            f"✅ Возраст установлен: {age}",
            reply_markup=get_main_menu()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_edit_interests(callback: CallbackQuery, state: FSMContext):
    """Изменить интересы"""
    try:
        await callback.message.edit_text("❤️ Напишите ваши интересы (через запятую):")
        await state.set_state(UserStates.waiting_interests)
        await callback.answer()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_interests_input(message: Message, state: FSMContext):
    """Обработать ввод интересов"""
    try:
        db.update_user(message.from_user.id, interests=message.text)
        await message.answer(
            f"✅ Интересы обновлены",
            reply_markup=get_main_menu()
        )
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_edit_bio(callback: CallbackQuery, state: FSMContext):
    """Изменить биографию"""
    try:
        await callback.message.edit_text("📝 Напишите о себе:")
        await state.set_state(UserStates.waiting_bio)
        await callback.answer()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_bio_input(message: Message, state: FSMContext):
    """Обработать ввод биографии"""
    try:
        db.update_user(message.from_user.id, bio=message.text)
        await message.answer(
            f"✅ Биография обновлена",
            reply_markup=get_main_menu()
        )
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def cmd_search(callback: CallbackQuery, state: FSMContext):
    """Начать поиск собеседника"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "🔍 Выберите категорию поиска:",
            reply_markup=get_search_category_keyboard()
        )
        await state.set_state(UserStates.choosing_category)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_category_selection(callback: CallbackQuery, state: FSMContext):
    """Обработать выбор категории"""
    global bot_instance
    try:
        user_id = callback.from_user.id
        category = callback.data.split('_')[1]
        
        await callback.answer()
        await callback.message.edit_text("🔍 Ищем собеседника...")
        
        # Найти партнера
        partner_id = await find_partner(user_id, category, bot_instance)
        
        if partner_id:
            # Партнер найден!
            chat_id = active_chats[user_id]['chat_id']
            
            await callback.message.edit_text(
                "🎉 Собеседник найден!\n📬 Начните общение:",
                reply_markup=get_chat_actions_keyboard()
            )
            
            await state.set_state(UserStates.in_chat)
            await state.update_data(
                chat_id=chat_id,
                partner_id=partner_id,
                category=category
            )
        else:
            # В очереди ожидания
            await callback.message.edit_text(
                "⏳ Вы в очереди ожидания\n"
                "Когда найдется партнер, вы получите уведомление\n\n"
                "[Отмена]",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_search")],
                ])
            )
            await state.set_state(UserStates.searching)
            await state.update_data(category=category)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

async def handle_chat_message(message: Message, state: FSMContext):
    """Обработать сообщение в чате"""
    global bot_instance
    try:
        data = await state.get_data()
        chat_id = data.get('chat_id')
        partner_id = data.get('partner_id')
        user_id = message.from_user.id
        
        if not chat_id or not partner_id:
            await message.answer(
                "❌ Ошибка: чат не найден. Начните заново.",
                reply_markup=get_main_menu()
            )
            return
        
        # Сохранить сообщение
        db.save_message(chat_id, user_id, message.text)
        
        # Отправить партнеру
        try:
            await bot_instance.send_message(
                partner_id,
                f"💬 Собеседник: {message.text}",
                reply_markup=get_chat_actions_keyboard()
            )
            logger.info(f"✅ Сообщение от {user_id} отправлено {partner_id}")
        except Exception as send_error:
            logger.error(f"❌ Ошибка при отправке сообщения партнеру: {send_error}")
            await message.answer(
                "⚠️ Собеседник недоступен или заблокировал бота.",
                reply_markup=get_chat_actions_keyboard()
            )
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_chat_message: {e}", exc_info=True)

async def handle_report_user(callback: CallbackQuery, state: FSMContext):
    """Начать жалобу"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "📋 Выберите причину жалобы:",
            reply_markup=get_report_reasons_keyboard()
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_report_reason(callback: CallbackQuery, state: FSMContext):
    """Обработать жалобу"""
    try:
        reason = callback.data.split('_')[1]
        data = await state.get_data()
        
        chat_id = data.get('chat_id')
        partner_id = data.get('partner_id')
        reporter_id = callback.from_user.id
        
        # Сохранить жалобу
        db.save_report(chat_id, reporter_id, partner_id, reason)
        db.end_chat(chat_id)
        
        # Очистить активный чат
        active_chats.pop(reporter_id, None)
        active_chats.pop(partner_id, None)
        
        await callback.answer("✅ Жалоба отправлена. Спасибо!", show_alert=True)
        await callback.message.edit_text(
            "✅ Жалоба получена. Спасибо за помощь!\n\n"
            "Хотите найти нового собеседника?",
            reply_markup=get_main_menu()
        )
        
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_end_chat(callback: CallbackQuery, state: FSMContext):
    """Завершить чат"""
    try:
        data = await state.get_data()
        chat_id = data.get('chat_id')
        partner_id = data.get('partner_id')
        user_id = callback.from_user.id
        
        db.end_chat(chat_id)
        
        # Очистить активный чат
        active_chats.pop(user_id, None)
        active_chats.pop(partner_id, None)
        
        await callback.answer("✅ Чат завершен", show_alert=True)
        await callback.message.edit_text(
            "👋 Спасибо за общение!\n\n"
            "Хотите найти нового собеседника?",
            reply_markup=get_main_menu()
        )
        
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_cancel_search(callback: CallbackQuery, state: FSMContext):
    """Отменить поиск"""
    global waiting_users
    try:
        data = await state.get_data()
        category = data.get('category')
        user_id = callback.from_user.id
        
        # Удалить из очереди
        if category and user_id in waiting_users[category]:
            waiting_users[category].remove(user_id)
            logger.info(f"❌ {user_id} отменил поиск в {category}")
        
        await callback.answer("Поиск отменен")
        await callback.message.edit_text(
            "Поиск отменен",
            reply_markup=get_main_menu()
        )
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Вернуться в главное меню"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "👋 Главное меню",
            reply_markup=get_main_menu()
        )
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def main():
    """
    Основная функция запуска бота.
    """
    global bot_instance
    try:
        logger.info("🚀 Инициализация бота 'Анонимный Чат'...")
        
        # Инициализация БД
        logger.info("📁 Инициализация базы данных...")
        await db.init_db()
        
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
        bot_instance = bot
        logger.info("✅ Бот создан успешно")
        
        # Создание диспетчера
        logger.info("📧 Создание диспетчера...")
        dp = Dispatcher()
        
        # Регистрация обработчиков
        logger.info("🔌 Подключение маршрутов...")
        
        dp.message.register(cmd_start, Command("start"))
        dp.callback_query.register(handle_profile, F.data == "profile")
        dp.callback_query.register(handle_edit_profile, F.data == "edit_profile")
        dp.callback_query.register(handle_edit_gender, F.data == "edit_gender")
        dp.callback_query.register(handle_set_gender, F.data.startswith("set_gender_"))
        dp.callback_query.register(handle_edit_age, F.data == "edit_age")
        dp.callback_query.register(handle_edit_interests, F.data == "edit_interests")
        dp.callback_query.register(handle_edit_bio, F.data == "edit_bio")
        dp.message.register(handle_age_input, UserStates.waiting_age)
        dp.message.register(handle_interests_input, UserStates.waiting_interests)
        dp.message.register(handle_bio_input, UserStates.waiting_bio)
        dp.callback_query.register(cmd_search, F.data == "search_start")
        dp.callback_query.register(handle_category_selection, F.data.startswith("category_"))
        dp.message.register(handle_chat_message, UserStates.in_chat)
        dp.callback_query.register(handle_report_user, F.data == "report_user")
        dp.callback_query.register(handle_report_reason, F.data.startswith("report_"))
        dp.callback_query.register(handle_end_chat, F.data == "end_chat")
        dp.callback_query.register(handle_cancel_search, F.data == "cancel_search")
        dp.callback_query.register(handle_back_to_menu, F.data == "back_to_menu")
        
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
        logger.info("🚪 Закрытие соединения с ботом...")
        await bot.session.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️  Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}", exc_info=True)
        sys.exit(1)
