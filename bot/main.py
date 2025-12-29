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
async def find_partner(user_id: int, category: str, search_filters: dict, bot: Bot):
    """Найти партнера для пользователя"""
    global waiting_users, active_chats
    
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
    """Кнопки во время чата (как в @AnonRuBot) - БЕЗ ОЦЕНОК"""
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
    try:
        user_id = message.from_user.id
        user = db.get_user(user_id)
        
        if not user:
            db.create_user(user_id, message.from_user.username, message.from_user.first_name)
            logger.info(f"✨ Новый пользователь: {user_id}")
        
        await message.answer(
            f"👋 Привет, {message.from_user.first_name or 'друг'}!\n\n"
            "🎭 **Добро пожаловать в Анонимный Чат Telegram!**\n\n"
            "Здесь можно найти интересного собеседника и общаться анонимно 💬\n\n"
            "✨ Полная конфиденциальность\n"
            "🔒 Безопасность гарантирована\n"
            "🌟 Много интересных людей",
            reply_markup=get_main_menu()
        )
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка в cmd_start: {e}", exc_info=True)

async def cmd_search(callback: CallbackQuery, state: FSMContext):
    """Начать поиск (случайный)"""
    try:
        user_id = callback.from_user.id
        user = db.get_user(user_id)
        
        if user_id in active_chats:
            await callback.answer("⚠️ Вы уже в чате!", show_alert=True)
            return
        
        # Проверить бан
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
        
        # Поиск партнера (без фильтров)
        partner_id, chat_id = await find_partner(user_id, 'random', {}, bot_instance)
        
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
                "⏳ **Вы в очереди ожидания...\n\n"
                "Когда найдется собеседник, вы получите уведомление.\n"
                "Пожалуйста, подождите ⏰",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена поиска", callback_data="cancel_search")],
                ])
            )
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=None, partner_id=None, category='random')
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def cmd_search_gender(callback: CallbackQuery, state: FSMContext):
    """Поиск по полу (требует премиум)"""
    try:
        user_id = callback.from_user.id
        is_premium = db.check_premium(user_id)
        
        if not is_premium:
            await callback.answer("💎 Это требует подписку на VIP!", show_alert=True)
            return
        
        await callback.answer()
        await callback.message.edit_text(
            "👤 **Поиск по полу (💎 только для VIP)**\n\n"
            "Выберите, кого вы хотите найти:",
            reply_markup=get_search_filters_keyboard()
        )
        await state.set_state(UserStates.choosing_search_filters)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_search_filter(callback: CallbackQuery, state: FSMContext):
    """Обработать выбор фильтра"""
    try:
        user_id = callback.from_user.id
        filter_type = callback.data.split('_')[1]
        
        await callback.answer()
        await callback.message.edit_text("⏳ Ищем собеседника...\n\n⏰ Это может занять несколько секунд")
        
        # Фильтры поиска
        search_filters = {'gender': filter_type if filter_type != 'any' else 'any'}
        
        partner_id, chat_id = await find_partner(user_id, 'gender', search_filters, bot_instance)
        
        if partner_id:
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=chat_id, partner_id=partner_id, category='gender', filters=search_filters)
            
            await callback.message.edit_text(
                "🎉 **Собеседник найден!**\n\n"
                "💬 Введите сообщение и отправьте его:",
                reply_markup=get_chat_actions_keyboard()
            )
        else:
            await callback.message.edit_text(
                "⏳ **Вы в очереди ожидания...\n\n"
                "Когда найдется собеседник, вы получите уведомление.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_search")],
                ])
            )
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=None, partner_id=None, category='gender', filters=search_filters)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_choose_interests(callback: CallbackQuery, state: FSMContext):
    """Выбрать интересы"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "💬 **Выберите ваши интересы для поиска:**",
            reply_markup=get_interests_keyboard()
        )
        await state.set_state(UserStates.choosing_interests)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_chat_message(message: Message, state: FSMContext):
    """Обработать сообщение в чате"""
    global bot_instance, active_chats
    try:
        user_id = message.from_user.id
        data = await state.get_data()
        chat_id = data.get('chat_id')
        partner_id = data.get('partner_id')
        
        # ИСПРАВЛЕНИЕ: Проверяем наличие активного чата
        if not chat_id or not partner_id or user_id not in active_chats:
            await message.answer(
                "❌ Чат не найден или завершен.\n\n"
                "Начните новый поиск:",
                reply_markup=get_main_menu()
            )
            await state.clear()
            return
        
        # Сохранить сообщение
        db.save_message(chat_id, user_id, message.text)
        
        # Отправить партнеру - ПРОСТОЕ СООБЩЕНИЕ БЕЗ ЛИШНИХ ДАННЫХ
        try:
            await bot_instance.send_message(partner_id, message.text, reply_markup=get_chat_actions_keyboard())
            logger.info(f"✅ Сообщение от {user_id} отправлено {partner_id}")
        except Exception as send_error:
            logger.error(f"❌ Ошибка отправки: {send_error}")
            await message.answer("❌ Ошибка отправки сообщения")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)

async def handle_end_chat(callback: CallbackQuery, state: FSMContext):
    """Завершить чат и показать оценку"""
    global active_chats
    try:
        user_id = callback.from_user.id
        data = await state.get_data()
        partner_id = data.get('partner_id')
        chat_id = data.get('chat_id')
        
        if not partner_id or not chat_id:
            await callback.answer("❌ Ошибка", show_alert=True)
            return
        
        # Завершить чат
        db.end_chat(chat_id)
        
        # Удалить из активных чатов
        active_chats.pop(user_id, None)
        active_chats.pop(partner_id, None)
        
        # Отправить партнёру сообщение что чат завершен
        try:
            await bot_instance.send_message(
                partner_id,
                "❌ Собеседник завершил чат\n\n"
                "Начните новый поиск:",
                reply_markup=get_main_menu()
            )
        except Exception as e:
            logger.error(f"❌ Ошибка при уведомлении партнёра: {e}")
        
        # Показать форму оценки текущему пользователю
        await callback.answer()
        await callback.message.edit_text(
            "⭐ **Оцените собеседника:**\n\n"
            "Ваша оценка помогает улучшать сервис!",
            reply_markup=get_rating_keyboard()
        )
        
        # Очистить состояние
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_vote(callback: CallbackQuery, state: FSMContext):
    """Обработать оценку"""
    try:
        user_id = callback.from_user.id
        vote_type = 'positive' if callback.data == 'vote_positive' else 'negative'
        
        data = await state.get_data()
        partner_id = data.get('partner_id')
        chat_id = data.get('chat_id')
        
        if not partner_id or not chat_id:
            await callback.answer("❌ Данные потеряны", show_alert=True)
            await callback.message.edit_text("Вернитесь в меню:", reply_markup=get_main_menu())
            await state.clear()
            return
        
        # Сохранить оценку
        db.save_vote(user_id, partner_id, chat_id, vote_type)
        
        emoji = "👍" if vote_type == 'positive' else "👎"
        await callback.answer(f"✅ Спасибо за оценку {emoji}!", show_alert=True)
        await callback.message.edit_text(
            "✅ Спасибо за вашу оценку!\n\n"
            "Это помогает нам улучшать сервис.",
            reply_markup=get_main_menu()
        )
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_report_user(callback: CallbackQuery, state: FSMContext):
    """Пожаловаться на собеседника"""
    try:
        reason = callback.data.split('_', 1)[1]
        data = await state.get_data()
        partner_id = data.get('partner_id')
        chat_id = data.get('chat_id')
        user_id = callback.from_user.id
        
        if not partner_id or not chat_id:
            await callback.answer("❌ Ошибка", show_alert=True)
            return
        
        # Сохранить жалобу
        db.save_report(chat_id, user_id, partner_id, reason)
        
        # Увеличить счётчик
        user = db.get_user(partner_id)
        if user:
            reports = user.get('reports_count', 0) + 1
            db.update_user(partner_id, reports_count=reports)
            
            # Автобан при 5+ жалобах
            if reports >= 5:
                expires = datetime.now() + timedelta(days=7)
                db.update_user(partner_id, is_banned=True, ban_expires_at=expires, ban_reason="Слишком много жалоб")
                logger.warning(f"⚠️ {partner_id} заблокирован на 7 дней")
        
        db.end_chat(chat_id)
        active_chats.pop(user_id, None)
        active_chats.pop(partner_id, None)
        
        await callback.answer("✅ Жалоба отправлена!", show_alert=True)
        await callback.message.edit_text(
            "✅ Спасибо за помощь в улучшении сервиса!\n\n"
            "Модераторы рассмотрят вашу жалобу в течение 24 часов.",
            reply_markup=get_main_menu()
        )
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_profile(callback: CallbackQuery, state: FSMContext):
    """Показать профиль"""
    try:
        user_id = callback.from_user.id
        user = db.get_user(user_id)
        
        if not user:
            await callback.answer("❌ Профиль не найден", show_alert=True)
            return
        
        gender_display = {'male': '👨 Мужчина', 'female': '👩 Женщина', 'other': '🤷 Другое'}.get(user['gender'], 'Не указано')
        premium_status = "⭐ VIP" if db.check_premium(user_id) else "📋 Базовый"
        
        profile_text = (
            f"👤 **Ваш профиль:**\n\n"
            f"**Имя:** {user['first_name'] or 'Аноним'}\n"
            f"**Пол:** {gender_display}\n"
            f"**Возраст:** {user['age'] or '?'} лет\n"
            f"**Статус:** {premium_status}\n\n"
            f"**Статистика:**\n"
            f"💬 Чатов: {user['chats_count']}\n"
            f"👍 Положительных оценок: {user['positive_votes']}\n"
            f"👎 Отрицательных оценок: {user['negative_votes']}\n"
            f"⭐ Рейтинг: {user['rating']:.1f}%"
        )
        
        await callback.answer()
        await callback.message.edit_text(
            profile_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Обновить", callback_data="edit_profile")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
            ])
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_edit_gender(callback: CallbackQuery, state: FSMContext):
    """Изменить пол"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "👨 Выберите ваш пол:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👨 Мужчина", callback_data="set_gender_male")],
                [InlineKeyboardButton(text="👩 Женщина", callback_data="set_gender_female")],
                [InlineKeyboardButton(text="🤷 Другое", callback_data="set_gender_other")],
            ])
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_set_gender(callback: CallbackQuery, state: FSMContext):
    """Установить пол"""
    try:
        gender = callback.data.split('_')[2]
        gender_display = {'male': '👨 Мужчина', 'female': '👩 Женщина', 'other': '🤷 Другое'}.get(gender)
        
        db.update_user(callback.from_user.id, gender=gender)
        
        await callback.answer()
        await callback.message.edit_text(
            f"✅ Пол изменён на: {gender_display}\n\n🎂 Теперь укажите ваш возраст:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
            ])
        )
        await state.set_state(UserStates.waiting_age)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_age_input(message: Message, state: FSMContext):
    """Обработать возраст"""
    try:
        age = int(message.text)
        if age < 13 or age > 120:
            await message.answer("❌ Возраст должен быть от 13 до 120 лет")
            return
        
        db.update_user(message.from_user.id, age=age)
        await message.answer(
            f"✅ Возраст установлен: {age} лет",
            reply_markup=get_main_menu()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число")

async def handle_vip_select(callback: CallbackQuery, state: FSMContext):
    """Выбрать VIP план"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "💎 **Преимущества VIP:**\n\n"
            "🎯 Поиск только по девушкам/парням\n"
            "👑 Premium пользователи видят только нужный пол\n"
            "∞ Безлимитное общение\n"
            "🚫 Без рекламы\n\n"
            "**Выберите план:**",
            reply_markup=get_vip_plans_keyboard()
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_vip_plan(callback: CallbackQuery, state: FSMContext):
    """Обработать выбор VIP плана"""
    try:
        plan = callback.data.split('_')[1:]
        plan_text = '_'.join(plan)
        
        # Симуляция платежа (в реальном боте нужно использовать payments API)
        days = {'7days': 7, '1month': 30, '1year': 365}.get(plan_text, 7)
        
        db.set_premium(callback.from_user.id, days)
        
        await callback.answer("✅ Спасибо за покупку!", show_alert=True)
        await callback.message.edit_text(
            f"⭐ **Поздравляем!**\n\n"
            f"Вы стали VIP-пользователем на {days} дней!\n\n"
            f"🎉 Теперь вам доступны все премиум функции",
            reply_markup=get_main_menu()
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_rules(callback: CallbackQuery, state: FSMContext):
    """Правила чата"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "📋 **Правила общения в чате:**\n\n"
            "✅ Будьте вежливы и уважительны\n"
            "✅ Соблюдайте законодательство\n"
            "❌ Без спама и рекламы\n"
            "❌ Без оскорблений и оскорбительного контента\n"
            "❌ Без персональной информации\n"
            "❌ Без материалов для взрослых\n\n"
            "⚠️ Нарушители будут заблокированы!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
            ])
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_help(callback: CallbackQuery, state: FSMContext):
    """Помощь"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "ℹ️ **Справка по командам:**\n\n"
            "`/search` - начать поиск\n"
            "`/next` - следующий собеседник\n"
            "`/stop` - завершить чат\n"
            "`/interests` - выбрать интересы\n"
            "`/settings` - настройки\n"
            "`/rules` - правила чата\n\n"
            "💬 Вопросы и предложения приветствуются!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
            ])
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_back_to_menu(callback: CallbackQuery, state: FSMContext):
    """Вернуться в меню"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "👋 **Главное меню**",
            reply_markup=get_main_menu()
        )
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_cancel_search(callback: CallbackQuery, state: FSMContext):
    """Отмена поиска"""
    global waiting_users
    try:
        user_id = callback.from_user.id
        data = await state.get_data()
        category = data.get('category')
        
        if category and user_id in waiting_users[category]:
            waiting_users[category].remove(user_id)
        
        await callback.answer("Поиск отменён")
        await callback.message.edit_text(
            "Поиск отменён",
            reply_markup=get_main_menu()
        )
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

