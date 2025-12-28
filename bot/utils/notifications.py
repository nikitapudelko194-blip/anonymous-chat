from aiogram import Bot
from datetime import datetime
from bot.config import BOT_TOKEN


async def notify_match_found(
    bot: Bot,
    user1_id: int,
    user2_id: int,
    user1_profile: dict,
    user2_profile: dict
):
    """
    Уведомить обоих пользователей о найденном матче.
    """
    
    msg1 = f"""
🎉 Вы нашли собеседника!

👤 {user2_profile.get('first_name', 'Участник')}, {user2_profile.get('age', '?')} лет
📕 О себе: {user2_profile.get('bio', 'еще ничего не рассказал')}
❤️ Интересы: {user2_profile.get('interests', 'новых интересов осталось')}

💬 Можете начать писать сообщения!
⏭️ /skip - пропустить
📊 /report - жалоба
    """
    
    msg2 = f"""
🎉 Вы нашли собеседника!

👤 {user1_profile.get('first_name', 'Участник')}, {user1_profile.get('age', '?')} лет
📕 О себе: {user1_profile.get('bio', 'еще ничего не рассказал')}
❤️ Интересы: {user1_profile.get('interests', 'новых интересов осталось')}

💬 Можете начать писать сообщения!
⏭️ /skip - пропустить
📊 /report - жалоба
    """
    
    try:
        await bot.send_message(user1_id, msg1)
        await bot.send_message(user2_id, msg2)
    except Exception as e:
        print(f"Error sending notifications: {e}")


async def notify_ban(bot: Bot, user_id: int, reason: str, expires_at: str):
    """
    Уведомить пользователя о бане.
    """
    
    msg = f"""
🚫 Вы заблокированы

**Причина:** {reason}
**Она-блокировка:** {expires_at}

💳 Чтобы разблокироваться раньше, купите премиум подписку (/premium)
    """
    
    try:
        await bot.send_message(user_id, msg)
    except Exception as e:
        print(f"Error sending ban notification: {e}")


async def notify_report_received(bot: Bot, user_id: int):
    """
    Уведомить о полученной жалобе.
    """
    
    msg = f"""
✅ Нася жалоба получена

Спасибо за то, что помогаете нам скравнить всех
    """
    
    try:
        await bot.send_message(user_id, msg)
    except Exception as e:
        print(f"Error sending report notification: {e}")


async def notify_premium_purchased(bot: Bot, user_id: int, subscription_type: str, duration: str):
    """
    Уведомить о купленной подписке.
    """
    
    msg = f"""
💳 Благодарим за покупку!

✨ Подписка: {subscription_type}
📅 Валидна: {duration}

Новые возможности:
✨ Выбор пола собеседника
✨ Удаление рекламы
✨ Приоритет в поиске
    """
    
    try:
        await bot.send_message(user_id, msg)
    except Exception as e:
        print(f"Error sending premium notification: {e}")
