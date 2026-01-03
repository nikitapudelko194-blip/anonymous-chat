"""Этот файл содержит список всех обработчиков для регистрации в dispatcher"""

# Импортируйте этот файл в main.py и используйте в функции main():

# from bot.handlers import setup_handlers
# await setup_handlers(dp)

from aiogram import Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from bot.main import (
    cmd_start, cmd_search, cmd_next, cmd_stop, cmd_me,
    handle_chat_message, cmd_search_callback,
    UserStates
)

async def setup_handlers(dp: Dispatcher):
    """
    Регистрация всех обработчиков
    """
    
    # Команды
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_search, Command("search"))
    dp.message.register(cmd_next, Command("next"))
    dp.message.register(cmd_stop, Command("stop"))
    dp.message.register(cmd_me, Command("me"))
    
    # Сообщения в чате (все типы медиа)
    dp.message.register(
        handle_chat_message,
        StateFilter(UserStates.in_chat),
        F.text | F.photo | F.voice | F.sticker
    )
    
    # Callback для кнопки поиска
    dp.callback_query.register(cmd_search_callback, F.data == "search_start")
    
    # Дополнительные callback'и можно добавить сюда
    # dp.callback_query.register(handle_other_callback, F.data == "other")
