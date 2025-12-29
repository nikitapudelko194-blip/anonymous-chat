from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
)

# МЕНЮ (Поовветствующие кнопки)
def main_menu_kb():
    """AnonRuBot style main menu."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Найти собеседника", callback_data="start_search")],
        [InlineKeyboardButton(text="💎 Премиум (тест)", callback_data="buy_premium")],
        [InlineKeyboardButton(text="⚖️ Правила", callback_data="rules")],
    ])

def search_category_kb():
    """Choose search category (2 only like AnonRuBot)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Случайный", callback_data="category_random")],
        [InlineKeyboardButton(text="👥 По полу (💎 premium)", callback_data="category_gender")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")],
    ])

def searching_kb():
    """Searching... menu."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить поиск", callback_data="cancel_search")],
    ])

def chat_menu_kb():
    """Chat menu with commands (AnonRuBot style)."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/stop ❌ Завершить")],
            [KeyboardButton(text="/new ➡️ Новый чат")],
            [KeyboardButton(text="/report 💥 Жалоба")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def chat_actions_kb():
    """Chat actions (inline)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💥 Жалоба", callback_data="report_user")],
        [InlineKeyboardButton(text="❌ Завершить чат", callback_data="stop_chat")],
    ])

def report_reason_kb():
    """Report reasons (like AnonRuBot)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Спам", callback_data="report_spam")],
        [InlineKeyboardButton(text="😤 Оскорбление", callback_data="report_abuse")],
        [InlineKeyboardButton(text="🔞 Неприличный", callback_data="report_inappropriate")],
        [InlineKeyboardButton(text="😠 Домогательство", callback_data="report_harassment")],
        [InlineKeyboardButton(text="❌ Другое", callback_data="report_other")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")],
    ])

def gender_filter_kb():
    """Gender filter for premium."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨 Мужины", callback_data="gender_filter_male")],
        [InlineKeyboardButton(text="👩 Женщины", callback_data="gender_filter_female")],
        [InlineKeyboardButton(text="🙀 Все", callback_data="gender_filter_all")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="search_category")],
    ])
