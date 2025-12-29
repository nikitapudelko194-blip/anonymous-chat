import random
from typing import Optional
from database.db import Database

# Глобальная очередь ожидающих пользователей по категориям
waiting_queue = {
    'random': [],
    'gender_male': [],
    'gender_female': [],
    'gender_other': []
}

async def find_match(
    user_id: int,
    category: str,
    gender_filter: Optional[str] = None
) -> Optional[int]:
    """
    Поиск собеседника с системой очереди.
    
    Алгоритм:
    1️⃣ Если в очереди есть ожидающий → спариваем их
    2️⃣ Если очередь пуста → добавляем пользователя в очередь
    3️⃣ Когда следующий придет → найдет первого в очереди
    
    Args:
        user_id: ID пользователя
        category: 'random' или 'gender'
        gender_filter: Пол собеседника (для gender категории)
    
    Returns:
        ID найденного собеседника или None (если в очереди)
    """
    
    db = Database()
    user = await db.get_user(user_id)
    
    if not user:
        return None
    
    # Определить ключ очереди
    if category == 'random':
        queue_key = 'random'
    elif category == 'gender' and gender_filter:
        queue_key = f'gender_{gender_filter}'
    else:
        return None
    
    # 🔍 ПРОВЕРИТЬ: есть ли ожидающий в очереди?
    if waiting_queue[queue_key]:
        # ✅ СПАРИТЬ с первым в очереди (FIFO)
        partner_id = waiting_queue[queue_key].pop(0)
        print(f"✅ Спариены: {user_id} ↔️ {partner_id} (из очереди)")
        return partner_id
    
    # 📋 ОЧЕРЕДЬ ПУСТА → добавить текущего в очередь
    waiting_queue[queue_key].append(user_id)
    print(f"⏳ {user_id} добавлен в очередь {queue_key}. Ждет: {waiting_queue}")
    return None  # Ждем партнера

async def remove_from_queue(user_id: int, category: str, gender_filter: Optional[str] = None):
    """Удалить пользователя из очереди (если отменил поиск)."""
    
    if category == 'random':
        queue_key = 'random'
    elif category == 'gender' and gender_filter:
        queue_key = f'gender_{gender_filter}'
    else:
        return
    
    if user_id in waiting_queue[queue_key]:
        waiting_queue[queue_key].remove(user_id)
        print(f"❌ {user_id} удален из очереди {queue_key}")

def get_queue_size(category: str, gender_filter: Optional[str] = None) -> int:
    """Получить количество ожидающих в очереди."""
    
    if category == 'random':
        return len(waiting_queue['random'])
    elif category == 'gender' and gender_filter:
        return len(waiting_queue[f'gender_{gender_filter}'])
    
    return 0
