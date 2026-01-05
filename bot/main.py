import asyncio
import logging
import sys
import os
from collections import defaultdict
from datetime import datetime, timedelta
import sqlite3
import uuid
import aiohttp

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
            logger.info(f"✅ Чат {chat_id} завершён")
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
    waiting_vote = State()
    waiting_report = State()
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
                    "🌟 <b>Новый собеседник найден!</b>\n\n🌏 Диалог начат. Напишите /next чтобы перейти к следующему собеседнику",
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
        [InlineKeyboardButton(text="🔍 Поиск собеседника", callback_data="search_start")],
        [InlineKeyboardButton(text="👫 Поиск по полу", callback_data="search_gender")],
        [InlineKeyboardButton(text="📖 Выбрать интересы", callback_data="choose_interests")],
        [InlineKeyboardButton(text="📄 Правила общения", callback_data="rules")],
        [InlineKeyboardButton(text="❓ Помощь по боту", callback_data="help")],
        [InlineKeyboardButton(text="💳 Премиум", callback_data="premium")],
    ])

def get_chat_actions_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Следующий", callback_data="next_partner")],
        [InlineKeyboardButton(text="🛑 Завершить", callback_data="end_chat")],
    ])

def get_vote_keyboard(chat_id, partner_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👍 Нравится", callback_data=f"vote_positive_{chat_id}_{partner_id}")],
        [InlineKeyboardButton(text="👎 Не нравится", callback_data=f"vote_negative_{chat_id}_{partner_id}")],
        [InlineKeyboardButton(text="🚨 Отчет", callback_data=f"report_{chat_id}_{partner_id}")],
        [InlineKeyboardButton(text="⏭️ Новый диалог", callback_data="search_start")],
    ])

def get_report_keyboard(chat_id, partner_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📛 Спам и реклама", callback_data=f"report_spam_{chat_id}_{partner_id}")],
        [InlineKeyboardButton(text="🚫 Непристойная речь", callback_data=f"report_obscene_{chat_id}_{partner_id}")],
        [InlineKeyboardButton(text="♾️ Остаться без удаления диалога", callback_data="search_start")],
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
            "👋 <b>Привет!</b>\n\n👋 Фантастических разговоров в случайных диалогах!",
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
            await safe_send_message(user_id, "⚠️ <b>Вы уже в диалоге!</b>\n\nНапишите /next чтобы перейти к следующему собеседнику")
            return
        
        await safe_send_message(user_id, "🔍 <b>Поиск собеседника...</b>")
        partner_id, chat_id = await find_partner(user_id, 'random', {}, bot_instance, state)
        
        if partner_id:
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=chat_id, partner_id=partner_id, category='random')
            await safe_send_message(user_id, "🌟 <b>Новый собеседник!</b>\n\n💬 Диалог начат. Напишите /next чтобы перейти к следующему собеседнику", reply_markup=get_chat_actions_keyboard())
        else:
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=None, partner_id=None, category='random')
            await safe_send_message(user_id, "⏳ <b>Ожидание собеседника...</b>\n\n🔍 Мы ищем нового собеседника для вас")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def cmd_next(message: Message, state: FSMContext):
    global active_chats, waiting_users
    try:
        user_id = message.from_user.id
        data = await state.get_data()
        chat_id = data.get('chat_id')
        partner_id = data.get('partner_id')
        
        if chat_id and partner_id:
            db.end_chat(chat_id)
            active_chats.pop(user_id, None)
            active_chats.pop(partner_id, None)
            
            # 📣 ОУВЕДОМЛЯЕМ ОБОИХ - ОБА ПОЛУЧАЮТ НОВОЕ СООБЩЕНИЕ
            await safe_send_message(
                user_id,
                "📑 <b>Оцените собеседника</b>\n\n👍 Нравится или Не нравится? Ваша оценка важна!",
                reply_markup=get_vote_keyboard(chat_id, partner_id)
            )
            
            await safe_send_message(
                partner_id,
                "📣 <b>ДИАЛОГ ЗАВЕРШЁН</b>\n\n👍 Оцените собеседника:\n\n👍 Нравится - Не нравится\n🚨 Оставить отчёт - Новый диалог",
                reply_markup=get_vote_keyboard(chat_id, user_id)
            )
            
            logger.info(f"📣 ОБА пользователя отобразили голосование")
        
        await state.clear()
        await cmd_search(message, state)
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
            
            # 📣 ОУВЕДОМЛЯЕМ ОБОИХ - ОБА ПОЛУЧАЮТ НОВОЕ СООБЩЕНИЕ
            
            # ОБОИМ ПОЛьзователям ПОСЛАНЕМ ОДИНАКОВОЕ СООБЩЕНИЕ!
            voting_message = "📑 <b>Оцените собеседника</b>\n\n👍 Нравится или Не нравится? Ваша оценка важна!"
            
            # ПРОВЕРКА: если партнёр ещё в диалоге
            if partner_id in active_chats:
                # ПАРТНЁР ЕЩЁ В ДИАЛОГЕ - ОТПРАВЛяем НОВОЕ СООБЩЕНИЕ
                await safe_send_message(
                    partner_id,
                    voting_message,
                    reply_markup=get_vote_keyboard(chat_id, user_id)
                )
            
            await safe_send_message(
                user_id,
                voting_message,
                reply_markup=get_vote_keyboard(chat_id, partner_id)
            )
            
            logger.info(f"📣 ОБА пользователя идентично видят голосование")
        
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
    try:
        await asyncio.wait_for(
            bot.send_voice(
                chat_id=partner_id,
                voice=message.voice.file_id
            ),
            timeout=40
        )
        logger.info(f"🎤 ГОЛОС: {user_id} -> {partner_id}")
    except TelegramBadRequest as e:
        logger.warning(f"⚠️ ГОЛОС ОТПРАВЛЕН несмотря на рестрикцию {partner_id}")

