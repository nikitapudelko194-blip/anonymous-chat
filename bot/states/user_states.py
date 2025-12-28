from aiogram.fsm.state import State, StatesGroup


class UserStates(StatesGroup):
    # Регистрация
    waiting_gender = State()
    waiting_age = State()
    waiting_interests = State()
    waiting_bio = State()
    
    # Поиск собеседника
    choosing_category = State()
    choosing_gender_filter = State()
    searching = State()
    
    # Чат
    in_chat = State()
    waiting_skip_confirm = State()
    
    # Жалоба
    reporting = State()
    report_reason = State()
    report_description = State()
    
    # Редактирование профиля
    editing_profile = State()
    editing_age = State()
    editing_interests = State()
    editing_bio = State()
