import asyncio
import logging
import sys
import os
from collections import defaultdict
from datetime import datetime, timedelta
import sqlite3
import uuid

# Добавить родительскую директорию в path для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters.command import Command

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
active_chats = {}  # user_id -> {partner_id, chat_id, search_filters}
user_states = {}  # user_id -> FSMContext state data
# НОВОЕ: Хранилище для FSM контекстов (для отправки уведомлений партнёру)
user_fsm_contexts = {}  # user_id -> FSMContext
user_voted = {}  # user_id -> {chat_id} - кто уже оценил кого

# Database
class Database:
    def __init__(self):
        self.db_path = DB_PATH
    
    async def init_db(self):
        """Инициализировать базу данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Таблица пользователей (обновлена)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    gender TEXT,
                    age INTEGER,
                    interests TEXT,
                    is_premium BOOLEAN DEFAULT 0,
                    premium_expires_at DATETIME,
                    is_banned BOOLEAN DEFAULT 0,
                    ban_reason TEXT,
                    ban_expires_at DATETIME,
                    chats_count INTEGER DEFAULT 0,
                    positive_votes INTEGER DEFAULT 0,
                    negative_votes INTEGER DEFAULT 0,
                    reports_count INTEGER DEFAULT 0,
                    rating REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'offline',
                    last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица чатов
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
            
            # Таблица сообщений
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
            
            # Таблица жалоб
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
            
            # Таблица оценок (НОВАЯ)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS votes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    voter_id INTEGER NOT NULL,
                    votee_id INTEGER NOT NULL,
                    chat_id TEXT NOT NULL,
                    vote_type TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица платежей (НОВАЯ)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount INTEGER,
                    plan TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("✅ База данных инициализирована успешно")
        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации БД: {e}", exc_info=True)
    
    def create_user(self, user_id, username, first_name):
        """Создать нового пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name)
                VALUES (?, ?, ?)
            ''', (user_id, username, first_name))
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
            chat_id = str(uuid.uuid4())
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO chats (chat_id, user1_id, user2_id, category, status)
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
    
    def save_vote(self, voter_id, votee_id, chat_id, vote_type):
        """Сохранить оценку (НОВАЯ)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO votes (voter_id, votee_id, chat_id, vote_type)
                VALUES (?, ?, ?, ?)
            ''', (voter_id, votee_id, chat_id, vote_type))
            
            # Обновить счётчик оценок
            if vote_type == 'positive':
                cursor.execute('UPDATE users SET positive_votes = positive_votes + 1 WHERE user_id = ?', (votee_id,))
            else:
                cursor.execute('UPDATE users SET negative_votes = negative_votes + 1 WHERE user_id = ?', (votee_id,))
            
            # Пересчитать рейтинг
            cursor.execute('''
                SELECT positive_votes, negative_votes FROM users WHERE user_id = ?
            ''', (votee_id,))
            result = cursor.fetchone()
            if result:
                positive, negative = result
                total = positive + negative
                rating = (positive / total * 100) if total > 0 else 0
                cursor.execute('UPDATE users SET rating = ? WHERE user_id = ?', (rating, votee_id))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении оценки: {e}")
    
    def set_premium(self, user_id, days):
        """Установить премиум (НОВАЯ)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            expires_at = datetime.now() + timedelta(days=days)
            cursor.execute('''
                UPDATE users SET is_premium = 1, premium_expires_at = ?
                WHERE user_id = ?
            ''', (expires_at, user_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Ошибка при установке премиума: {e}")
    
    def check_premium(self, user_id):
        """Проверить премиум статус (НОВАЯ)"""
        try:
            user = self.get_user(user_id)
            if not user:
                return False
            
            if not user['is_premium']:
                return False
            
            if user['premium_expires_at']:
                expires = datetime.fromisoformat(user['premium_expires_at'])
                if expires < datetime.now():
                    self.update_user(user_id, is_premium=False)
                    return False
            
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке премиума: {e}")
            return False

# FSM States
class UserStates(StatesGroup):
    waiting_gender = State()
    waiting_age = State()
    choosing_interests = State()
    choosing_search_filters = State()
    in_chat = State()
    waiting_rating = State()
    selecting_premium_plan = State()

# Initialize
db = Database()
bot_instance = None

# 🔄 Функция поиска пары
async def find_partner(user_id: int, category: str, search_filters: dict, bot: Bot, state: FSMContext):
    """Найти партнера для пользователя"""
    global waiting_users, active_chats, user_fsm_contexts
    
    # Очистить из других категорий
    for cat in waiting_users:
        if user_id in waiting_users[cat]:
            waiting_users[cat].remove(user_id)
    
    # Проверить очередь ожидания
    if waiting_users[category]:
        partner_id = waiting_users[category].pop(0)
        
        # Проверить фильтры
        partner = db.get_user(partner_id)
        
        # Если есть фильтр по полу, проверить
        if search_filters.get('gender') and search_filters['gender'] != 'any':
            if partner['gender'] != search_filters['gender']:
                # Вернуть обратно в очередь
                waiting_users[category].append(partner_id)
                # Добавить текущего в очередь
                waiting_users[category].append(user_id)
                return None, None
        
        # Создать чат
        chat_id = db.create_chat(user_id, partner_id, category)
        
        # Сохранить в активные чаты
        active_chats[user_id] = {'partner_id': partner_id, 'chat_id': chat_id}
        active_chats[partner_id] = {'partner_id': user_id, 'chat_id': chat_id}
        
        logger.info(f"✅ Матч найден: {user_id} <-> {partner_id}")
        
        # ИСПРАВЛЕНИЕ: Уведомить партнёра с кнопками (обновить его состояние)
        if partner_id in user_fsm_contexts:
            partner_state = user_fsm_contexts[partner_id]
            await partner_state.set_state(UserStates.in_chat)
            await partner_state.update_data(chat_id=chat_id, partner_id=user_id, category=category)
            
            # Отправить уведомление партнёру
            try:
                await bot.send_message(
                    partner_id,
                    "🎉 **Собеседник найден!**\n\n💬 Введите сообщение и отправьте его:",
                    reply_markup=get_chat_actions_keyboard()
                )
                logger.info(f"✅ Партнёр {partner_id} уведомлен о подключении к {user_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка при уведомлении партнёра: {e}")
        
        return partner_id, chat_id
    else:
        # Добавить в очередь
        waiting_users[category].append(user_id)
        logger.info(f"⏳ {user_id} добавлен в очередь {category}. В очереди: {len(waiting_users[category])}")
        return None, None

# ============= KEYBOARDS (НОВОЕ ОФОРМЛЕНИЕ) =============

def get_main_menu():
    """Главное меню как в @AnonRuBot"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Поиск собеседника", callback_data="search_start")],
        [InlineKeyboardButton(text="👤 Поиск по полу", callback_data="search_gender")],
        [InlineKeyboardButton(text="💬 Выбрать интересы", callback_data="choose_interests")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="💎 Стать VIP", callback_data="vip_select")],
        [InlineKeyboardButton(text="📋 Правила чата", callback_data="rules")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
    ])

