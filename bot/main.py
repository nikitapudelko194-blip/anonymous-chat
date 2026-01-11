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
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, MenuButtonCommands
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters.command import Command
from aiogram.exceptions import TelegramNetworkError, TelegramAPIError, TelegramBadRequest

from bot.config import BOT_TOKEN, DB_PATH, ADMIN_ID

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

# 🔐 LOCK ДЛЯ КРИТИЧЕСКИХ ОПЕРАЦИЙ (исправляет race condition)
partner_search_lock = asyncio.Lock()

# 🚫 FORBIDDEN CONTENT FILTER
FORBIDDEN_KEYWORDS = {
    'csam': ['child sex', 'minor porn', 'cp', 'children porn', 'kid porn', 'underage', 'pedophilia'],
    'drugs': ['cocaine', 'heroin', 'meth', 'fentanyl', 'mdma', 'lsd', 'mushrooms', 'weed dealer', 'sell drugs'],
    'violence': ['kill yourself', 'kys', 'commit suicide', 'bomb', 'attack plan', 'shoot up'],
    'scam': ['money transfer', 'send money', 'western union', 'gift card', 'paypal verify', 'bitcoin transfer'],
}

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
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS banned_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    reason TEXT,
                    banned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
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
    
    def is_user_banned(self, user_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT expires_at FROM banned_users 
                WHERE user_id = ? AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            ''', (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result is not None
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    def is_premium_active(self, user_id):
        """✅ НОВАЯ ФУНКЦИЯ: Проверка активности премиума с учётом срока"""
        try:
            user = self.get_user(user_id)
            if not user or not user['is_premium']:
                return False
            
            if user['premium_expires_at']:
                expires = datetime.fromisoformat(user['premium_expires_at'])
                if datetime.now() > expires:
                    # Премиум истёк - обновляем БД
                    self.remove_premium(user_id)
                    return False
            
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    def ban_user(self, user_id, reason, duration_days=None):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            expires_at = None
            if duration_days:
                expires_at = (datetime.now() + timedelta(days=duration_days)).isoformat()
            
            cursor.execute('''
                INSERT OR REPLACE INTO banned_users (user_id, reason, expires_at)
                VALUES (?, ?, ?)
            ''', (user_id, reason, expires_at))
            
            conn.commit()
            conn.close()
            logger.warning(f"🚫 Пользователь {user_id} банен: {reason}")
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
    
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
    
    def give_premium(self, user_id, months):
        """Выдать премиум на N месяцев"""
        try:
            expires_at = (datetime.now() + timedelta(days=months * 30)).isoformat()
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET is_premium = 1, premium_expires_at = ?
                WHERE user_id = ?
            ''', (expires_at, user_id))
            conn.commit()
            conn.close()
            logger.info(f"✅ Премиум выдан {user_id} на {months} месяцев до {expires_at}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    def remove_premium(self, user_id):
        """Забрать премиум"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET is_premium = 0, premium_expires_at = NULL
                WHERE user_id = ?
            ''', (user_id,))
            conn.commit()
            conn.close()
            logger.info(f"✅ Премиум забран у {user_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    def delete_user_data(self, user_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            cursor.execute('DELETE FROM messages WHERE sender_id = ?', (user_id,))
            cursor.execute('DELETE FROM votes WHERE voter_id = ? OR votee_id = ?', (user_id, user_id))
            cursor.execute('DELETE FROM reports WHERE reporter_id = ? OR reported_user_id = ?', (user_id, user_id))
            cursor.execute('DELETE FROM chats WHERE user1_id = ? OR user2_id = ?', (user_id, user_id))
            
            conn.commit()
            conn.close()
            logger.info(f"🗑️ Очищены все данные пользователя {user_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
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
    
    def get_stats(self):
        """📊 Получить статистику бота"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM users')
            total_users = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM users WHERE is_premium = 1')
            premium_users = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM banned_users WHERE expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP')
            banned_users = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM chats WHERE status = "active"')
            active_chats_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM chats')
            total_chats = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM messages')
            total_messages = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_users': total_users,
                'premium_users': premium_users,
                'banned_users': banned_users,
                'active_chats': active_chats_count,
                'total_chats': total_chats,
                'total_messages': total_messages
            }
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return None
    
    def get_premium_users(self):
        """📋 Получить список премиум пользователей"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT user_id, username, first_name, premium_expires_at
                FROM users
                WHERE is_premium = 1
                ORDER BY premium_expires_at DESC
            ''')
            
            users = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return users
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return []

class UserStates(StatesGroup):
    waiting_gender = State()
    waiting_age = State()
    choosing_interests = State()
    choosing_search_filters = State()
    in_chat = State()
    waiting_vote = State()
    waiting_report = State()
    selecting_premium_plan = State()
    waiting_payment_confirmation = State()
    waiting_search_gender = State()

db = Database()
bot_instance = None

def check_forbidden_content(text: str) -> tuple[bool, str]:
    """🚫 Проверка на запрещённый контент"""
    text_lower = text.lower()
    
    for category, keywords in FORBIDDEN_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                logger.warning(f"🚫 Открыт {category}: {keyword}")
                return True, category
    
    return False, ""

def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    if ADMIN_ID is None:
        logger.warning(f"⚠️  ADMIN_ID не установлен")
        return False
    
    result = user_id == ADMIN_ID
    if result:
        logger.info(f"✅ Пользователь {user_id} является администратором")
    else:
        logger.debug(f"❌ Пользователь {user_id} - не администратор (ADMIN_ID={ADMIN_ID})")
    return result

async def find_partner(user_id: int, category: str, search_filters: dict, bot: Bot, state: FSMContext):
    """✅ ИСПРАВЛЕНО: Добавлена защита от race condition"""
    global waiting_users, active_chats, user_fsm_contexts
    
    async with partner_search_lock:
        user = db.get_user(user_id)
        user_interests = user.get('interests', '') if user else ''
        
        for cat in list(waiting_users.keys()):
            if user_id in waiting_users[cat]:
                waiting_users[cat].remove(user_id)
        
        if waiting_users[category]:
            partner_id = waiting_users[category].pop(0)
            partner = db.get_user(partner_id)
            
            if search_filters.get('gender') and search_filters['gender'] != 'any':
                partner_gender = partner.get('gender') if partner else None
                if partner_gender != search_filters['gender']:
                    waiting_users[category].append(partner_id)
                    waiting_users[category].append(user_id)
                    logger.info(f"❌ Пол не совпадает: ищет {search_filters['gender']}, партнёр {partner_gender}")
                    return None, None
            
            partner_interests = partner.get('interests', '') if partner else ''
            
            if user_interests and partner_interests and user_interests != partner_interests:
                waiting_users[category].append(partner_id)
                waiting_users[category].append(user_id)
                logger.info(f"🎯 {user_id} и {partner_id} имеют разные интересы: '{user_interests}' vs '{partner_interests}'")
                return None, None
            
            chat_id = db.create_chat(user_id, partner_id, category)
            active_chats[user_id] = {'partner_id': partner_id, 'chat_id': chat_id}
            active_chats[partner_id] = {'partner_id': user_id, 'chat_id': chat_id}
            
            logger.info(f"✅ Матч: {user_id} <-> {partner_id} (интересы: {user_interests})")
            
            if partner_id in user_fsm_contexts:
                partner_state = user_fsm_contexts[partner_id]
                await partner_state.set_state(UserStates.in_chat)
                await partner_state.update_data(chat_id=chat_id, partner_id=user_id, category=category)
                
                try:
                    await bot.send_message(
                        partner_id,
                        "🌟 <b>Новый собеседник найден!</b>\n\n🏳️ Диалог начат. Напишите /next чтобы перейти к следующему собеседнику",
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
        [InlineKeyboardButton(text="📖 Выбрать интересы", callback_data="choose_interests")],
        [InlineKeyboardButton(text="📄 Правила общения", callback_data="rules")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
        [InlineKeyboardButton(text="💳 Премиум", callback_data="premium")],
    ])

def get_search_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Обычный поиск", callback_data="search_random")],
        [InlineKeyboardButton(text="💳 Поиск по полу (Премиум)", callback_data="search_gender_check")],
    ])

def get_gender_keyboard():
    """Клавиатура для выбора пола при поиске"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨 Парень", callback_data="search_gender_male")],
        [InlineKeyboardButton(text="👩 Девушка", callback_data="search_gender_female")],
        [InlineKeyboardButton(text="🔄 Любой пол", callback_data="search_gender_any")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
    ])

