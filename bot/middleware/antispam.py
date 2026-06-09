import time
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from collections import defaultdict
from typing import Callable, Dict, Any, Awaitable
import logging

logger = logging.getLogger(__name__)

class AntiSpamMiddleware(BaseMiddleware):
    def __init__(self, db, limit: int = 5, window_seconds: int = 2):
        self.db = db
        self.limit = limit
        self.window_seconds = window_seconds
        # Хранит список временных меток сообщений: {user_id: [t1, t2, ...]}
        self.users_history = defaultdict(list)
        # Штрафные очки за спам (больше 3 спам-волн = бан)
        self.spam_strikes = defaultdict(int)
        
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Проверяем только сообщения от пользователей
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)
            
        user_id = event.from_user.id
        current_time = time.time()
        
        # Очищаем старые записи
        self.users_history[user_id] = [
            t for t in self.users_history[user_id] 
            if current_time - t <= self.window_seconds
        ]
        
        self.users_history[user_id].append(current_time)
        
        if len(self.users_history[user_id]) > self.limit:
            self.spam_strikes[user_id] += 1
            
            # Если 1-3 страйка, просто игнорим сообщение и предупреждаем
            if self.spam_strikes[user_id] <= 3:
                try:
                    await event.answer("⚠️ Пожалуйста, не отправляйте сообщения так часто!")
                except:
                    pass
                return # Прерываем обработку
                
            # Если больше 3 страйков - выдаем бан на 1 день (или можно навсегда)
            if self.spam_strikes[user_id] == 4:
                try:
                    await event.answer("🚫 Вы заблокированы на 1 день за многочисленный спам.")
                except:
                    pass
                
                # Добавляем бан в БД через асинхронный метод
                await self.db.ban_user(user_id, "Многочисленный спам", duration_days=1)
                logger.warning(f"🚫 Пользователь {user_id} заблокирован системой анти-спама")
                return
            else:
                # Уже заблокирован, просто игнорируем
                return
                
        return await handler(event, data)
