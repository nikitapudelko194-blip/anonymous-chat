from datetime import datetime, timedelta
from bot.config import BAN_DURATION, MAX_REPORTS_FOR_BAN, AUTO_BAN_RESET
from bot.database.db import Database


async def check_and_apply_ban(user_id: int, db: Database) -> bool:
    """
    Проверить количество жалоб и применить бан если нужно.
    """
    user = await db.get_user(user_id)
    
    if not user:
        return False
    
    if user['reports_count'] >= MAX_REPORTS_FOR_BAN:
        # Бан на 7 дней
        ban_expires = datetime.now() + timedelta(seconds=BAN_DURATION)
        await db.ban_user(
            user_id,
            reason=f'Очень много жалоб: {user["reports_count"]}',
            expires_at=ban_expires
        )
        return True
    
    return False


async def auto_unban_expired(db: Database):
    """
    Автоматически разбанить пользователей по истечению времени.
    """
    expired_bans = await db.get_expired_bans()
    
    for ban_user in expired_bans:
        await db.unban_user(ban_user['user_id'])


async def is_user_banned(user_id: int, db: Database) -> bool:
    """
    Проверить, забанен ли пользователь.
    """
    # Также автоматически разбанить если время истекло
    await auto_unban_expired(db)
    
    user = await db.get_user(user_id)
    
    if not user:
        return False
    
    if not user['is_banned']:
        return False
    
    # Проверить время бана
    if user['ban_expires_at']:
        ban_expires = datetime.fromisoformat(user['ban_expires_at'])
        if datetime.now() > ban_expires:
            await db.unban_user(user_id)
            return False
    
    return True


async def get_ban_info(user_id: int, db: Database) -> dict:
    """
    Получить информацию о бане.
    """
    user = await db.get_user(user_id)
    
    if not user or not user['is_banned']:
        return {}
    
    return {
        'reason': user['ban_reason'],
        'expires_at': user['ban_expires_at'],
        'is_banned': True
    }
