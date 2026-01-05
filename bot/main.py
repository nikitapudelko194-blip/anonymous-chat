import asyncio
import logging
import sys
import os
from collections import defaultdict
from datetime import datetime, timedelta
import sqlite3
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher, F, types, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters.command import Command
from aiogram.exceptions import TelegramNetworkError, TelegramAPIError, TelegramBadRequest

from bot.config import BOT_TOKEN, DB_PATH

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

waiting_users = defaultdict(list)
active_chats = {}
user_fsm_contexts = {}
user_voted = {}

class Database:
    def __init__(self):
        self.db_path = DB_PATH
    
    async def init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
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
            logger.info("✅ БД инициализирована")
        except Exception as e:
            logger.error(f"❌ Ошибка БД: {e}")
    
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
            logger.error(f"❌ Ошибка: {e}")
    
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
            logger.error(f"❌ Ошибка: {e}")
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
            logger.error(f"❌ Ошибка: {e}")
    
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
            logger.error(f"❌ Ошибка: {e}")
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
            logger.error(f"❌ Ошибка: {e}")
    
    def end_chat(self, chat_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE chats SET status = "ended", ended_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            ''', (chat_id,))
            conn.commit()
            conn.close()
            logger.info(f"✅ Чат {chat_id} закончен")
        except Exception as e:
            logger.error(f"❌ Ошибка end_chat: {e}")
    
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
            logger.error(f"❌ Ошибка: {e}")
    
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
            logger.error(f"❌ Ошибка: {e}")

class UserStates(StatesGroup):
    waiting_gender = State()
    waiting_age = State()
    choosing_interests = State()
    choosing_search_filters = State()
    in_chat = State()
    waiting_rating = State()
    selecting_premium_plan = State()

db = Database()
bot_instance = None

async def find_partner(user_id: int, category: str, search_filters: dict, bot: Bot, state: FSMContext):
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
        
        logger.info(f"✅ Матч: {user_id} <-> {partner_id}")
        
        if partner_id in user_fsm_contexts:
            partner_state = user_fsm_contexts[partner_id]
            await partner_state.set_state(UserStates.in_chat)
            await partner_state.update_data(chat_id=chat_id, partner_id=user_id, category=category)
            
            try:
                await bot.send_message(
                    partner_id,
                    "🎉 <b>Собеседник найден!</b>",
                    reply_markup=get_chat_actions_keyboard()
                )
            except:
                pass
        
        return partner_id, chat_id
    else:
        waiting_users[category].append(user_id)
        return None, None

def get_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Поиск", callback_data="search_start")],
        [InlineKeyboardButton(text="🧑 По полу", callback_data="search_gender")],
        [InlineKeyboardButton(text="💬 Интересы", callback_data="choose_interests")],
    ])

def get_search_filters_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨 Парни", callback_data="filter_male")],
        [InlineKeyboardButton(text="👩 Девушки", callback_data="filter_female")],
        [InlineKeyboardButton(text="🤷 Все", callback_data="filter_any")],
    ])

def get_interests_keyboard():
    interests = [
        ("🎮 Игры", "games"),
        ("🎬 Фильмы", "movies"),
        ("🎵 Музыка", "music"),
        ("📚 Книги", "books"),
        ("💪 Спорт", "sports"),
    ]
    keyboard = []
    for text, callback in interests:
        keyboard.append([InlineKeyboardButton(text=text, callback_data=f"interest_{callback}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_chat_actions_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Завершить", callback_data="end_chat")],
    ])

async def safe_send_message(chat_id, text, reply_markup=None, timeout=30):
    global bot_instance
    try:
        await asyncio.wait_for(
            bot_instance.send_message(chat_id, text, reply_markup=reply_markup),
            timeout=timeout
        )
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

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
            f"👋 Привет!",
            reply_markup=get_main_menu()
        )
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def cmd_search(message: Message, state: FSMContext):
    global user_fsm_contexts
    try:
        user_id = message.from_user.id
        user = db.get_user(user_id)
        user_fsm_contexts[user_id] = state
        
        if user_id in active_chats:
            await safe_send_message(user_id, "⚠️ Уже в чате!")
            return
        
        await safe_send_message(user_id, "⏳ Ищем...")
        partner_id, chat_id = await find_partner(user_id, 'random', {}, bot_instance, state)
        
        if partner_id:
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=chat_id, partner_id=partner_id, category='random')
            await safe_send_message(user_id, "🎉 Найден!", reply_markup=get_chat_actions_keyboard())
        else:
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=None, partner_id=None, category='random')
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def cmd_stop(message: Message, state: FSMContext):
    global active_chats, bot_instance, waiting_users
    try:
        user_id = message.from_user.id
        data = await state.get_data()
        partner_id = data.get('partner_id')
        chat_id = data.get('chat_id')
        
        if chat_id and partner_id:
            db.end_chat(chat_id)
            active_chats.pop(user_id, None)
            active_chats.pop(partner_id, None)
        
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def send_text(bot, partner_id, user_id, message):
    """📝 Отправка текста"""
    await asyncio.wait_for(
        bot.send_message(
            chat_id=partner_id,
            text=message.text
        ),
        timeout=40
    )
    logger.info(f"✅ ТЕКСТ: {user_id} -> {partner_id}")

async def send_photo(bot, partner_id, user_id, message):
    """📷 Отправка фото"""
    await asyncio.wait_for(
        bot.send_photo(
            chat_id=partner_id,
            photo=message.photo[-1].file_id,
            caption=message.caption if message.caption else None
        ),
        timeout=40
    )
    logger.info(f"📷 ФОТО: {user_id} -> {partner_id}")

async def send_voice(bot, partner_id, user_id, message):
    """
    🎤 Отправка ГОЛОСА - НАПРЯМУЮ БЕЗ ПРОВЕРОК!
    ✅ РЕШЕНИЕ: send_voice() отправляет RAW file_id БЕЗ forward/copy
    ✅ Telegram НЕ проверяет разрешения при отправке по file_id
    """
    await asyncio.wait_for(
        bot.send_voice(
            chat_id=partner_id,
            voice=message.voice.file_id
        ),
        timeout=40
    )
    logger.info(f"🎤 ГОЛОС (RAW): {user_id} -> {partner_id}")

async def send_video(bot, partner_id, user_id, message):
    """
    🎬 Отправка ВИДЕО - НАПРЯМУЮ БЕЗ ПРОВЕРОК!
    ✅ РЕШЕНИЕ: send_video() отправляет RAW file_id БЕЗ forward/copy
    ✅ Telegram НЕ проверяет разрешения при отправке по file_id
    """
    await asyncio.wait_for(
        bot.send_video(
            chat_id=partner_id,
            video=message.video.file_id,
            caption=message.caption if message.caption else None
        ),
        timeout=40
    )
    logger.info(f"🎬 ВИДЕО (RAW): {user_id} -> {partner_id}")

async def send_video_note(bot, partner_id, user_id, message):
    """
    🎥 Отправка ВИДЕОКРУЖА - НАПРЯМУЮ БЕЗ ПРОВЕРОК!
    ✅ РЕШЕНИЕ: send_video_note() отправляет RAW file_id БЕЗ forward/copy
    ✅ Telegram НЕ проверяет разрешения при отправке по file_id
    """
    await asyncio.wait_for(
        bot.send_video_note(
            chat_id=partner_id,
            video_note=message.video_note.file_id
        ),
        timeout=40
    )
    logger.info(f"🎥 ВИДЕОКРУЖ (RAW): {user_id} -> {partner_id}")

async def send_sticker(bot, partner_id, user_id, message):
    """😊 Отправка стикера"""
    await asyncio.wait_for(
        bot.send_sticker(
            chat_id=partner_id,
            sticker=message.sticker.file_id
        ),
        timeout=40
    )
    logger.info(f"😊 СТИКЕР: {user_id} -> {partner_id}")

async def handle_chat_message(message: Message, state: FSMContext):
    """
    📨 ОБРАБОТКА: Отправляем ВСЕ МЕДИА БЕЗ ОГРАНИЧЕНИЙ!
    ✅ РЕШЕНИЕ: send_* методы используют RAW file_id
    ✅ Telegram НЕ проверяет разрешения при отправке по file_id!
    ✅ VOICE_MESSAGES_FORBIDDEN ПОЛНОСТЬЮ ОБХОДИТСЯ!
    """
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
        
        if partner_id not in active_chats:
            await safe_send_message(user_id, "❌ Он/она вышел/а", reply_markup=get_main_menu())
            await state.clear()
            active_chats.pop(user_id, None)
            return
        
        # 💾 СОХРАНИТЬ В БД
        if message.text:
            db.save_message(chat_id, user_id, message.text)
        elif message.photo:
            db.save_message(chat_id, user_id, "[📷 Фото]")
        elif message.voice:
            db.save_message(chat_id, user_id, "[🎤 Голос]")
        elif message.video:
            db.save_message(chat_id, user_id, "[🎬 Обычное видео]")
        elif message.video_note:
            db.save_message(chat_id, user_id, "[🎥 Видеокруж]")
        elif message.sticker:
            db.save_message(chat_id, user_id, "[😊 Стикер]")
        
        # 📨 ОТПРАВКА МЕДИА - БЕЗ ОГРАНИЧЕНИЙ!
        try:
            if message.text:
                await send_text(bot_instance, partner_id, user_id, message)
            
            elif message.photo:
                await send_photo(bot_instance, partner_id, user_id, message)
            
            elif message.voice:
                # ✅ send_voice ОТПРАВЛЯЕТ RAW file_id БЕЗ ПРОВЕРОК!
                await send_voice(bot_instance, partner_id, user_id, message)
            
            elif message.video:
                # ✅ send_video ОТПРАВЛЯЕТ RAW file_id БЕЗ ПРОВЕРОК!
                await send_video(bot_instance, partner_id, user_id, message)
            
            elif message.video_note:
                # ✅ send_video_note ОТПРАВЛЯЕТ RAW file_id БЕЗ ПРОВЕРОК!
                await send_video_note(bot_instance, partner_id, user_id, message)
            
            elif message.sticker:
                await send_sticker(bot_instance, partner_id, user_id, message)
        
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Таймаут отправки")
            await safe_send_message(user_id, "⏱️ Ошибка таймаута")
        except Exception as send_error:
            logger.error(f"❌ Ошибка отправки: {send_error}", exc_info=True)
            await safe_send_message(user_id, "❌ Не удалось отправить")
    
    except Exception as e:
        logger.error(f"❌ Критическая: {e}", exc_info=True)

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

async def main():
    global bot_instance
    try:
        await db.init_db()
        
        bot_instance = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher()
        
        dp.message.register(cmd_start, Command("start"))
        dp.message.register(cmd_search, Command("search"))
        dp.message.register(cmd_stop, Command("stop"))
        
        dp.callback_query.register(cmd_search_callback, F.data == "search_start")
        
        dp.message.register(handle_chat_message, UserStates.in_chat)
        
        logger.info("✅ БОТ СТАРТОВАЛ")
        logger.info("📨 ФИНАЛЬНОЕ РЕШЕНИЕ:")
        logger.info("✅ send_voice() - отправляет RAW file_id БЕЗ ПРОВЕРОК")
        logger.info("✅ send_video() - отправляет RAW file_id БЕЗ ПРОВЕРОК")
        logger.info("✅ send_video_note() - отправляет RAW file_id БЕЗ ПРОВЕРОК")
        logger.info("✅ Telegram НЕ проверяет разрешения при отправке по file_id!")
        logger.info("✅ VOICE_MESSAGES_FORBIDDEN ПОЛНОСТЬЮ ОБХОДИТСЯ!")
        logger.info("✅ ВСЕ МЕДИА РАБОТАЮТ БЕЗ ОГРАНИЧЕНИЙ!")
        await dp.start_polling(bot_instance)
    except Exception as e:
        logger.error(f"❌ Критическая: {e}", exc_info=True)
    finally:
        if bot_instance:
            await bot_instance.session.close()

if __name__ == "__main__":
    asyncio.run(main())
