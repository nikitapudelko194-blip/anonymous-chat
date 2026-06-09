import aiosqlite
import logging
import uuid
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path):
        self.db_path = db_path
    
    async def init_db(self):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute('''
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
                
                await conn.execute('''
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
                
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id TEXT NOT NULL,
                        reporter_id INTEGER NOT NULL,
                        reported_user_id INTEGER NOT NULL,
                        reason TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS votes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        voter_id INTEGER NOT NULL,
                        votee_id INTEGER NOT NULL,
                        chat_id TEXT NOT NULL,
                        vote_type TEXT NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                await conn.execute('''
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
                
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS banned_users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL UNIQUE,
                        reason TEXT,
                        banned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        expires_at DATETIME
                    )
                ''')
                
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS mandatory_channels (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        channel_id TEXT NOT NULL UNIQUE,
                        url TEXT NOT NULL,
                        name TEXT NOT NULL
                    )
                ''')
                
                await conn.commit()
                logger.info("✅ БД инициализирована")
        except Exception as e:
            logger.error(f"❌ Ошибка БД: {e}")
    
    async def create_user(self, user_id, username, first_name):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute('''
                    INSERT OR IGNORE INTO users (user_id, username, first_name)
                    VALUES (?, ?, ?)
                ''', (user_id, username, first_name))
                await conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка create_user: {e}")
    
    async def get_user(self, user_id):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
                    user = await cursor.fetchone()
                    return dict(user) if user else None
        except Exception as e:
            logger.error(f"❌ Ошибка get_user: {e}")
            return None
    
    async def is_user_banned(self, user_id):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                async with conn.execute('''
                    SELECT expires_at FROM banned_users 
                    WHERE user_id = ? AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                ''', (user_id,)) as cursor:
                    result = await cursor.fetchone()
                    return result is not None
        except Exception as e:
            logger.error(f"❌ Ошибка is_user_banned: {e}")
            return False
    
    async def is_premium_active(self, user_id):
        try:
            user = await self.get_user(user_id)
            if not user or not user['is_premium']:
                return False
            
            if user['premium_expires_at']:
                expires = datetime.fromisoformat(user['premium_expires_at'])
                if datetime.now() > expires:
                    await self.remove_premium(user_id)
                    return False
            
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка is_premium_active: {e}")
            return False
    
    async def ban_user(self, user_id, reason, duration_days=None):
        try:
            expires_at = None
            if duration_days:
                expires_at = (datetime.now() + timedelta(days=duration_days)).isoformat()
                
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute('''
                    INSERT OR REPLACE INTO banned_users (user_id, reason, expires_at)
                    VALUES (?, ?, ?)
                ''', (user_id, reason, expires_at))
                await conn.commit()
                logger.warning(f"🚫 Пользователь {user_id} банен: {reason}")
        except Exception as e:
            logger.error(f"❌ Ошибка ban_user: {e}")
    
    async def update_user(self, user_id, **kwargs):
        try:
            fields = ', '.join([f"{k} = ?" for k in kwargs.keys()])
            values = list(kwargs.values()) + [user_id]
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute(f'UPDATE users SET {fields} WHERE user_id = ?', values)
                await conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка update_user: {e}")
    
    async def give_premium(self, user_id, months):
        try:
            expires_at = (datetime.now() + timedelta(days=months * 30)).isoformat()
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute('''
                    UPDATE users SET is_premium = 1, premium_expires_at = ?
                    WHERE user_id = ?
                ''', (expires_at, user_id))
                await conn.commit()
                logger.info(f"✅ Премиум выдан {user_id} на {months} месяцев до {expires_at}")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка give_premium: {e}")
            return False
    
    async def remove_premium(self, user_id):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute('''
                    UPDATE users SET is_premium = 0, premium_expires_at = NULL
                    WHERE user_id = ?
                ''', (user_id,))
                await conn.commit()
                logger.info(f"✅ Премиум забран у {user_id}")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка remove_premium: {e}")
            return False
    
    async def delete_user_data(self, user_id):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
                await conn.execute('DELETE FROM votes WHERE voter_id = ? OR votee_id = ?', (user_id, user_id))
                await conn.execute('DELETE FROM reports WHERE reporter_id = ? OR reported_user_id = ?', (user_id, user_id))
                await conn.execute('DELETE FROM chats WHERE user1_id = ? OR user2_id = ?', (user_id, user_id))
                await conn.commit()
                logger.info(f"🗑️ Очищены все данные пользователя {user_id}")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка delete_user_data: {e}")
            return False
    
    async def create_chat(self, user1_id, user2_id, category):
        try:
            chat_id = str(uuid.uuid4())
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute('''
                    INSERT INTO chats (chat_id, user1_id, user2_id, category, status)
                    VALUES (?, ?, ?, ?, 'active')
                ''', (chat_id, user1_id, user2_id, category))
                await conn.commit()
                return chat_id
        except Exception as e:
            logger.error(f"❌ Ошибка create_chat: {e}")
            return None
    
    async def end_chat(self, chat_id):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute('''
                    UPDATE chats SET status = "ended", ended_at = CURRENT_TIMESTAMP
                    WHERE chat_id = ?
                ''', (chat_id,))
                await conn.commit()
                logger.info(f"✅ Чат {chat_id} завершён")
        except Exception as e:
            logger.error(f"❌ Ошибка end_chat: {e}")
    
    async def save_report(self, chat_id, reporter_id, reported_user_id, reason):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute('''
                    INSERT INTO reports (chat_id, reporter_id, reported_user_id, reason)
                    VALUES (?, ?, ?, ?)
                ''', (chat_id, reporter_id, reported_user_id, reason))
                await conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка save_report: {e}")
    
    async def save_vote(self, voter_id, votee_id, chat_id, vote_type):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute('''
                    INSERT INTO votes (voter_id, votee_id, chat_id, vote_type)
                    VALUES (?, ?, ?, ?)
                ''', (voter_id, votee_id, chat_id, vote_type))
                
                if vote_type == 'positive':
                    await conn.execute('UPDATE users SET positive_votes = positive_votes + 1 WHERE user_id = ?', (votee_id,))
                else:
                    await conn.execute('UPDATE users SET negative_votes = negative_votes + 1 WHERE user_id = ?', (votee_id,))
                
                async with conn.execute('SELECT positive_votes, negative_votes FROM users WHERE user_id = ?', (votee_id,)) as cursor:
                    result = await cursor.fetchone()
                    if result:
                        positive, negative = result
                        total = positive + negative
                        rating = (positive / total * 100) if total > 0 else 0
                        await conn.execute('UPDATE users SET rating = ? WHERE user_id = ?', (rating, votee_id))
                
                await conn.commit()
        except Exception as e:
            logger.error(f"❌ Ошибка save_vote: {e}")
    
    async def get_stats(self):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                async with conn.execute('SELECT COUNT(*) FROM users') as c:
                    total_users = (await c.fetchone())[0]
                
                async with conn.execute('SELECT COUNT(*) FROM users WHERE is_premium = 1') as c:
                    premium_users = (await c.fetchone())[0]
                
                async with conn.execute('SELECT COUNT(*) FROM banned_users WHERE expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP') as c:
                    banned_users = (await c.fetchone())[0]
                
                async with conn.execute('SELECT COUNT(*) FROM chats WHERE status = "active"') as c:
                    active_chats_count = (await c.fetchone())[0]
                
                async with conn.execute('SELECT COUNT(*) FROM chats') as c:
                    total_chats = (await c.fetchone())[0]
                
                return {
                    'total_users': total_users,
                    'premium_users': premium_users,
                    'banned_users': banned_users,
                    'active_chats': active_chats_count,
                    'total_chats': total_chats,
                    'total_messages': 0 # Legacy, table removed
                }
        except Exception as e:
            logger.error(f"❌ Ошибка get_stats: {e}")
            return None
    
    async def get_premium_users(self):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute('''
                    SELECT user_id, username, first_name, premium_expires_at
                    FROM users
                    WHERE is_premium = 1
                    ORDER BY premium_expires_at DESC
                ''') as cursor:
                    users = [dict(row) for row in await cursor.fetchall()]
                    return users
        except Exception as e:
            logger.error(f"❌ Ошибка get_premium_users: {e}")
            return []

    async def add_mandatory_channel(self, channel_id: str, url: str, name: str):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute('''
                    INSERT OR REPLACE INTO mandatory_channels (channel_id, url, name)
                    VALUES (?, ?, ?)
                ''', (channel_id, url, name))
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка add_mandatory_channel: {e}")
            return False

    async def remove_mandatory_channel(self, channel_id: str):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cursor = await conn.execute('DELETE FROM mandatory_channels WHERE channel_id = ?', (channel_id,))
                await conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ Ошибка remove_mandatory_channel: {e}")
            return False

    async def get_mandatory_channels(self):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                async with conn.execute('SELECT * FROM mandatory_channels') as cursor:
                    channels = [dict(row) for row in await cursor.fetchall()]
                    return channels
        except Exception as e:
            logger.error(f"❌ Ошибка get_mandatory_channels: {e}")
            return []

    async def get_all_users(self):
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                async with conn.execute('SELECT user_id FROM users') as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"❌ Ошибка get_all_users: {e}")
            return []