async def send_video(bot, partner_id, user_id, message):
    try:
        await asyncio.wait_for(
            bot.send_video(
                chat_id=partner_id,
                video=message.video.file_id,
                caption=message.caption if message.caption else None
            ),
            timeout=40
        )
        logger.info(f"🎬 ВИДЕО: {user_id} -> {partner_id}")
    except TelegramBadRequest as e:
        logger.warning(f"⚠️ ВИДЕО ОТПРАВЛЕНО несмотря на рестрикцию {partner_id}")

async def send_video_note(bot, partner_id, user_id, message):
    try:
        await asyncio.wait_for(
            bot.send_video_note(
                chat_id=partner_id,
                video_note=message.video_note.file_id
            ),
            timeout=40
        )
        logger.info(f"🎥 ВИДЕОКРУЖ: {user_id} -> {partner_id}")
    except TelegramBadRequest as e:
        logger.warning(f"⚠️ ВИДЕОКРУЖ ОТПРАВЛЕН несмотря на рестрикцию {partner_id}")
    except Exception as e:
        logger.warning(f"⚠️ ВИДЕОКРУЖ ОТПРАВЛЕН")

async def send_sticker(bot, partner_id, user_id, message):
    await asyncio.wait_for(
        bot.send_sticker(
            chat_id=partner_id,
            sticker=message.sticker.file_id
        ),
        timeout=40
    )
    logger.info(f"😊 СТИКЕР: {user_id} -> {partner_id}")

async def handle_chat_message(message: Message, state: FSMContext):
    global bot_instance, active_chats
    try:
        user_id = message.from_user.id
        data = await state.get_data()
        chat_id = data.get('chat_id')
        partner_id = data.get('partner_id')
        
        if not chat_id or not partner_id or user_id not in active_chats:
            await safe_send_message(user_id, "❌ <b>Диалог завершён</b>", reply_markup=get_main_menu())
            await state.clear()
            return
        
        if partner_id not in active_chats:
            await safe_send_message(user_id, "❌ <b>Он/она вышел/а</b>", reply_markup=get_main_menu())
            await state.clear()
            active_chats.pop(user_id, None)
            return
        
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
        
        try:
            if message.text:
                await send_text(bot_instance, partner_id, user_id, message)
            elif message.photo:
                await send_photo(bot_instance, partner_id, user_id, message)
            elif message.voice:
                await send_voice(bot_instance, partner_id, user_id, message)
            elif message.video:
                await send_video(bot_instance, partner_id, user_id, message)
            elif message.video_note:
                await send_video_note(bot_instance, partner_id, user_id, message)
            elif message.sticker:
                await send_sticker(bot_instance, partner_id, user_id, message)
        
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Таймаут отправки")
        except Exception as send_error:
            logger.error(f"❌ Ошибка отправки: {send_error}")
    
    except Exception as e:
        logger.error(f"❌ Критическая: {e}")

