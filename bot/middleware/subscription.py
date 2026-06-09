from aiogram import BaseMiddleware, Bot
from aiogram.types import Message, CallbackQuery, TelegramObject, InlineKeyboardMarkup, InlineKeyboardButton
from typing import Callable, Dict, Any, Awaitable
import logging

logger = logging.getLogger(__name__)

class SubscriptionMiddleware(BaseMiddleware):
    def __init__(self, db, bot: Bot):
        self.db = db
        self.bot = bot
        
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        
        # Получаем пользователя из сообщения или коллбека
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id
            if event.text == "/start":
                # Разрешаем /start для проверки подписки
                pass
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            # Разрешаем коллбек "check_subscription" проходить без проверок
            if event.data == "check_subscription":
                return await handler(event, data)
        else:
            return await handler(event, data)
            
        if not user_id:
            return await handler(event, data)

        # Получаем обязательные каналы
        channels = await self.db.get_mandatory_channels()
        if not channels:
            return await handler(event, data)
            
        unsubscribed_channels = []
        
        for channel in channels:
            try:
                # Проверяем статус в канале
                member = await self.bot.get_chat_member(chat_id=channel['channel_id'], user_id=user_id)
                if member.status in ['left', 'kicked']:
                    unsubscribed_channels.append(channel)
            except Exception as e:
                # Если бот не администратор в канале или ID неверный, мы пропускаем канал (или можно логировать)
                logger.error(f"Не удалось проверить подписку для {channel['channel_id']}: {e}")
                # Если хотите строгую проверку - можно раскомментировать
                # unsubscribed_channels.append(channel)
                pass

        if unsubscribed_channels:
            keyboard = []
            for ch in unsubscribed_channels:
                keyboard.append([InlineKeyboardButton(text=ch['name'], url=ch['url'])])
                
            keyboard.append([InlineKeyboardButton(text="✅ Я подписался (Проверить)", callback_data="check_subscription")])
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            
            text = "👋 <b>Обязательная подписка!</b>\n\nЧтобы использовать бота, подпишитесь на наших спонсоров:"
            
            if isinstance(event, Message):
                await event.answer(text, reply_markup=reply_markup)
            elif isinstance(event, CallbackQuery):
                await event.answer("Подпишитесь на каналы!", show_alert=True)
                await event.message.answer(text, reply_markup=reply_markup)
            
            return # Прерываем обработку
            
        return await handler(event, data)