def get_search_filters_keyboard():
    """Выбор фильтров для поиска"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨 Только парни", callback_data="filter_male")],
        [InlineKeyboardButton(text="👩 Только девушки", callback_data="filter_female")],
        [InlineKeyboardButton(text="🤷 Без разницы", callback_data="filter_any")],
    ])

def get_interests_keyboard():
    """Выбор интересов"""
    interests = [
        ("🎮 Игры", "games"),
        ("🎬 Фильмы", "movies"),
        ("🎵 Музыка", "music"),
        ("📚 Книги", "books"),
        ("💪 Спорт", "sports"),
        ("🎨 Искусство", "art"),
        ("🍕 Кулинария", "food"),
        ("✈️ Путешествия", "travel"),
        ("💼 Работа", "work"),
        ("💗 Отношения", "dating"),
    ]
    
    keyboard = []
    for text, callback in interests:
        keyboard.append([InlineKeyboardButton(text=text, callback_data=f"interest_{callback}")])
    
    keyboard.append([InlineKeyboardButton(text="✅ Готово", callback_data="interests_done")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_chat_actions_keyboard():
    """Кнопки во время чата (как в @AnonRuBot)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Спам и реклама", callback_data="report_spam")],
        [InlineKeyboardButton(text="❌ Пошлый собеседник", callback_data="report_inappropriate")],
        [InlineKeyboardButton(text="⚠️ Пожаловаться", callback_data="report_user")],
        [InlineKeyboardButton(text="❌ Завершить чат", callback_data="end_chat")],
    ])

