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
from aiogram.exceptions import TelegramNetworkError, TelegramAPIError, TelegramBadRequest

from bot.config import BOT_TOKEN, DB_PATH

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
user_fsm_contexts = {}  # user_id -> FSMContext
user_voted = {}  # user_id -> {chat_id} - кто уже оценил кого

# НОВО: Хранилище для превюю загруженных медиа-файлов
media_storage = {}  # unique_id -> {file_id, type, duration, caption, timestamp}

# Database
class Database:
    def __init__(self):
        self.db_path = DB_PATH
    
    async def init_db(self):
        """Инициализировать базу данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Таблица пользователей
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
            
            # Таблица оценок
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
            
            # Таблица платежей
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
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO votes (voter_id, votee_id, chat_id, vote_type)
                VALUES (?, ?, ?, ?)
            ''', (voter_id, votee_id, chat_id, vote_type))
            
            if vote_type == 'positive':
                cursor.execute('UPDATE users SET positive_votes = positive_votes + 1 WHERE user_id = ?', (votee_id,))
            else:
                cursor.execute('UPDATE users SET negative_votes = negative_votes + 1 WHERE user_id = ?', (votee_id,))
            
            cursor.execute('SELECT positive_votes, negative_votes FROM users WHERE user_id = ?', (votee_id,))
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

async def find_partner(user_id: int, category: str, search_filters: dict, bot: Bot, state: FSMContext):
    """Найти партнера"""
    global waiting_users, active_chats, user_fsm_contexts
    
    for cat in waiting_users:
        if user_id in waiting_users[cat]:
            waiting_users[cat].remove(user_id)
    
    if waiting_users[category]:
        partner_id = waiting_users[category].pop(0)
        partner = db.get_user(partner_id)
        
        if search_filters.get('gender') and search_filters['gender'] != 'any':
            if partner['gender'] != search_filters['gender']:
                waiting_users[category].append(partner_id)
                waiting_users[category].append(user_id)
                return None, None
        
        chat_id = db.create_chat(user_id, partner_id, category)
        active_chats[user_id] = {'partner_id': partner_id, 'chat_id': chat_id}
        active_chats[partner_id] = {'partner_id': user_id, 'chat_id': chat_id}
        
        logger.info(f"✅ Матч найден: {user_id} <-> {partner_id}")
        
        if partner_id in user_fsm_contexts:
            partner_state = user_fsm_contexts[partner_id]
            await partner_state.set_state(UserStates.in_chat)
            await partner_state.update_data(chat_id=chat_id, partner_id=user_id, category=category)
            
            try:
                await bot.send_message(
                    partner_id,
                    "🎉 <b>Собеседник найден!</b>\n\n💬 Введите сообщение и отправьте его:",
                    reply_markup=get_chat_actions_keyboard()
                )
            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
        
        return partner_id, chat_id
    else:
        waiting_users[category].append(user_id)
        logger.info(f"⏳ {user_id} в очереди {category}")
        return None, None

# ============= KEYBOARDS =============

def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Поиск собеседника", callback_data="search_start")],
        [InlineKeyboardButton(text="👤 Поиск по полу", callback_data="search_gender")],
        [InlineKeyboardButton(text="💬 Выбрать интересы", callback_data="choose_interests")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="💎 Стать VIP", callback_data="vip_select")],
        [InlineKeyboardButton(text="📋 Правила", callback_data="rules")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
    ])

def get_search_filters_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨 Парни", callback_data="filter_male")],
        [InlineKeyboardButton(text="👩 Девушки", callback_data="filter_female")],
        [InlineKeyboardButton(text="🤷 Без разницы", callback_data="filter_any")],
    ])

def get_interests_keyboard():
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Спам", callback_data="report_spam")],
        [InlineKeyboardButton(text="❌ Полнота", callback_data="report_inappropriate")],
        [InlineKeyboardButton(text="⚠️ Пожаловаться", callback_data="report_user")],
        [InlineKeyboardButton(text="❌ Завершить", callback_data="end_chat")],
    ])

def get_rating_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👍 Нравится", callback_data="vote_positive"), 
         InlineKeyboardButton(text="👎 Не нравится", callback_data="vote_negative")],
        [InlineKeyboardButton(text="➡️ Новый", callback_data="search_start")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="back_to_menu")],
    ])

def get_vip_plans_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 7 дней - 250₽", callback_data="vip_7days")],
        [InlineKeyboardButton(text="⭐ 1 мес - 350₽", callback_data="vip_1month")],
        [InlineKeyboardButton(text="⭐ 1 год - 500₽", callback_data="vip_1year")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
    ])

# ============= HELPER FUNCTIONS =============

async def safe_send_message(chat_id, text, reply_markup=None, timeout=30):
    global bot_instance
    retries = 3
    for attempt in range(retries):
        try:
            await asyncio.wait_for(
                bot_instance.send_message(chat_id, text, reply_markup=reply_markup),
                timeout=timeout
            )
            return True
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Таймаут {chat_id} (попытка {attempt+1}/{retries})")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                return False
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False
    return False

# ============= MESSAGE HANDLERS =============

async def cmd_start(message: Message, state: FSMContext):
    global user_fsm_contexts
    try:
        user_id = message.from_user.id
        user = db.get_user(user_id)
        user_fsm_contexts[user_id] = state
        
        if not user:
            db.create_user(user_id, message.from_user.username, message.from_user.first_name)
        
        await safe_send_message(
            user_id,
            f"👋 Привет, {message.from_user.first_name or 'друг'}!\n\n"
            "🎭 <b>Анонимный чат</b>\n\n"
            "💬 Общайтесь анонимно \n"
            "✨ Полная конфиденциальность\n"
            "🔒 Безопасность\n\n"
            "<b>Команды:</b>\n"
            "`/search` - Найти собеседника\n"
            "`/next` - Новый чат\n"
            "`/stop` - Завершить\n"
            "`/help` - Справка",
            reply_markup=get_main_menu()
        )
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка в cmd_start: {e}", exc_info=True)

async def cmd_search(message: Message, state: FSMContext):
    global user_fsm_contexts
    try:
        user_id = message.from_user.id
        user = db.get_user(user_id)
        user_fsm_contexts[user_id] = state
        
        if user_id in active_chats:
            await safe_send_message(user_id, "⚠️ Вы уже в чате!")
            return
        
        if user['is_banned']:
            await safe_send_message(user_id, "❌ Вы заблокированы")
            return
        
        await safe_send_message(user_id, "⏳ Ищем...")
        partner_id, chat_id = await find_partner(user_id, 'random', {}, bot_instance, state)
        
        if partner_id:
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=chat_id, partner_id=partner_id, category='random')
            await safe_send_message(user_id, "🎉 <b>Найден!</b>\n\n💬 Пишите:", reply_markup=get_chat_actions_keyboard())
        else:
            await safe_send_message(user_id, "⏳ Ожидание...")
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=None, partner_id=None, category='random')
    except Exception as e:
        logger.error(f"❌ Ошибка в search: {e}")

async def cmd_next(message: Message, state: FSMContext):
    global active_chats, bot_instance, user_fsm_contexts
    try:
        user_id = message.from_user.id
        data = await state.get_data()
        partner_id = data.get('partner_id')
        chat_id = data.get('chat_id')
        
        if chat_id and partner_id:
            db.end_chat(chat_id)
            active_chats.pop(user_id, None)
            active_chats.pop(partner_id, None)
            
            try:
                await asyncio.wait_for(
                    bot_instance.send_message(partner_id, "❌ Новый чат", reply_markup=get_rating_keyboard()),
                    timeout=15
                )
            except:
                pass
        
        await state.clear()
        user_fsm_contexts[user_id] = state
        await safe_send_message(user_id, "⏳ Ищем...")
        
        partner_id, chat_id = await find_partner(user_id, 'random', {}, bot_instance, state)
        if partner_id:
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=chat_id, partner_id=partner_id, category='random')
            await safe_send_message(user_id, "🎉 Найден!", reply_markup=get_chat_actions_keyboard())
    except Exception as e:
        logger.error(f"❌ Ошибка в next: {e}")

async def cmd_stop(message: Message, state: FSMContext):
    global active_chats, bot_instance, waiting_users
    try:
        user_id = message.from_user.id
        data = await state.get_data()
        partner_id = data.get('partner_id')
        chat_id = data.get('chat_id')
        category = data.get('category')
        
        if chat_id and partner_id:
            db.end_chat(chat_id)
            active_chats.pop(user_id, None)
            active_chats.pop(partner_id, None)
            
            try:
                await asyncio.wait_for(
                    bot_instance.send_message(partner_id, "❌ Окончил", reply_markup=get_rating_keyboard()),
                    timeout=15
                )
            except:
                pass
            
            await safe_send_message(user_id, "✅ Окончил", reply_markup=get_rating_keyboard())
        
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def cmd_help(message: Message, state: FSMContext):
    try:
        await safe_send_message(
            message.from_user.id,
            "<b>📖 Справка</b>\n\n"
            "/search - Найти\n"
            "/next - Новый\n"
            "/stop - Окончить\n"
            "/help - Это",
            reply_markup=get_main_menu()
        )
    except Exception as e:
        logger.error(f"❌ help: {e}")

# ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ В ЧАТЕ

async def handle_chat_message(message: Message, state: FSMContext):
    """🔧 ОСНОВНОЕ ОБНОВЛЕНИЕ: НИКАКОЙ ПЕРЕсылки МЕДИА, ОДНО ОЕДИНЕНИЕ СООБЩЕНИЕ"""
    global bot_instance, active_chats
    try:
        user_id = message.from_user.id
        data = await state.get_data()
        chat_id = data.get('chat_id')
        partner_id = data.get('partner_id')
        
        if not chat_id or not partner_id or user_id not in active_chats:
            await safe_send_message(user_id, "❌ Чат закончен", reply_markup=get_main_menu())
            await state.clear()
            return
        
        if partner_id not in active_chats or active_chats[partner_id].get('chat_id') != chat_id:
            await safe_send_message(user_id, "❌ Он/она вышел/а", reply_markup=get_main_menu())
            await state.clear()
            active_chats.pop(user_id, None)
            return
        
        # СОХРАНИТЬ СООБЩЕНИЕ В БД
        msg_type = "текст"
        if message.text:
            db.save_message(chat_id, user_id, message.text)
            msg_type = "текст"
        elif message.photo:
            db.save_message(chat_id, user_id, "[📷 Фото]")
            msg_type = "фото"
        elif message.voice:
            db.save_message(chat_id, user_id, "[🎤 Голос]")
            msg_type = "голос"
        elif message.sticker:
            db.save_message(chat_id, user_id, "[😊 Стикер]")
            msg_type = "стикер"
        elif message.video_note:
            db.save_message(chat_id, user_id, "[🎬 Видео]")
            msg_type = "видео"
        
        # ОТПРАВКА
        try:
            if message.text:
                await asyncio.wait_for(
                    bot_instance.send_message(partner_id, message.text),
                    timeout=20
                )
                logger.info(f"✅ Текст: {user_id} -> {partner_id}")
            
            elif message.photo:
                await asyncio.wait_for(
                    bot_instance.send_photo(partner_id, message.photo[-1].file_id, caption=message.caption or "📷"),
                    timeout=30
                )
                logger.info(f"✅ Фото: {user_id} -> {partner_id}")
            
            elif message.voice:
                # 🔧 ГОЛОС - ПОКАЗЫВАЕМ КНОПКУ, НО НЕ ОТПРАВЛЯЕМ МЕДИА
                logger.info(f"🎤 Голос от {user_id} получен")
                
                # Храним в памяти
                unique_id = str(uuid.uuid4())
                media_storage[unique_id] = {
                    'file_id': message.voice.file_id,
                    'type': 'voice',
                    'duration': message.voice.duration,
                    'timestamp': datetime.now()
                }
                
                # Отправляем нотификацию с кнопкой
                await asyncio.wait_for(
                    bot_instance.send_message(
                        partner_id,
                        f"🎤 <b>Голосовое сообщение</b> ({message.voice.duration}c)",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="🔊 Прослушать", callback_data=f"play_voice_{unique_id}")]
                        ])
                    ),
                    timeout=15
                )
                logger.info(f"✅ Кнопка голоса отправлена {partner_id}")
            
            elif message.sticker:
                await asyncio.wait_for(
                    bot_instance.send_sticker(partner_id, message.sticker.file_id),
                    timeout=20
                )
                logger.info(f"✅ Стикер: {user_id} -> {partner_id}")
            
            elif message.video_note:
                await asyncio.wait_for(
                    bot_instance.send_video_note(partner_id, message.video_note.file_id),
                    timeout=30
                )
                logger.info(f"✅ Видео: {user_id} -> {partner_id}")
        
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Таймаут")
            await safe_send_message(user_id, "⏱️ Проблема сети")
        except Exception as send_error:
            logger.error(f"❌ Ошибка отправки: {send_error}")
            await safe_send_message(user_id, "❌ Ошибка")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)

# КОЛЛБЕК дЛЯ ПРОСЛУШИВАНИЯ ГОЛОСА

async def on_play_voice(callback: CallbackQuery):
    """Отправить голосовое сообщение по кнопке"""
    try:
        callback_data = callback.data
        unique_id = callback_data.replace("play_voice_", "")
        
        if unique_id in media_storage:
            media_info = media_storage[unique_id]
            await callback.message.answer_voice(
                media_info['file_id'],
                duration=media_info.get('duration')
            )
            await callback.answer("🔊 Плей")
            logger.info(f"✅ Голос воспроизведен: {unique_id}")
        else:
            await callback.answer("❌ Голос больше не актуален", show_alert=True)
    except Exception as e:
        logger.error(f"❌ Ошибка воспроизведения: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

async def cmd_search_callback(callback: CallbackQuery, state: FSMContext):
    global user_fsm_contexts
    try:
        user_id = callback.from_user.id
        user = db.get_user(user_id)
        user_fsm_contexts[user_id] = state
        
        if user_id in active_chats:
            await callback.answer("⚠️ Уже в чате", show_alert=True)
            return
        
        await callback.answer()
        partner_id, chat_id = await find_partner(user_id, 'random', {}, bot_instance, state)
        
        if partner_id:
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=chat_id, partner_id=partner_id, category='random')
            await callback.message.edit_text("🎉 Найден!", reply_markup=get_chat_actions_keyboard())
        else:
            await callback.message.edit_text("⏳ Ожидание...")
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=None, partner_id=None, category='random')
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

# ============= MAIN =============

async def main():
    global bot_instance
    try:
        await db.init_db()
        
        bot_instance = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher()
        
        # Команды
        dp.message.register(cmd_start, Command("start"))
        dp.message.register(cmd_search, Command("search"))
        dp.message.register(cmd_next, Command("next"))
        dp.message.register(cmd_stop, Command("stop"))
        dp.message.register(cmd_help, Command("help"))
        
        # Коллбэки
        dp.callback_query.register(cmd_search_callback, F.data == "search_start")
        dp.callback_query.register(on_play_voice, F.data.startswith("play_voice_"))
        
        # Мессажи в чате
        dp.message.register(handle_chat_message, UserStates.in_chat, F.voice)
        dp.message.register(handle_chat_message, UserStates.in_chat, F.photo)
        dp.message.register(handle_chat_message, UserStates.in_chat, F.sticker)
        dp.message.register(handle_chat_message, UserStates.in_chat, F.video_note)
        dp.message.register(handle_chat_message, UserStates.in_chat)
        
        logger.info("✅ Бот старт")
        logger.info("💌 Голосовые сообщения: на кнопку для плейа")
        await dp.start_polling(bot_instance)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
    finally:
        if bot_instance:
            await bot_instance.session.close()

if __name__ == "__main__":
    asyncio.run(main())
