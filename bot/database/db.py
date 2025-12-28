import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from config import DB_PATH, BAN_DURATION, MAX_REPORTS_FOR_BAN


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
    
    def get_connection(self):
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    async def init_db(self):
        """Initialize database with all required tables."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                gender TEXT,
                age INTEGER,
                interests TEXT,
                bio TEXT,
                is_premium BOOLEAN DEFAULT 0,
                premium_expires_at DATETIME,
                chats_count INTEGER DEFAULT 0,
                skips_count INTEGER DEFAULT 0,
                violations_count INTEGER DEFAULT 0,
                reports_count INTEGER DEFAULT 0,
                is_banned BOOLEAN DEFAULT 0,
                ban_reason TEXT,
                ban_expires_at DATETIME,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица чатов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT UNIQUE NOT NULL,
                user1_id INTEGER NOT NULL,
                user2_id INTEGER NOT NULL,
                category TEXT,
                status TEXT DEFAULT 'active',
                reports_count INTEGER DEFAULT 0,
                report_reasons TEXT,
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
                receiver_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                message_type TEXT DEFAULT 'text',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(chat_id)
            )
        ''')
        
        # Таблица подписок
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                subscription_type TEXT,
                purchase_amount REAL,
                payment_method TEXT,
                purchased_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # Таблица банов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bans_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ban_type TEXT,
                reason TEXT,
                reports_count INTEGER,
                ban_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
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
                description TEXT,
                status TEXT DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(chat_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    # ===== USER METHODS =====
    
    async def create_user(self, user_id: int, username: str = None, first_name: str = None, 
                         last_name: str = None) -> bool:
        """Create new user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    async def update_user(self, user_id: int, **kwargs) -> bool:
        """Update user data."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Build UPDATE query dynamically
        set_clause = ', '.join([f'{key} = ?' for key in kwargs.keys()])
        values = list(kwargs.values()) + [user_id]
        
        query = f'UPDATE users SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?'
        
        try:
            cursor.execute(query, values)
            conn.commit()
            return True
        finally:
            conn.close()
    
    async def get_all_active_users(self, exclude_id: int = None) -> List[Dict]:
        """Get all active users, optionally excluding one user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if exclude_id:
            cursor.execute('''
                SELECT * FROM users 
                WHERE is_active = 1 AND is_banned = 0 AND user_id != ?
            ''', (exclude_id,))
        else:
            cursor.execute('''
                SELECT * FROM users 
                WHERE is_active = 1 AND is_banned = 0
            ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # ===== CHAT METHODS =====
    
    async def create_chat(self, user1_id: int, user2_id: int, category: str) -> str:
        """Create new chat between two users."""
        chat_id = f"{user1_id}_{user2_id}"
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO chats (chat_id, user1_id, user2_id, category)
                VALUES (?, ?, ?, ?)
            ''', (chat_id, user1_id, user2_id, category))
            conn.commit()
            return chat_id
        finally:
            conn.close()
    
    async def get_chat(self, chat_id: str) -> Optional[Dict]:
        """Get chat by ID."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM chats WHERE chat_id = ?', (chat_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    async def end_chat(self, chat_id: str) -> bool:
        """End chat session."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE chats 
                SET status = 'ended', ended_at = CURRENT_TIMESTAMP 
                WHERE chat_id = ?
            ''', (chat_id,))
            conn.commit()
            return True
        finally:
            conn.close()
    
    # ===== MESSAGE METHODS =====
    
    async def save_message(self, chat_id: str, sender_id: int, receiver_id: int, 
                          content: str, message_type: str = 'text') -> bool:
        """Save message to database."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO messages (chat_id, sender_id, receiver_id, content, message_type)
                VALUES (?, ?, ?, ?, ?)
            ''', (chat_id, sender_id, receiver_id, content, message_type))
            conn.commit()
            return True
        finally:
            conn.close()
    
    async def get_messages(self, chat_id: str, limit: int = 50) -> List[Dict]:
        """Get messages from chat."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?
        ''', (chat_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # ===== SUBSCRIPTION METHODS =====
    
    async def create_subscription(self, user_id: int, subscription_type: str, 
                                 amount: float, payment_method: str = 'telegram_stars') -> bool:
        """Create subscription for user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Calculate expiration date
        if subscription_type == 'monthly':
            expires_at = datetime.now() + timedelta(days=30)
        elif subscription_type == 'lifetime':
            expires_at = datetime.now() + timedelta(days=365*100)  # Практически навсегда
        else:
            return False
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO subscriptions 
                (user_id, subscription_type, purchase_amount, payment_method, expires_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, subscription_type, amount, payment_method, expires_at))
            
            # Обновить статус премиум в пользователе
            cursor.execute('''
                UPDATE users 
                SET is_premium = 1, premium_expires_at = ?, is_banned = 0
                WHERE user_id = ?
            ''', (expires_at, user_id))
            
            conn.commit()
            return True
        finally:
            conn.close()
    
    async def get_subscription(self, user_id: int) -> Optional[Dict]:
        """Get subscription for user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM subscriptions WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    async def check_premium_expired(self, user_id: int) -> bool:
        """Check if premium has expired."""
        sub = await self.get_subscription(user_id)
        
        if not sub or not sub['expires_at']:
            return True
        
        expires = datetime.fromisoformat(sub['expires_at'])
        if datetime.now() > expires:
            # Обновить статус пользователя
            await self.update_user(user_id, is_premium=False)
            return True
        
        return False
    
    # ===== BAN METHODS =====
    
    async def ban_user(self, user_id: int, reason: str, expires_at: datetime = None) -> bool:
        """Ban user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE users 
                SET is_banned = 1, ban_reason = ?, ban_expires_at = ?
                WHERE user_id = ?
            ''', (reason, expires_at, user_id))
            
            # Log ban
            cursor.execute('''
                INSERT INTO bans_log (user_id, ban_type, reason, ban_date, expires_at)
                VALUES (?, 'report_based', ?, CURRENT_TIMESTAMP, ?)
            ''', (user_id, reason, expires_at))
            
            conn.commit()
            return True
        finally:
            conn.close()
    
    async def unban_user(self, user_id: int) -> bool:
        """Unban user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE users 
                SET is_banned = 0, ban_reason = NULL, ban_expires_at = NULL
                WHERE user_id = ?
            ''', (user_id,))
            conn.commit()
            return True
        finally:
            conn.close()
    
    async def get_expired_bans(self) -> List[Dict]:
        """Get users with expired bans."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM users 
            WHERE is_banned = 1 AND ban_expires_at IS NOT NULL 
            AND ban_expires_at < CURRENT_TIMESTAMP
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # ===== REPORT METHODS =====
    
    async def create_report(self, chat_id: str, reporter_id: int, reported_user_id: int,
                           reason: str, description: str = None) -> bool:
        """Create report against user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO reports (chat_id, reporter_id, reported_user_id, reason, description)
                VALUES (?, ?, ?, ?, ?)
            ''', (chat_id, reporter_id, reported_user_id, reason, description))
            conn.commit()
            return True
        finally:
            conn.close()
    
    async def increment_reports(self, user_id: int) -> int:
        """Increment report count for user and return new count."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE users 
                SET reports_count = reports_count + 1
                WHERE user_id = ?
            ''', (user_id,))
            
            cursor.execute('SELECT reports_count FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            conn.commit()
            
            return row['reports_count'] if row else 0
        finally:
            conn.close()
    
    async def get_reports(self, user_id: int) -> List[Dict]:
        """Get all reports against user."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM reports WHERE reported_user_id = ? ORDER BY created_at DESC
        ''', (user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    # ===== STATS METHODS =====
    
    async def increment_chats_count(self, user_id: int) -> bool:
        """Increment user chats count."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE users SET chats_count = chats_count + 1 WHERE user_id = ?
            ''', (user_id,))
            conn.commit()
            return True
        finally:
            conn.close()
    
    async def increment_skips_count(self, user_id: int) -> bool:
        """Increment user skips count."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE users SET skips_count = skips_count + 1 WHERE user_id = ?
            ''', (user_id,))
            conn.commit()
            return True
        finally:
            conn.close()
