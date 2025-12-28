from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from bot.config import GENDERS, INTERESTS, REPORT_REASONS, CATEGORIES


def get_main_menu() -> InlineKeyboardMarkup:
    """
    Основное меню.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Поиск собеседника", callback_data="search_start")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile_view")],
        [InlineKeyboardButton(text="💳 Премиум", callback_data="premium_info")],
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="stats_view")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help_info")],
    ])


def get_gender_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура выбора пола.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=gender[0], callback_data=f"gender_{gender[1]}") for gender in GENDERS]
    ])


def get_interests_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура выбора интересов.
    """
    keyboard = []
    for i, interest in enumerate(INTERESTS):
        keyboard.append(InlineKeyboardButton(text=interest, callback_data=f"interest_{i}"))
        if (i + 1) % 2 == 0:
            keyboard.append("\n")
    
    buttons = []
    for btn in keyboard:
        if btn != "\n":
            buttons.append(btn)
        else:
            continue
    
    # Group by 2
    grouped = []
    for i in range(0, len(buttons), 2):
        grouped.append(buttons[i:i+2])
    
    return InlineKeyboardMarkup(inline_keyboard=grouped + [
        [InlineKeyboardButton(text="✅ ОК", callback_data="interests_done")]
    ])


def get_search_category_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура выбора категории поиска.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=category[0], callback_data=f"category_{category[1]}")] for category in CATEGORIES
    ])


def get_chat_menu() -> InlineKeyboardMarkup:
    """
    Меню в чате.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="chat_skip")],
        [InlineKeyboardButton(text="📊 Жалоба", callback_data="chat_report")],
    ])


def get_report_reasons_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура выбора причины жалобы.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=reason[0], callback_data=f"report_{reason[1]}")] for reason in REPORT_REASONS
    ])


def get_premium_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура выбора плана подписки.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Месячная", callback_data="premium_monthly")],
        [InlineKeyboardButton(text="♾️ Пожизненная", callback_data="premium_lifetime")],
        [InlineKeyboardButton(text="←️ Назад", callback_data="main_menu")],
    ])


def get_confirm_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data="confirm_yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="confirm_no")],
    ])


def get_back_button() -> InlineKeyboardMarkup:
    """
    Кнопка назад.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="←️ Назад", callback_data="main_menu")],
    ])