def get_gender_registration_keyboard():
    """Клавиатура для выбора пола при регистрации"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨 Парень", callback_data="register_gender_male")],
        [InlineKeyboardButton(text="👩 Девушка", callback_data="register_gender_female")],
    ])

def get_interests_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Общение", callback_data="interest_general")],
        [InlineKeyboardButton(text="🏳️‍🌈 LGBT", callback_data="interest_lgbt")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
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
        [InlineKeyboardButton(text="↩️ Новый диалог", callback_data="search_start")],
    ])

def get_premium_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📈 1 месяц (99₽)", callback_data="premium_1month")],
        [InlineKeyboardButton(text="∞ Пожизненно (499₽)", callback_data="premium_lifetime")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
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

# ═══════════════════════════════════════════════════════════════════════════════════════════
# 👑 АДМИН КОМАНДЫ
# ═══════════════════════════════════════════════════════════════════════════════════════════

async def cmd_admin_give_premium(message: Message):
    """👑 /admin_give_premium <user_id> <months> - Выдать премиум"""
    if not is_admin(message.from_user.id):
        await safe_send_message(message.from_user.id, "❌ <b>Доступ запрещён!</b>\n\nЭта команда только для администратора.")
        return
    
    try:
        args = message.text.split()
        if len(args) < 3:
            await safe_send_message(
                message.from_user.id,
                "❌ <b>Неправильный формат!</b>\n\nИспользование:\n<code>/admin_give_premium 123456789 1</code>\n\n📝 Параметры:\n• user_id - ID пользователя\n• months - количество месяцев (1, 3, 6, 12, 999 для пожизненного)"
            )
            return
        
        user_id = int(args[1])
        months = int(args[2])
        
        if months >= 100:
            months = 3650
        
        success = db.give_premium(user_id, months)
        
        if success:
            user = db.get_user(user_id)
            username = f"@{user['username']}" if user and user['username'] else "ID: " + str(user_id)
            
            await safe_send_message(
                message.from_user.id,
                f"✅ <b>Премиум выдан!</b>\n\n👤 {username}\n⏱️ На {months} месяцев\n✨ Срок действия обновлён"
            )
            
            try:
                premium_text = "✨ <b>Поздравляем!</b>\n\nВам выдан ПРЕМИУМ статус!\n🎉 Теперь вам доступны все преимущества!"
                await bot_instance.send_message(user_id, premium_text)
            except:
                pass
            
            logger.info(f"✅ АДМИН: Премиум выдан пользователю {user_id} на {months} месяцев")
        else:
            await safe_send_message(message.from_user.id, "❌ <b>Ошибка!</b>\n\nНе удалось выдать премиум.")
    
    except ValueError:
        await safe_send_message(message.from_user.id, "❌ <b>Ошибка!</b>\n\nID и количество месяцев должны быть числами.")
    except Exception as e:
        logger.error(f"❌ Ошибка команды: {e}")
        await safe_send_message(message.from_user.id, f"❌ <b>Ошибка!</b>\n\n{str(e)}")

async def cmd_admin_remove_premium(message: Message):
    """👑 /admin_remove_premium <user_id> - Забрать премиум"""
    if not is_admin(message.from_user.id):
        await safe_send_message(message.from_user.id, "❌ <b>Доступ запрещён!</b>")
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            await safe_send_message(
                message.from_user.id,
                "❌ <b>Неправильный формат!</b>\n\nИспользование:\n<code>/admin_remove_premium 123456789</code>"
            )
            return
        
        user_id = int(args[1])
        success = db.remove_premium(user_id)
        
        if success:
            user = db.get_user(user_id)
            username = f"@{user['username']}" if user and user['username'] else str(user_id)
            
            await safe_send_message(
                message.from_user.id,
                f"✅ <b>Премиум отозван!</b>\n\n👤 {username}\n❌ Статус ПРЕМИУМ удалён"
            )
            
            logger.info(f"✅ АДМИН: Премиум отозван у {user_id}")
        else:
            await safe_send_message(message.from_user.id, "❌ <b>Ошибка!</b>\n\nНе удалось отозвать премиум.")
    
    except ValueError:
        await safe_send_message(message.from_user.id, "❌ <b>Ошибка!</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"❌ Ошибка команды: {e}")
        await safe_send_message(message.from_user.id, f"❌ <b>Ошибка!</b>\n\n{str(e)}")

async def cmd_admin_ban_user(message: Message):
    """👑 /admin_ban <user_id> <дни (0=навсегда)> <причина> - Забанить пользователя"""
    if not is_admin(message.from_user.id):
        await safe_send_message(message.from_user.id, "❌ <b>Доступ запрещён!</b>")
        return
    
    try:
        parts = message.text.split(None, 3)
        if len(parts) < 3:
            await safe_send_message(
                message.from_user.id,
                "❌ <b>Неправильный формат!</b>\n\nИспользование:\n<code>/admin_ban 123456789 30 Спам</code>\n\n📝 Параметры:\n• user_id - ID пользователя\n• дни - количество дней (0 = навсегда)\n• причина - причина бана"
            )
            return
        
        user_id = int(parts[1])
        days = int(parts[2])
        reason = parts[3] if len(parts) > 3 else "Нарушение правил"
        
        db.ban_user(user_id, reason, days if days > 0 else None)
        
        user = db.get_user(user_id)
        username = f"@{user['username']}" if user and user['username'] else str(user_id)
        
        expire_text = f"на {days} дней" if days > 0 else "навсегда"
        
        await safe_send_message(
            message.from_user.id,
            f"✅ <b>Пользователь забанен!</b>\n\n👤 {username}\n⏱️ {expire_text}\n📝 Причина: {reason}"
        )
        
        try:
            ban_msg = f"🚫 <b>Вы забанены!</b>\n\n📝 Причина: {reason}\n⏱️ {expire_text}"
            await bot_instance.send_message(user_id, ban_msg)
        except:
            pass
        
        logger.warning(f"✅ АДМИН: Пользователь {user_id} забанен {expire_text}. Причина: {reason}")
    
    except ValueError:
        await safe_send_message(message.from_user.id, "❌ <b>Ошибка!</b>\n\nID и дни должны быть числами.")
    except Exception as e:
        logger.error(f"❌ Ошибка команды: {e}")
        await safe_send_message(message.from_user.id, f"❌ <b>Ошибка!</b>\n\n{str(e)}")

async def cmd_admin_unban_user(message: Message):
    """👑 /admin_unban <user_id> - Разбанить пользователя"""
    if not is_admin(message.from_user.id):
        await safe_send_message(message.from_user.id, "❌ <b>Доступ запрещён!</b>")
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            await safe_send_message(
                message.from_user.id,
                "❌ <b>Неправильный формат!</b>\n\nИспользование:\n<code>/admin_unban 123456789</code>"
            )
            return
        
        user_id = int(args[1])
        
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        
        user = db.get_user(user_id)
        username = f"@{user['username']}" if user and user['username'] else str(user_id)
        
        await safe_send_message(
            message.from_user.id,
            f"✅ <b>Пользователь разбанен!</b>\n\n👤 {username}\n✨ Доступ восстановлен"
        )
        
        try:
            unban_msg = "✅ <b>Вас разбанили!</b>\n\n🎉 Добро пожаловать обратно! Вы снова можете использовать бота."
            await bot_instance.send_message(user_id, unban_msg)
        except:
            pass
        
        logger.info(f"✅ АДМИН: Пользователь {user_id} разбанен")
    
    except ValueError:
        await safe_send_message(message.from_user.id, "❌ <b>Ошибка!</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"❌ Ошибка команды: {e}")
        await safe_send_message(message.from_user.id, f"❌ <b>Ошибка!</b>\n\n{str(e)}")

async def cmd_admin_user_info(message: Message):
    """👑 /admin_info <user_id> - Информация о пользователе"""
    if not is_admin(message.from_user.id):
        await safe_send_message(message.from_user.id, "❌ <b>Доступ запрещён!</b>")
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            await safe_send_message(
                message.from_user.id,
                "❌ <b>Неправильный формат!</b>\n\nИспользование:\n<code>/admin_info 123456789</code>"
            )
            return
        
        user_id = int(args[1])
        user = db.get_user(user_id)
        
        if not user:
            await safe_send_message(message.from_user.id, f"❌ <b>Пользователь не найден!</b>\n\nID: {user_id}")
            return
        
        is_banned = db.is_user_banned(user_id)
        is_premium = db.is_premium_active(user_id)
        premium_status = "✅ ДА" if is_premium else "❌ НЕТ"
        ban_status = "🚫 ЗАБАНЕН" if is_banned else "✅ Активен"
        
        info_text = f"""