# ============= MAIN =============

async def main():
    """Основная функция"""
    global bot_instance
    try:
        logger.info("🚀 Запуск бота @AnonRuBot...")
        
        await db.init_db()
        logger.info("📁 БД инициализирована")
        
        if not BOT_TOKEN:
            logger.error("❌ BOT_TOKEN не установлен!")
            sys.exit(1)
        
        bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
        bot_instance = bot
        
        dp = Dispatcher()
        
        # Регистрация handlers
        dp.message.register(cmd_start, Command("start"))
        dp.callback_query.register(cmd_search, F.data == "search_start")
        dp.callback_query.register(cmd_search_gender, F.data == "search_gender")
        dp.callback_query.register(handle_search_filter, F.data.startswith("filter_"))
        dp.callback_query.register(handle_choose_interests, F.data == "choose_interests")
        dp.message.register(handle_chat_message, UserStates.in_chat)
        dp.callback_query.register(handle_end_chat, F.data == "end_chat")
        dp.callback_query.register(handle_vote, F.data.startswith("vote_"))
        dp.callback_query.register(handle_report_user, F.data.startswith("report_"))
        dp.callback_query.register(handle_profile, F.data == "profile")
        dp.callback_query.register(handle_edit_gender, F.data == "edit_profile")
        dp.callback_query.register(handle_set_gender, F.data.startswith("set_gender_"))
        dp.message.register(handle_age_input, UserStates.waiting_age)
        dp.callback_query.register(handle_vip_select, F.data == "vip_select")
        dp.callback_query.register(handle_vip_plan, F.data.startswith("vip_"))
        dp.callback_query.register(handle_rules, F.data == "rules")
        dp.callback_query.register(handle_help, F.data == "help")
        dp.callback_query.register(handle_back_to_menu, F.data == "back_to_menu")
        dp.callback_query.register(handle_cancel_search, F.data == "cancel_search")
        
        logger.info("✅ Все handlers зарегистрированы")
        logger.info("🚀 БОТ ЗАПУЩЕН И ГОТОВ!")
        
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await bot.session.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️  Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}", exc_info=True)