def get_rating_keyboard():
    """Кнопки оценки в конце чата"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👍 Нравится", callback_data="vote_positive"), 
         InlineKeyboardButton(text="👎 Не нравится", callback_data="vote_negative")],
        [InlineKeyboardButton(text="➡️ Новый диалог", callback_data="search_start")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")],
    ])

def get_vip_plans_keyboard():
    """VIP планы"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 7 дней за 250", callback_data="vip_7days")],
        [InlineKeyboardButton(text="⭐ 1 месяц за 350", callback_data="vip_1month")],
        [InlineKeyboardButton(text="⭐ 1 год за 500", callback_data="vip_1year")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
    ])

# ============= HANDLERS =============

async def cmd_start(message: Message, state: FSMContext):
    """Команда /start"""
    global user_fsm_contexts
    try:
        user_id = message.from_user.id
        user = db.get_user(user_id)
        
        # ИСПРАВЛЕНИЕ: Сохранить контекст FSM для доступа из других функций
        user_fsm_contexts[user_id] = state
        
        if not user:
            db.create_user(user_id, message.from_user.username, message.from_user.first_name)
            logger.info(f"✨ Новый пользователь: {user_id}")
        
        await message.answer(
            f"👋 Привет, {message.from_user.first_name or 'друг'}!\n\n"
            "🎭 **Добро пожаловать в Анонимный Чат Telegram!**\n\n"
            "Здесь можно найти интересного собеседника и общаться анонимно 💬\n\n"
            "✨ Полная конфиденциальность\n"
            "🔒 Безопасность гарантирована\n"
            "🌟 Много интересных людей\n\n"
            "**📚 Доступные команды:**\n"
            "`/search` - начать поиск собеседника\n"
            "`/next` - новый диалог (если уже в чате)\n"
            "`/stop` - завершить текущий диалог\n"
            "`/me` - поделиться своим профилем\n"
            "`/start` - главное меню\n\n"
            "**📸 В диалоге можно делиться:**\n"
            "📷 Фотографиями\n"
            "🎞 Голосовыми сообщениями\n"
            "👽 Стикерами\n\n"
            "**Выберите действие:**",
            reply_markup=get_main_menu()
        )
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка в cmd_start: {e}", exc_info=True)

async def cmd_search(message: Message, state: FSMContext):
    """Команда /search - начать поиск"""
    global user_fsm_contexts
    try:
        user_id = message.from_user.id
        user = db.get_user(user_id)
        
        user_fsm_contexts[user_id] = state
        
        if user_id in active_chats:
            await message.answer("⚠️ Вы уже в чате! Используйте /stop чтобы завершить.")
            return
        
        # Проверить бан
        if user['is_banned']:
            if user['ban_expires_at']:
                expires = datetime.fromisoformat(user['ban_expires_at'])
                if expires > datetime.now():
                    await message.answer(f"❌ Вы заблокированы до {expires.strftime('%d.%m')}")
                    return
            else:
                await message.answer("❌ Вы заблокированы")
                return
        
        await message.answer("⏳ Ищем собеседника...\n\n⏰ Это может занять несколько секунд")
        
        partner_id, chat_id = await find_partner(user_id, 'random', {}, bot_instance, state)
        
        if partner_id:
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=chat_id, partner_id=partner_id, category='random')
            
            await message.answer(
                "🎉 **Собеседник найден!**\n\n"
                "💬 Введите сообщение и отправьте его:",
                reply_markup=get_chat_actions_keyboard()
            )
        else:
            await message.answer(
                "⏳ **Вы в очереди ожидания...**\n\n"
                "Когда найдется собеседник, вы получите уведомление.\n"
                "Используйте /stop чтобы отменить поиск."
            )
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=None, partner_id=None, category='random')
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def cmd_next(message: Message, state: FSMContext):
    """Команда /next - начать новый диалог сразу"""
    global active_chats, bot_instance, user_fsm_contexts
    try:
        user_id = message.from_user.id
        data = await state.get_data()
        partner_id = data.get('partner_id')
        chat_id = data.get('chat_id')
        
        # Завершить текущий чат
        if chat_id and partner_id:
            db.end_chat(chat_id)
            active_chats.pop(user_id, None)
            active_chats.pop(partner_id, None)
            
            # Уведомить партнёра
            try:
                await bot_instance.send_message(
                    partner_id,
                    "❌ Собеседник начал новый диалог.\n\n"
                    "⭐ **Оцените его/её:**",
                    reply_markup=get_rating_keyboard()
                )
            except:
                pass
        
        await state.clear()
        user_fsm_contexts[user_id] = state
        
        await message.answer("⏳ Ищем нового собеседника...")
        
        partner_id, chat_id = await find_partner(user_id, 'random', {}, bot_instance, state)
        
        if partner_id:
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=chat_id, partner_id=partner_id, category='random')
            
            await message.answer(
                "🎉 **Собеседник найден!**\n\n"
                "💬 Введите сообщение и отправьте его:",
                reply_markup=get_chat_actions_keyboard()
            )
        else:
            await message.answer(
                "⏳ **Вы в очереди ожидания нового собеседника...**\n\n"
                "Используйте /stop чтобы отменить."
            )
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=None, partner_id=None, category='random')
    except Exception as e:
        logger.error(f"❌ Ошибка в cmd_next: {e}")