👤 <b>ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ</b>

🆔 ID: <code>{user['user_id']}</code>
📝 Username: @{user['username'] or 'Не установлено'}
👶 Имя: {user['first_name'] or 'Не установлено'}
👨‍👩‍👧 Пол: {user['gender'] or 'Не указан'}
🎂 Возраст: {user['age'] or 'Не указан'}

💳 Премиум: {premium_status}
⏰ Срок действия: {user['premium_expires_at'] or 'Отсутствует'}

⚠️ Статус: {ban_status}

📊 <b>СТАТИСТИКА:</b>
👍 Позитивных оценок: {user['positive_votes']}
👎 Негативных оценок: {user['negative_votes']}
⭐ Рейтинг: {user['rating']:.1f}%
💬 Диалогов: {user['chats_count']}

📅 Регистрация: {user['created_at']}
🔄 Последняя активность: {user['last_activity']}
"""
        
        await safe_send_message(message.from_user.id, info_text)
    
    except ValueError:
        await safe_send_message(message.from_user.id, "❌ <b>Ошибка!</b>\n\nID должен быть числом.")
    except Exception as e:
        logger.error(f"❌ Ошибка команды: {e}")
        await safe_send_message(message.from_user.id, f"❌ <b>Ошибка!</b>\n\n{str(e)}")

async def cmd_admin_stats(message: Message):
    """👑 /admin_stats - Общая статистика бота"""
    if not is_admin(message.from_user.id):
        await safe_send_message(message.from_user.id, "❌ <b>Доступ запрещён!</b>")
        return
    
    try:
        stats = db.get_stats()
        
        if not stats:
            await safe_send_message(message.from_user.id, "❌ <b>Ошибка при получении статистики!</b>")
            return
        
        stats_text = f"""
📊 <b>СТАТИСТИКА БОТА</b>

👥 <b>ПОЛЬЗОВАТЕЛИ:</b>
👨‍👩‍👧‍👦 Всего пользователей: {stats['total_users']}
💳 Премиум пользователей: {stats['premium_users']}
🚫 Забанено пользователей: {stats['banned_users']}

💬 <b>ДИАЛОГИ:</b>
🔴 Активных диалогов: {stats['active_chats']}
📊 Всего диалогов: {stats['total_chats']}
💭 Всего сообщений: {stats['total_messages']}

