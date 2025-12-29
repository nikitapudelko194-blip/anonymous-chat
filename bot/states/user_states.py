from aiogram.fsm.state import State, StatesGroup

class UserStates(StatesGroup):
    # Регистрация (минимальная)
    waiting_gender = State()
    waiting_age = State()
    
    # Главное меню
    main_menu = State()
    
    # Поиск собеседника
    choosing_category = State()
    searching = State()
    
    # Чат
    in_chat = State()
    chat_menu = State()
    
    # Жалоба
    report_reason = State()