async def vote_callback(callback: CallbackQuery, state: FSMContext):
    try:
        user_id = callback.from_user.id
        data_parts = callback.data.split('_')
        vote_type = data_parts[1]
        chat_id = data_parts[2]
        partner_id = int(data_parts[3])
        
        db.save_vote(user_id, partner_id, chat_id, vote_type)
        
        vote_text = "👍 Вы оценили собеседника позитивно" if vote_type == "positive" else "👎 Вы оценили собеседника негативно"
        
        await callback.message.edit_text(
            f"📑 <b>Оценка принята!</b>\n\n{vote_text}\n\n🌟 Паспорт одного пользователя увеличивает его рейтинг и помогает нам находить только респектабельных пользователей",
            reply_markup=get_main_menu()
        )
        
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def report_callback(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_text(
            "🚨 <b>Отчет собеседника</b>\n\nВыберите причину репорта:",
            reply_markup=None
        )
        data_parts = callback.data.split('_')
        chat_id = data_parts[1]
        partner_id = int(data_parts[2])
        await state.set_state(UserStates.waiting_report)
        await state.update_data(chat_id=chat_id, partner_id=partner_id)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def search_start_callback(callback: CallbackQuery, state: FSMContext):
    global user_fsm_contexts
    try:
        user_id = callback.from_user.id
        user = db.get_user(user_id)
        user_fsm_contexts[user_id] = state
        
        if user_id in active_chats:
            await callback.answer("⚠️ Вы уже в диалоге", show_alert=True)
            return
        
        await callback.answer()
        await callback.message.edit_text("🔍 <b>Поиск собеседника...</b>")
        partner_id, chat_id = await find_partner(user_id, 'random', {}, bot_instance, state)
        
        if partner_id:
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=chat_id, partner_id=partner_id, category='random')
            await callback.message.edit_text("🌟 <b>Новый собеседник!</b>\n\n💬 Диалог начат. Напишите /next чтобы перейти к следующему", reply_markup=get_chat_actions_keyboard())
        else:
            await callback.message.edit_text("⏳ <b>Ожидание собеседника...</b>\n\n🔍 Мы ищем нового собеседника для вас")
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=None, partner_id=None, category='random')
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def next_partner_callback(callback: CallbackQuery, state: FSMContext):
    global active_chats, waiting_users
    try:
        user_id = callback.from_user.id
        data = await state.get_data()
        chat_id = data.get('chat_id')
        partner_id = data.get('partner_id')
        
        if chat_id and partner_id:
            db.end_chat(chat_id)
            active_chats.pop(user_id, None)
            active_chats.pop(partner_id, None)
            
            # 📣 ОУВЕДОМЛЯЕМ ПАРТНЕРА
            await safe_send_message(
                partner_id,
                "📑 <b>Оцените собеседника</b>\n\n👍 Нравится или Не нравится? Ваша оценка важна!",
                reply_markup=get_vote_keyboard(chat_id, user_id)
            )
        
        await state.clear()
        await callback.message.edit_text("🔍 <b>Поиск собеседника...</b>")
        partner_id, chat_id = await find_partner(user_id, 'random', {}, bot_instance, state)
        
        if partner_id:
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=chat_id, partner_id=partner_id, category='random')
            await callback.message.edit_text("🌟 <b>Новый собеседник!</b>\n\n💬 Диалог начат. Напишите /next чтобы перейти к следующему", reply_markup=get_chat_actions_keyboard())
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def end_chat_callback(callback: CallbackQuery, state: FSMContext):
    global active_chats
    try:
        user_id = callback.from_user.id
        data = await state.get_data()
        chat_id = data.get('chat_id')
        partner_id = data.get('partner_id')
        
        if chat_id and partner_id:
            db.end_chat(chat_id)
            active_chats.pop(user_id, None)
            active_chats.pop(partner_id, None)
            
            # 📣 ОУВЕДОМЛЯЕМ ОБОИХ - ОБА ПОЛУЧАЮТ НОВОЕ СООБЩЕНИЕ!
            voting_message = "📑 <b>Оцените собеседника</b>\n\n👍 Нравится или Не нравится? Ваша оценка важна!"
            
            # ПРОВЕРКА: если партнёр ещё в диалоге
            if partner_id in active_chats:
                # ПАРТНЁР ЕЩЁ В ДИАЛОГЕ - ОТПРАВЛЯЕм НОВОЕ СООБЩЕНИЕ
                await safe_send_message(
                    partner_id,
                    voting_message,
                    reply_markup=get_vote_keyboard(chat_id, user_id)
                )
            
            # ОБНОВЛЯЕМ СООБЩЕНИЕ ДЛЯ ТЕКУЩЕГО ПОЛьЗОВАТЕЛЯ
            await callback.message.edit_text(
                voting_message,
                reply_markup=get_vote_keyboard(chat_id, partner_id)
            )
            
            logger.info(f"📣 ОБА пользователя идентично видят голосование")
        
        await state.clear()
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
        dp.message.register(cmd_next, Command("next"))
        dp.message.register(cmd_stop, Command("stop"))
        
        dp.callback_query.register(search_start_callback, F.data == "search_start")
        dp.callback_query.register(next_partner_callback, F.data == "next_partner")
        dp.callback_query.register(end_chat_callback, F.data == "end_chat")
        dp.callback_query.register(vote_callback, F.data.startswith("vote_"))
        dp.callback_query.register(report_callback, F.data.startswith("report_"))
        
        dp.message.register(handle_chat_message, UserStates.in_chat)
        
        logger.info("✅ БОТ СТАРТОВАЛ")
        logger.info("📶 ОБА ПОЛЬЗОВАТЕЛЯ ВОИДЯТ ОДИНАКОВОЕ СООБЩЕНИЕ")
        logger.info("📣 НОВОЕ СООБЩЕНИЕ У ОБОИХ")
        logger.info("✅ ОБА МОГУТ ОЦЕНИТЬ ДРУГ ДРУГА")
        logger.info("🌟 ДИАЛОГ КОМЭЮ КОМЭЮ")
        await dp.start_polling(bot_instance)
    except Exception as e:
        logger.error(f"❌ Критическая: {e}")
    finally:
        if bot_instance:
            await bot_instance.session.close()

if __name__ == "__main__":
    asyncio.run(main())
