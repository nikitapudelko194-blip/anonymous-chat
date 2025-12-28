import random
from typing import Optional
from bot.database.db import Database
from bot.config import MAX_REPORTS_FOR_BAN


async def find_match(
    user_id: int,
    category: str,
    gender_filter: Optional[str] = None
) -> Optional[int]:
    """
    Поиск собеседника по категории.
    
    Args:
        user_id: ID пользователя
        category: 'random', 'gender', 'interests', 'age'
        gender_filter: Предпочитаемый пол (для премиум)
    
    Returns:
        ID найденного собеседника или None
    """
    db = Database()
    
    # Получить профиль текущего пользователя
    user_profile = await db.get_user(user_id)
    
    if not user_profile:
        return None
    
    # Получить всех активных пользователей
    all_users = await db.get_all_active_users(exclude_id=user_id)
    
    if not all_users:
        return None
    
    # Фильтрация по категориям
    candidates = all_users
    
    if category == 'random':
        # Полностью случайный выбор
        candidate = random.choice(candidates)
        return candidate['user_id']
    
    elif category == 'gender':
        # Фильтр по полу (платная функция)
        if gender_filter:
            candidates = [
                u for u in candidates 
                if u['gender'] == gender_filter
            ]
    
    elif category == 'interests':
        # Поиск по общим интересам
        if user_profile['interests']:
            user_interests = set(user_profile['interests'].split(','))
            candidates = [
                u for u in candidates
                if u['interests'] and bool(user_interests & set(u['interests'].split(',')))
            ]
    
    elif category == 'age':
        # Поиск пользователей близкого возраста (±5 лет)
        if user_profile['age']:
            min_age = user_profile['age'] - 5
            max_age = user_profile['age'] + 5
            candidates = [
                u for u in candidates
                if u['age'] and min_age <= u['age'] <= max_age
            ]
    
    if not candidates:
        return None
    
    return random.choice(candidates)['user_id']
