from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨 Парень", callback_data="search_gender_male")],
        [InlineKeyboardButton(text="👩 Девушка", callback_data="search_gender_female")],
        [InlineKeyboardButton(text="🔄 Любой пол", callback_data="search_gender_any")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")],
    ])

def get_gender_registration_keyboard():
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

def get_cancel_search_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить поиск", callback_data="cancel_search")],
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

def get_admin_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Управление пользователями", callback_data="admin_users_menu")],
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔗 Обязательная подписка", callback_data="admin_subs_menu")],
    ])

def get_admin_users_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Инфо о пользователе", callback_data="admin_user_info")],
        [InlineKeyboardButton(text="🚫 Забанить / Разбанить", callback_data="admin_user_ban")],
        [InlineKeyboardButton(text="💳 Выдать / Забрать Premium", callback_data="admin_user_premium")],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin_main_menu")],
    ])

def get_admin_subs_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список каналов", callback_data="admin_subs_list")],
        [InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin_subs_add")],
        [InlineKeyboardButton(text="➖ Удалить канал", callback_data="admin_subs_del")],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin_main_menu")],
    ])

def get_admin_cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel_action")],
    ])