async def cmd_stop(message: Message, state: FSMContext):
    """Команда /stop - завершить диалог"""
    global active_chats, bot_instance, waiting_users
    try:
        user_id = message.from_user.id
        data = await state.get_data()
        partner_id = data.get('partner_id')
        chat_id = data.get('chat_id')
        category = data.get('category')
        
        # Если в чате
        if chat_id and partner_id:
            db.end_chat(chat_id)
            active_chats.pop(user_id, None)
            active_chats.pop(partner_id, None)
            
            # Уведомить партнёра
            try:
                await bot_instance.send_message(
                    partner_id,
                    "❌ Собеседник завершил чат.\n\n"
                    "⭐ **Оцените его/её:**",
                    reply_markup=get_rating_keyboard()
                )
            except:
                pass
            
            await message.answer(
                "✅ Чат завершен!\n\n"
                "⭐ **Оцените собеседника:**",
                reply_markup=get_rating_keyboard()
            )
        elif category and user_id in waiting_users[category]:
            # Если в очереди
            waiting_users[category].remove(user_id)
            await message.answer(
                "❌ Поиск отменён.\n\n"
                "Вы вышли из очереди.",
                reply_markup=get_main_menu()
            )
        else:
            await message.answer(
                "ℹ️ Вы не в чате и не в очереди.",
                reply_markup=get_main_menu()
            )
        
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка в cmd_stop: {e}")

async def cmd_me(message: Message, state: FSMContext):
    """Команда /me - отправить ссылку на свой аккаунт"""
    try:
        user_id = message.from_user.id
        data = await state.get_data()
        partner_id = data.get('partner_id')
        
        # Получить информацию пользователя
        user = db.get_user(user_id)
        
        # Формируем профиль
        gender = {'male': '👨', 'female': '👩', 'other': '🤷'}.get(user['gender'], '❓')
        
        profile_text = (
            f"{gender} **{user['first_name'] or 'Аноним'}**\n\n"
            f"🔗 **Telegram:** @{message.from_user.username or 'username_not_set'}\n"
            f"📱 **ID:** `{user_id}`\n"
            f"⭐ **Рейтинг:** {user['rating']:.1f}%\n"
            f"👍 **Нравится:** {user['positive_votes']}\n"
            f"👎 **Не нравится:** {user['negative_votes']}\n\n"
            f"_Скопируйте ссылку чтобы обмениваться контактами_"
        )
        
        if partner_id and user_id in active_chats:
            # Если в чате - отправить партнёру
            try:
                await bot_instance.send_message(
                    partner_id,
                    profile_text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✍️ Ответить", callback_data="send_profile")]
                    ])
                )
                await message.answer("✅ Профиль отправлен собеседнику!")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки профиля: {e}")
                await message.answer("❌ Ошибка при отправке профиля.")
        else:
            # Если не в чате - показать свой профиль
            await message.answer(
                profile_text + "\n\n_Это ваш профиль. Используйте эту команду во время чата чтобы поделиться им._"
            )
    except Exception as e:
        logger.error(f"❌ Ошибка в cmd_me: {e}")

# ИСПРАВЛЕННЫЕ ОБРАБОТЧИКИ ДЛЯ ПОДДЕРКИ МЕДИА