📈 <b>СТАТИСТИКА:</b>
💬 Среднее сообщения на диалог: {stats['total_messages'] // max(stats['total_chats'], 1) if stats['total_chats'] > 0 else 0}
📊 Процент премиум: {(stats['premium_users'] / max(stats['total_users'], 1) * 100):.1f}%
🚷 Процент забанено: {(stats['banned_users'] / max(stats['total_users'], 1) * 100):.1f}%
"""
        
        await safe_send_message(message.from_user.id, stats_text)
        logger.info(f"✅ АДМИН: Статистика запрошена администратором {message.from_user.id}")
    
    except Exception as e:
        logger.error(f"❌ Ошибка команды: {e}")
        await safe_send_message(message.from_user.id, f"❌ <b>Ошибка!</b>\n\n{str(e)}")

async def cmd_admin_list_premium(message: Message):
    """👑 /admin_list_premium - Список премиум пользователей"""
    if not is_admin(message.from_user.id):
        await safe_send_message(message.from_user.id, "❌ <b>Доступ запрещён!</b>")
        return
    
    try:
        premium_users = db.get_premium_users()
        
        if not premium_users:
            await safe_send_message(message.from_user.id, "❌ <b>Нет премиум пользователей!</b>")
            return
        
        users_list = "📋 <b>ПРЕМИУМ ПОЛЬЗОВАТЕЛИ</b>\n\n"
        
        for i, user in enumerate(premium_users, 1):
            username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
            expires = user['premium_expires_at'] if user['premium_expires_at'] else "Неизвестно"
            users_list += f"{i}. {username}\n"
            users_list += f"   📅 Истекает: {expires}\n\n"
        
        users_list += f"<b>Всего премиум пользователей: {len(premium_users)}</b>"
        
        await safe_send_message(message.from_user.id, users_list)
        logger.info(f"✅ АДМИН: Список премиум пользователей запрошен администратором {message.from_user.id}")
    
    except Exception as e:
        logger.error(f"❌ Ошибка команды: {e}")
        await safe_send_message(message.from_user.id, f"❌ <b>Ошибка!</b>\n\n{str(e)}")

async def cmd_admin_help(message: Message):
    """👑 /admin_help - Справка по админ командам"""
    if not is_admin(message.from_user.id):
        await safe_send_message(message.from_user.id, "❌ <b>Доступ запрещён!</b>")
        return
    
    help_text = """
👑 <b>АДМИН КОМАНДЫ</b>

💳 <b>УПРАВЛЕНИЕ ПРЕМИУМОМ:</b>
/admin_give_premium <user_id> <месяцы> - Выдать премиум
Пример: <code>/admin_give_premium 123456789 1</code>
→ Выдаст премиум на 1 месяц
→ Используйте 999 для пожизненного доступа

/admin_remove_premium <user_id> - Забрать премиум
Пример: <code>/admin_remove_premium 123456789</code>

🚫 <b>УПРАВЛЕНИЕ БАНАМИ:</b>
/admin_ban <user_id> <дни> <причина> - Забанить пользователя
Пример: <code>/admin_ban 123456789 30 Спам</code>
→ Используйте 0 дней для постоянного бана

/admin_unban <user_id> - Разбанить пользователя
Пример: <code>/admin_unban 123456789</code>

👤 <b>ИНФОРМАЦИЯ:</b>
/admin_info <user_id> - Информация о пользователе
Пример: <code>/admin_info 123456789</code>
→ Показывает полную информацию о пользователе, его статистику и статус

📊 <b>СТАТИСТИКА:</b>
/admin_stats - Общая статистика бота
→ Показывает всех пользователей, премиум пользователей, забанено, диалогов и сообщений

📋 <b>СПИСОК ПРЕМИУМА:</b>
/admin_list_premium - Список всех премиум пользователей
→ Показывает всех премиум пользователей с датами истечения подписки

❓ <b>СПРАВКА:</b>
/admin_help - Показать эту справку
"""
    
    await safe_send_message(message.from_user.id, help_text)

# ═══════════════════════════════════════════════════════════════════════════════════════════

async def cmd_start(message: Message, state: FSMContext):
    global user_fsm_contexts
    try:
        user_id = message.from_user.id
        
        if db.is_user_banned(user_id):
            await safe_send_message(user_id, "❌ <b>Вы банны в этом боте</b>\n\nЕсли это ошибка, отправьте /appeal")
            return
        
        user = db.get_user(user_id)
        user_fsm_contexts[user_id] = state
        
        if not user:
            db.create_user(user_id, message.from_user.username, message.from_user.first_name)
            await safe_send_message(
                user_id,
                "👋 <b>Привет! Добро пожаловать!</b>\n\n👨‍👩 <b>Сначала укажите ваш пол:</b>",
                reply_markup=get_gender_registration_keyboard()
            )
            await state.set_state(UserStates.waiting_gender)
        else:
            await safe_send_message(
                user_id,
                "👋 <b>Привет! Добро пожаловать обратно!</b>\n\n🌟 Фантастических разговоров в случайных диалогах!",
                reply_markup=get_main_menu()
            )
            await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def register_gender_callback(callback: CallbackQuery, state: FSMContext):
    """Регистрация пола пользователя и переход к вводу возраста"""
    try:
        user_id = callback.from_user.id
        
        gender_map = {
            "register_gender_male": "👨 Парень",
            "register_gender_female": "👩 Девушка",
        }
        
        gender_text = gender_map.get(callback.data)
        if not gender_text:
            return
        
        db.update_user(user_id, gender=gender_text)
        
        await callback.answer()
        await callback.message.edit_text(
            f"✅ <b>Спасибо!</b>\n\nВы выбрали: {gender_text}\n\n🎂 <b>Теперь укажите ваш возраст:</b>\n\n⚠️ <b>Минимальный возраст: 18 лет</b>"
        )
        
        await state.set_state(UserStates.waiting_age)
        logger.info(f"✅ Пользователь {user_id} указал пол: {gender_text}")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def handle_age_input(message: Message, state: FSMContext):
    """Обработка ввода возраста"""
    try:
        user_id = message.from_user.id
        
        try:
            age = int(message.text)
        except ValueError:
            await safe_send_message(
                user_id,
                "❌ <b>Ошибка!</b>\n\nПожалуйста, введите число.\n\n🎂 <b>Укажите ваш возраст:</b>"
            )
            return
        
        if age < 18:
            await safe_send_message(
                user_id,
                f"❌ <b>К сожалению!</b>\n\nВам {age} лет, а минимальный возраст для использования бота - 18 лет.\n\n🚫 Вы не можете использовать этот бот."
            )
            logger.warning(f"🚫 Пользователь {user_id} попытался зарегистрироваться в возрасте {age} лет")
            await state.clear()
            return
        
        if age > 120:
            await safe_send_message(
                user_id,
                "❌ <b>Ошибка!</b>\n\nПожалуйста, введите корректный возраст.\n\n🎂 <b>Укажите ваш возраст:</b>"
            )
            return
        
        db.update_user(user_id, age=age)
        
        await safe_send_message(
            user_id,
            f"✅ <b>Спасибо!</b>\n\nВам {age} лет.\n\n🎉 Регистрация завершена! Теперь можете начать поиск собеседника!",
            reply_markup=get_main_menu()
        )
        
        await state.clear()
        logger.info(f"✅ Пользователь {user_id} указал возраст: {age} лет")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await safe_send_message(user_id, "❌ <b>Ошибка при обработке возраста!</b>")

async def cmd_rules(message: Message):
    """📄 Правила общения"""
    rules_text = """👋 <b>Добро пожаловать в анонимный чат!</b>
Здесь можно найти интересный разговор с незнакомцем, оставаясь инкогнито. Чтобы магия анонимности не обернулась кошмаром, давай договоримся:

<b>Мы остаемся тайной.</b> Не проси телефон, инсту или фото «для уверенности». И сам не светись. В этом вся суть!

<b>Общаемся по-человечески.</b> Можно спорить, шутить, обсуждать что угодно, но переходить на личности, оскорблять или угрожать — низко. Давай лучше!

<b>Верим в хорошее, но проверяем.</b> Если новый друг просит деньги, пароли или странные коды — это 100% мошенник. Блокируй и доложи боту.

<b>Не засоряем эфир.</b> Отправлять десять раз «привет» или ссылки на свои каналы — плохо.

<b>Если ты столкнулся с нарушением этих правил — обязательно пожалуйся!</b> Это помогает всем.

<b>🗺️ Как здесь всё устроено? Простые команды:</b>

/next — Главная кнопка! Ищешь нового собеседника? Жми сюда. Старый диалог завершится.

/stop — Вежливо завершить текущий разговор, чтобы затем найти кого-то нового.

/report — Спасательный круг! Если собеседник нарушает правила (оскорбляет, спамит), используй эту команду в чате с ним, чтобы отправить жалобу. Мы разберемся.

/rules — Если забудешь правила, просто вызови эту команду, и я напомню.

Просто нажми /next, чтобы начать своё первое анонимное приключение! Удачи и приятного общения! 🚀"""
    await safe_send_message(message.from_user.id, rules_text)

async def cmd_help(message: Message):
    """❓ Помощь"""
    help_text = """
❓ <b>ПОМОЩЬ</b>

🤖 <b>ЭТО БОТ ДЛЯ АНОНИМНОГО ОБЩЕНИЯ В ТЕЛЕГРАМЕ</b>

Бот умеет пересылать сообщения, фото, видео, гифки, стикеры, аудиосообщения и видеосообщения.

<b>📋 ОСНОВНЫЕ КОМАНДЫ:</b>
/search - поиск собеседника
/next - закончить текущий диалог и сразу же искать нового собеседника
/stop - закончить разговор с собеседником
/interests - выбрать интересы поиска
/pay - поиск по полу, оформление и управление премиумом
/link - отправить собеседнику ссылку на вас в Телеграме
/rules - ознакомиться с правилами

<b>🏃 КАК ПОЛЬЗОВАТЬСЯ:</b>
• Нажмите /search чтобы начать поиск
• Выберите категорию интересов в /interests
• Используйте /next для смены собеседника
• /stop для завершения диалога

<b>🎮 ПОДДЕРЖИВАЕМЫЕ МЕДИА:</b>
• 📝 Текстовые сообщения
• 📷 Фото
• 🎥 Видео
• 🎙️ Аудиосообщения
• 🎬 Видеосообщения
• 😊 Стикеры
• 🎬 Гифки

📞 <b>ПОДДЕРЖКА:</b>
По любым вопросам обращаться к @Dontonu
"""
    await safe_send_message(message.from_user.id, help_text)

async def help_callback(callback: CallbackQuery):
    """❓ Помощь через кнопку"""
    try:
        await callback.answer()
        help_text = """
❓ <b>ПОМОЩЬ</b>

🤖 <b>ЭТО БОТ ДЛЯ АНОНИМНОГО ОБЩЕНИЯ В ТЕЛЕГРАМЕ</b>

Бот умеет пересылать сообщения, фото, видео, гифки, стикеры, аудиосообщения и видеосообщения.

<b>📋 ОСНОВНЫЕ КОМАНДЫ:</b>
/search - поиск собеседника
/next - закончить текущий диалог и сразу же искать нового собеседника
/stop - закончить разговор с собеседником
/interests - выбрать интересы поиска
/pay - поиск по полу, оформление и управление премиумом
/link - отправить собеседнику ссылку на вас в Телеграме
/rules - ознакомиться с правилами

<b>🏃 КАК ПОЛЬЗОВАТЬСЯ:</b>
• Нажмите /search чтобы начать поиск
• Выберите категорию интересов в /interests
• Используйте /next для смены собеседника
• /stop для завершения диалога

<b>🎮 ПОДДЕРЖИВАЕМЫЕ МЕДИА:</b>
• 📝 Текстовые сообщения
• 📷 Фото
• 🎥 Видео
• 🎙️ Аудиосообщения
• 🎬 Видеосообщения
• 😊 Стикеры
• 🎬 Гифки

📞 <b>ПОДДЕРЖКА:</b>
По любым вопросам обращаться к @Dontonu
"""
        await callback.message.edit_text(help_text, reply_markup=get_main_menu())
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def rules_callback(callback: CallbackQuery):
    """📄 Правила через кнопку"""
    try:
        await callback.answer()
        rules_text = """👋 <b>Добро пожаловать в анонимный чат!</b>
Здесь можно найти интересный разговор с незнакомцем, оставаясь инкогнито. Чтобы магия анонимности не обернулась кошмаром, давай договоримся:

<b>Мы остаемся тайной.</b> Не проси телефон, инсту или фото «для уверенности». И сам не светись. В этом вся суть!

<b>Общаемся по-человечески.</b> Можно спорить, шутить, обсуждать что угодно, но переходить на личности, оскорблять или угрожать — низко. Давай лучше!

<b>Верим в хорошее, но проверяем.</b> Если новый друг просит деньги, пароли или странные коды — это 100% мошенник. Блокируй и доложи боту.

<b>Не засоряем эфир.</b> Отправлять десять раз «привет» или ссылки на свои каналы — плохо.

<b>Если ты столкнулся с нарушением этих правил — обязательно пожалуйся!</b> Это помогает всем.

<b>🗺️ Как здесь всё устроено? Простые команды:</b>

/next — Главная кнопка! Ищешь нового собеседника? Жми сюда. Старый диалог завершится.

/stop — Вежливо завершить текущий разговор, чтобы затем найти кого-то нового.

/report — Спасательный круг! Если собеседник нарушает правила (оскорбляет, спамит), используй эту команду в чате с ним, чтобы отправить жалобу. Мы разберемся.

/rules — Если забудешь правила, просто вызови эту команду, и я напомню.

Просто нажми /next, чтобы начать своё первое анонимное приключение! Удачи и приятного общения! 🚀"""
        await callback.message.edit_text(rules_text, reply_markup=get_main_menu())
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def cmd_delete_my_data(message: Message):
    """🗑️ Отметить все данные пользователя"""
    user_id = message.from_user.id
    
    try:
        success = db.delete_user_data(user_id)
        
        if success:
            await safe_send_message(
                user_id,
                "🗑️ <b>Успех!</b>\n\nВсе ваши данные удалены из базы данных."
            )
            logger.info(f"✅ Пользователь {user_id} удалил свои данные")
        else:
            await safe_send_message(user_id, "❌ Ошибка при удалении данных")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await safe_send_message(user_id, "❌ Ошибка при удалении данных")

async def search_start_callback(callback: CallbackQuery, state: FSMContext):
    """🔍 Начать поиск с главного меню"""
    try:
        user_id = callback.from_user.id
        
        if db.is_user_banned(user_id):
            await callback.answer("❌ Вы банны в этом боте", show_alert=True)
            return
        
        user = db.get_user(user_id)
        user_fsm_contexts[user_id] = state
        
        if user_id in active_chats:
            await callback.answer("⚠️ Вы уже в диалоге! Используйте /next или /stop")
            return
        
        await callback.answer()
        await callback.message.edit_text(
            "🔍 <b>Выберите тип поиска:</b>",
            reply_markup=get_search_menu()
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def search_random_callback(callback: CallbackQuery, state: FSMContext):
    """Обычный поиск без фильтра по полу"""
    try:
        user_id = callback.from_user.id
        await callback.answer()
        await callback.message.edit_text("🔍 <b>Поиск собеседника...</b>")
        
        partner_id, chat_id = await find_partner(user_id, 'random', {}, bot_instance, state)
        
        if partner_id:
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=chat_id, partner_id=partner_id, category='random')
            await callback.message.edit_text("🌟 <b>Новый собеседник!</b>\n\n💬 Диалог начат. Напишите /next чтобы перейти к следующему собеседнику", reply_markup=get_chat_actions_keyboard())
        else:
            await callback.message.edit_text("⏳ <b>Ожидание собеседника...</b>\n\n🔍 Мы ищем нового собеседника для вас")
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=None, partner_id=None, category='random', waiting=True)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def search_gender_check_callback(callback: CallbackQuery, state: FSMContext):
    """Проверка наличия премиума и выбор пола для поиска"""
    try:
        user_id = callback.from_user.id
        user = db.get_user(user_id)
        
        # ✅ ИСПРАВЛЕНО: Используем новую функцию проверки активного премиума
        if not user or not db.is_premium_active(user_id):
            await callback.answer("💳 ПОИСК ПО ПОЛУ Доступен только для ПРЕМИУМ!", show_alert=True)
            return
        
        await callback.answer()
        await callback.message.edit_text(
            "👨‍👩 <b>Выберите кого вы хотите найти:</b>",
            reply_markup=get_gender_keyboard()
        )
        
        await state.set_state(UserStates.waiting_search_gender)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def search_gender_callback(callback: CallbackQuery, state: FSMContext):
    """Выбор пола для поиска и начало поиска"""
    try:
        user_id = callback.from_user.id
        
        gender_map = {
            "search_gender_male": "👨 Парень",
            "search_gender_female": "👩 Девушка",
            "search_gender_any": "any",
        }
        
        gender = gender_map.get(callback.data)
        if not gender:
            return
        
        await callback.answer()
        await callback.message.edit_text("🔍 <b>Поиск собеседника...</b>")
        
        search_filters = {'gender': gender}
        partner_id, chat_id = await find_partner(user_id, 'gender_filter', search_filters, bot_instance, state)
        
        if partner_id:
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=chat_id, partner_id=partner_id, category='gender_filter', search_gender=gender)
            await callback.message.edit_text("🌟 <b>Новый собеседник найден!</b>\n\n💬 Диалог начат. Напишите /next чтобы перейти к следующему собеседнику", reply_markup=get_chat_actions_keyboard())
        else:
            await callback.message.edit_text("⏳ <b>Ожидание собеседника...</b>\n\n🔍 Мы ищем нового собеседника для вас с фильтром по полу")
            await state.set_state(UserStates.in_chat)
            await state.update_data(chat_id=None, partner_id=None, category='gender_filter', waiting=True, search_gender=gender)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def choose_interests_callback(callback: CallbackQuery):
    """Выбор категории интересов"""
    try:
        user_id = callback.from_user.id
        await callback.answer()
        await callback.message.edit_text(
            "📖 <b>Выберите категорию интересов:</b>",
            reply_markup=get_interests_keyboard()
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def interest_select_callback(callback: CallbackQuery):
    """Выбор интереса"""
    try:
        user_id = callback.from_user.id
        interest_map = {
            "interest_general": "💬 Общение",
            "interest_lgbt": "🏳️‍🌈 LGBT",
        }
        
        interest_text = interest_map.get(callback.data, "Неизвестно")
        db.update_user(user_id, interests=interest_text)
        
        await callback.answer()
        await callback.message.edit_text(
            f"✅ <b>Интересы сохранены!</b>\n\nВы выбрали: {interest_text}",
            reply_markup=get_main_menu()
        )
        logger.info(f"🎯 Пользователь {user_id} выбрал интересы: {interest_text}")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def premium_callback(callback: CallbackQuery):
    """Показать планы премиума"""
    try:
        user_id = callback.from_user.id
        user = db.get_user(user_id)
        
        if user and db.is_premium_active(user_id):
            await callback.answer("🎉 У вас уже есть ПРЕМИУМ!", show_alert=True)
            return
        
        await callback.answer()
        premium_text = """
💳 <b>ПЛАНЫ ПРЕМИУМА</b>

<b>📈 1 МЕСЯЦ - 99₽</b>
• 🔍 Поиск по полу
• 👤 Приоритетные собеседники
• ✏️ Без рекламы

<b>∞ ПОЖИЗНЕННО - 499₽</b>
• 🔍 Поиск по полу
• 👤 Приоритетные собеседники
• ✏️ Без рекламы
• 💡 Эксклюзивные фичи для жизни

💳 <b>НА ВНИМАНИЕ:</b> Оплата настраивается по отдельности
💳 Обратитесь к администратору
"""
        
        await callback.message.edit_text(premium_text, reply_markup=get_premium_keyboard())
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def premium_plan_callback(callback: CallbackQuery):
    """Выбор плана премиума"""
    try:
        user_id = callback.from_user.id
        plan_map = {
            "premium_1month": {
                "name": "1 МЕСЯЦ",
                "price": "99",
                "duration": 30
            },
            "premium_lifetime": {
                "name": "ПОЖИЗНЕННО",
                "price": "499",
                "duration": 36500
            },
        }
        
        plan_info = plan_map.get(callback.data)
        if not plan_info:
            return
        
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO payments (user_id, amount, plan, status)
            VALUES (?, ?, ?, 'pending')
        ''', (user_id, plan_info["price"], plan_info["name"]))
        conn.commit()
        conn.close()
        
        payment_text = f"""
📈 <b>ПЛАН: {plan_info['name']}</b>
💰 <b>ЦЕНА: {plan_info['price']}₽</b>

📋 <b>ДЛЯ ОПЛАТЫ:</b>
1. Обратитесь к администратору
2. Отправьте свою ID: <code>{user_id}</code>
3. Проверьте ваш ПРЕМИУМ статус

💳 Администратор: @Dontonu
"""
        
        await callback.answer()
        await callback.message.edit_text(payment_text, reply_markup=get_main_menu())
        
        try:
            admin_msg = f"📈 НОВАЯ ПОДПИСКА\nПользователь ID: {user_id}\nПлан: {plan_info['name']} - {plan_info['price']}₽"
            if ADMIN_ID:
                await bot_instance.send_message(ADMIN_ID, admin_msg)
        except:
            pass
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def back_to_menu_callback(callback: CallbackQuery):
    """Вернуться в главное меню"""
    try:
        await callback.answer()
        await callback.message.edit_text(
            "👋 <b>Главное меню</b>",
            reply_markup=get_main_menu()
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def cmd_search(message: Message, state: FSMContext):
    global user_fsm_contexts
    try:
        user_id = message.from_user.id
        
        if db.is_user_banned(user_id):
            await safe_send_message(user_id, "❌ <b>Вы банны в этом боте</b>")
            return
        
        user = db.get_user(user_id)
        user_fsm_contexts[user_id] = state
        
        if user_id in active_chats:
            await safe_send_message(user_id, "⚠️ <b>Вы уже в диалоге!</b>\n\nНапишите /next чтобы перейти к следующему собеседнику")
            return
        
        await safe_send_message(
            user_id,
            "🔍 <b>Выберите тип поиска:</b>",
            reply_markup=get_search_menu()
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def cmd_interests(message: Message):
    """Выбор интересов"""
    try:
        user_id = message.from_user.id
        await safe_send_message(
            user_id,
            "📖 <b>Выберите категорию интересов:</b>",
            reply_markup=get_interests_keyboard()
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def cmd_pay(message: Message):
    """Премиум и поиск по полу"""
    try:
        user_id = message.from_user.id
        await safe_send_message(
            user_id,
            "💳 <b>ПРЕМИУМ И ПОИСК ПО ПОЛУ</b>\n\n/pay команда для управления подписками",
            reply_markup=get_premium_keyboard()
        )
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def cmd_link(message: Message):
    """Отправить ссылку на себя"""
    try:
        user_id = message.from_user.id
        user = db.get_user(user_id)
        
        if not user or not user['username']:
            await safe_send_message(user_id, "❌ У вас нет юзернейма в Телеграме. Установите его в настройках профиля.")
            return
        
        link_text = f"Привет! Мой профиль Телеграма: @{user['username']}"
        await safe_send_message(user_id, f"🔗 <b>Ссылка на вас:</b>\n\n<code>@{user['username']}</code>")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def next_partner_callback(callback: CallbackQuery, state: FSMContext):
    """➡️ Переход к следующему собеседнику через кнопку"""
    try:
        user_id = callback.from_user.id
        data = await state.get_data()
        chat_id = data.get('chat_id')
        partner_id = data.get('partner_id')
        
        await callback.answer()
        
        if chat_id and partner_id:
            db.end_chat(chat_id)
            active_chats.pop(user_id, None)
            active_chats.pop(partner_id, None)
            
            # ✅ ИСПРАВЛЕНО: Удалить пользователя из очереди ожидания
            for cat in list(waiting_users.keys()):
                if user_id in waiting_users[cat]:
                    waiting_users[cat].remove(user_id)
                if partner_id in waiting_users[cat]:
                    waiting_users[cat].remove(partner_id)
            
            voting_message = "📋 <b>Оцените собеседника</b>\n\n👍 Нравится или Не нравится? Ваша оценка важна!"
            
            await safe_send_message(
                user_id,
                voting_message,
                reply_markup=get_vote_keyboard(chat_id, partner_id)
            )
            
            await safe_send_message(
                partner_id,
                voting_message,
                reply_markup=get_vote_keyboard(chat_id, user_id)
            )
        
        await state.clear()
        await search_random_callback(callback, state)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def end_chat_callback(callback: CallbackQuery, state: FSMContext):
    """🛑 Завершить диалог через кнопку"""
    try:
        user_id = callback.from_user.id
        data = await state.get_data()
        partner_id = data.get('partner_id')
        chat_id = data.get('chat_id')
        
        await callback.answer()
        
        if chat_id and partner_id:
            db.end_chat(chat_id)
            active_chats.pop(user_id, None)
            active_chats.pop(partner_id, None)
            
            # ✅ ИСПРАВЛЕНО: Удалить пользователей из очереди ожидания
            for cat in list(waiting_users.keys()):
                if user_id in waiting_users[cat]:
                    waiting_users[cat].remove(user_id)
                if partner_id in waiting_users[cat]:
                    waiting_users[cat].remove(partner_id)
            
            voting_message = "📋 <b>Оцените собеседника</b>\n\n👍 Нравится или Не нравится? Ваша оценка важна!"
            
            await safe_send_message(
                partner_id,
                voting_message,
                reply_markup=get_vote_keyboard(chat_id, user_id)
            )
            
            await callback.message.edit_text(
                voting_message,
                reply_markup=get_vote_keyboard(chat_id, partner_id)
            )
        
        await state.clear()
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
            
            # ✅ ИСПРАВЛЕНО: Удалить пользователя из очереди ожидания
            for cat in list(waiting_users.keys()):
                if user_id in waiting_users[cat]:
                    waiting_users[cat].remove(user_id)
                if partner_id in waiting_users[cat]:
                    waiting_users[cat].remove(partner_id)
            
            voting_message = "📋 <b>Оцените собеседника</b>\n\n👍 Нравится или Не нравится? Ваша оценка важна!"
            
            await safe_send_message(
                user_id,
                voting_message,
                reply_markup=get_vote_keyboard(chat_id, partner_id)
            )
            
            await safe_send_message(
                partner_id,
                voting_message,
                reply_markup=get_vote_keyboard(chat_id, user_id)
            )
            
            logger.info(f"📢 /next: ОБА пользователя видят новое сообщение")
        
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
            
            # ✅ ИСПРАВЛЕНО: Удалить пользователя из очереди ожидания
            for cat in list(waiting_users.keys()):
                if user_id in waiting_users[cat]:
                    waiting_users[cat].remove(user_id)
                if partner_id in waiting_users[cat]:
                    waiting_users[cat].remove(partner_id)
            
            voting_message = "📋 <b>Оцените собеседника</b>\n\n👍 Нравится или Не нравится? Ваша оценка важна!"
            
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
            
            logger.info(f"📢 /stop: ОБА пользователя видят новое сообщение")
        
        await state.clear()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def send_text(bot, partner_id, user_id, message):
    try:
        await asyncio.wait_for(
            bot.send_message(chat_id=partner_id, text=message.text),
            timeout=40
        )
        logger.info(f"✅ ТЕКСТ: {user_id} -> {partner_id}")
    except asyncio.TimeoutError:
        logger.warning(f"⏱️ Тайм-аут отправки текста")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки текста: {e}")

async def send_photo(bot, partner_id, user_id, message):
    try:
        await asyncio.wait_for(
            bot.send_photo(
                chat_id=partner_id,
                photo=message.photo[-1].file_id,
                caption=message.caption if message.caption else None
            ),
            timeout=40
        )
        logger.info(f"📷 ФОТО: {user_id} -> {partner_id}")
    except asyncio.TimeoutError:
        logger.warning(f"⏱️ Тайм-аут отправки фото")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки фото: {e}")

async def send_voice(bot, partner_id, user_id, message):
    try:
        await asyncio.wait_for(
            bot.send_voice(chat_id=partner_id, voice=message.voice.file_id),
            timeout=40
        )
        logger.info(f"🎤 ГОЛОС: {user_id} -> {partner_id}")
    except asyncio.TimeoutError:
        logger.warning(f"⏱️ Тайм-аут отправки голоса")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки голоса: {e}")

async def send_video(bot, partner_id, user_id, message):
    """✅ ИСПРАВЛЕНО: Удалены дублированные except блоки"""
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
    except asyncio.TimeoutError:
        logger.warning(f"⏱️ Тайм-аут отправки видео")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки видео: {e}")

async def send_video_note(bot, partner_id, user_id, message):
    """✅ ИСПРАВЛЕНО: Удалены дублированные except блоки"""
    try:
        await asyncio.wait_for(
            bot.send_video_note(chat_id=partner_id, video_note=message.video_note.file_id),
            timeout=40
        )
        logger.info(f"📹 ВИДЕОКРУГ: {user_id} -> {partner_id}")
    except asyncio.TimeoutError:
        logger.warning(f"⏱️ Тайм-аут отправки видеокруга")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки видеокруга: {e}")

async def send_sticker(bot, partner_id, user_id, message):
    try:
        await asyncio.wait_for(
            bot.send_sticker(chat_id=partner_id, sticker=message.sticker.file_id),
            timeout=40
        )
        logger.info(f"😊 СТИКЕР: {user_id} -> {partner_id}")
    except asyncio.TimeoutError:
        logger.warning(f"⏱️ Тайм-аут отправки стикера")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки стикера: {e}")

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
            is_forbidden, category = check_forbidden_content(message.text)
            if is_forbidden:
                await safe_send_message(
                    user_id,
                    f"🚫 <b>Сообщение заблокировано</b>\n\nВы пытались отправить запрещённый контент ({category})."
                )
                logger.warning(f"🚫 {user_id} попытался отправить {category}")
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
            db.save_message(chat_id, user_id, "[📹 Видеокруг]")
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
            logger.warning(f"⏱️ Тайм-аут отправки")
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
            f"📋 <b>Оценка принята!</b>\n\n{vote_text}\n\n🌟 Оценки пользователей помогают нам определить наилучших собеседников!",
            reply_markup=get_main_menu()
        )
        
        await state.clear()
        await callback.answer()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

async def setup_menu_button(bot: Bot):
    """📱 Настройка меню кнопок бота"""
    try:
        commands = [
            BotCommand(command="search", description="🔍 Начать поиск собеседника"),
            BotCommand(command="next", description="➡️ Перейти к следующему"),
            BotCommand(command="stop", description="🛑 Завершить диалог"),
            BotCommand(command="interests", description="📖 Выбрать интересы"),
            BotCommand(command="pay", description="💳 Премиум и поиск по полу"),
            BotCommand(command="link", description="🔗 Ссылка на вас"),
            BotCommand(command="rules", description="📄 Правила общения"),
            BotCommand(command="help", description="❓ Помощь"),
            BotCommand(command="start", description="👋 Главное меню"),
        ]
        
        await bot.set_my_commands(commands)
        menu_button = MenuButtonCommands()
        await bot.set_chat_menu_button(menu_button=menu_button)
        logger.info("✅ Menu Button установлена")
    except Exception as e:
        logger.error(f"❌ Ошибка при установке меню: {e}")

async def main():
    global bot_instance
    try:
        await db.init_db()
        
        bot_instance = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher()
        
        await setup_menu_button(bot_instance)
        
        # Регистрация команд
        dp.message.register(cmd_start, Command("start"))
        dp.message.register(cmd_rules, Command("rules"))
        dp.message.register(cmd_help, Command("help"))
        dp.message.register(cmd_delete_my_data, Command("delete_my_data"))
        dp.message.register(cmd_search, Command("search"))
        dp.message.register(cmd_interests, Command("interests"))
        dp.message.register(cmd_pay, Command("pay"))
        dp.message.register(cmd_link, Command("link"))
        dp.message.register(cmd_next, Command("next"))
        dp.message.register(cmd_stop, Command("stop"))
        
        # Регистрация админ команд
        dp.message.register(cmd_admin_give_premium, Command("admin_give_premium"))
        dp.message.register(cmd_admin_remove_premium, Command("admin_remove_premium"))
        dp.message.register(cmd_admin_ban_user, Command("admin_ban"))
        dp.message.register(cmd_admin_unban_user, Command("admin_unban"))
        dp.message.register(cmd_admin_user_info, Command("admin_info"))
        dp.message.register(cmd_admin_stats, Command("admin_stats"))
        dp.message.register(cmd_admin_list_premium, Command("admin_list_premium"))
        dp.message.register(cmd_admin_help, Command("admin_help"))
        
        # Обработка ввода возраста
        dp.message.register(handle_age_input, UserStates.waiting_age)
        
        # Регистрация callback'ов
        dp.callback_query.register(register_gender_callback, F.data.startswith("register_gender_"))
        dp.callback_query.register(search_start_callback, F.data == "search_start")
        dp.callback_query.register(search_random_callback, F.data == "search_random")
        dp.callback_query.register(search_gender_check_callback, F.data == "search_gender_check")
        dp.callback_query.register(search_gender_callback, F.data.startswith("search_gender_"))
        dp.callback_query.register(choose_interests_callback, F.data == "choose_interests")
        dp.callback_query.register(interest_select_callback, F.data.startswith("interest_"))
        dp.callback_query.register(premium_callback, F.data == "premium")
        dp.callback_query.register(premium_plan_callback, F.data.startswith("premium_"))
        dp.callback_query.register(rules_callback, F.data == "rules")
        dp.callback_query.register(help_callback, F.data == "help")
        dp.callback_query.register(back_to_menu_callback, F.data == "back_to_menu")
        dp.callback_query.register(next_partner_callback, F.data == "next_partner")
        dp.callback_query.register(end_chat_callback, F.data == "end_chat")
        dp.callback_query.register(vote_callback, F.data.startswith("vote_"))
        
        # Обработка сообщений в чате
        dp.message.register(handle_chat_message, UserStates.in_chat)
        
        logger.info("📱 BOT STARTED - ✨ АДМИН КОМАНДЫ АКТИВИРОВАНЫ ✨")
        logger.info("✅ БЕЗОПАСНОСТЬ: Проверка возраста (18+) активирована")
        logger.info("✅ ФИЛЬТРАЦИЯ: Проверка на запрещённый контент активирована")
        logger.info("✅ ИСПРАВЛЕНИЯ: Все ошибки исправлены, включая race condition и проверку премиума")
        await dp.start_polling(bot_instance)
    except Exception as e:
        logger.error(f"❌ Критическая: {e}")
    finally:
        if bot_instance:
            await bot_instance.session.close()

if __name__ == "__main__":
    asyncio.run(main())