async def handle_chat_message(message: Message, state: FSMContext):
    """Обработать сообщение в чате (текст, фото, голос, стикер)"""
    global bot_instance, active_chats, user_fsm_contexts
    try:
        user_id = message.from_user.id
        data = await state.get_data()
        chat_id = data.get('chat_id')
        partner_id = data.get('partner_id')
        
        if not chat_id or not partner_id or user_id not in active_chats:
            await message.answer(
                "❌ Чат не найден или завершен.\n\n"
                "Начните новый поиск:",
                reply_markup=get_main_menu()
            )
            await state.clear()
            return
        
        if partner_id not in active_chats or active_chats[partner_id].get('chat_id') != chat_id:
            await message.answer(
                "❌ Собеседник завершил чат.\n\n"
                "Начните новый поиск:",
                reply_markup=get_main_menu()
            )
            await state.clear()
            active_chats.pop(user_id, None)
            return
        
        # Обработать повторно - сохраним сообщение в БД
        if message.text:
            db.save_message(chat_id, user_id, message.text)
        elif message.photo:
            db.save_message(chat_id, user_id, f"[📷 Фото]")
        elif message.voice:
            db.save_message(chat_id, user_id, f"[🎞 Голос]")
        elif message.sticker:
            db.save_message(chat_id, user_id, f"[👽 Стикер]")
        
        try:
            # Отправить сообщение партнёру РОВНОМ (новым сообщением)
            if message.text:
                # Текстовое сообщение
                await bot_instance.send_message(partner_id, message.text)
                logger.info(f"✅ Текст от {user_id} отправлен {partner_id}")
            elif message.photo:
                # Фотография
                await bot_instance.send_photo(partner_id, message.photo[-1].file_id, caption=message.caption or "📷")
                logger.info(f"✅ Фото от {user_id} отправлена {partner_id}")
            elif message.voice:
                # Голосовое сообщение
                await bot_instance.send_voice(partner_id, message.voice.file_id)
                logger.info(f"✅ Голос от {user_id} отправлен {partner_id}")
            elif message.sticker:
                # Стикер
                await bot_instance.send_sticker(partner_id, message.sticker.file_id)
                logger.info(f"✅ Стикер от {user_id} отправлен {partner_id}")
        except Exception as send_error:
            logger.error(f"❌ Ошибка отправки сообщения партнёру {partner_id}: {send_error}")
            await message.answer("❌ Ошибка отправки сообщения. Возможно, собеседник вышел из чата.")
            db.end_chat(chat_id)
            active_chats.pop(user_id, None)
            active_chats.pop(partner_id, None)
            await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_chat_message: {e}", exc_info=True)

# ============= ОСТАЛЬНЫЕ ОБРАБОТЧИКИ =============

async def cmd_search_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки поиска"""
    global user_fsm_contexts
    try:
        user_id = callback.from_user.id
        user = db.get_user(user_id)
        
        user_fsm_contexts[user_id] = state
        
        if user_id in active_chats:
            await callback.answer("⚠️ Вы уже в чате!", show_alert=True)
            return
        
        if user['is_banned']:
            if user['ban_expires_at']:
                expires = datetime.fromisoformat(user['ban_expires_at'])
                if expires > datetime.now():
                    await callback.answer(f"❌ Вы заблокированы до {expires.strftime('%d.%m')}", show_alert=True)
                    return
            else:
                await callback.answer("❌ Вы заблокированы", show_alert=True)
                return
        
        await callback.answer()
        await callback.message.edit_text("⏳ Ищем собеседника...\n\n⏰ Это может занять несколько секунд")
        
        partner_id, chat_id = await find_partner(user_id, 'random', {}, bot_instance, state)
        
        if partner_id:
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=chat_id, partner_id=partner_id, category='random')
            
            await callback.message.edit_text(
                "🎉 **Собеседник найден!**\n\n"
                "💬 Введите сообщение и отправьте его:",
                reply_markup=get_chat_actions_keyboard()
            )
        else:
            await callback.message.edit_text(
                "⏳ **Вы в очереди ожидания...",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена поиска", callback_data="cancel_search")],
                ])
            )
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=None, partner_id=None, category='random')
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

# ... (Остальные обработчики в другой части файла...)

# Остальное - все аналогичные обработчики
# ... файл есть в GitHub
