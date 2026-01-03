from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..states.user_states import UserStates
from ..keyboards.main import main_menu_kb
from ..database.db import Database

router = Router()
db = Database()

@router.message(Command('start'))
async def start(
    message: types.Message,
    state: FSMContext
):
    """Начать работу бота."""
    
    # Проверить, регистрация самым минимальная
    user = await db.get_user(message.from_user.id)
    
    if not user:
        # Новый пользователь - выбрать пол
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👨 Мужчина", callback_data="gender_male")],
            [InlineKeyboardButton(text="👩 Женщина", callback_data="gender_female")],
            [InlineKeyboardButton(text="🙀 Не скажу", callback_data="gender_other")],
        ])
        
        await message.answer(
            "🐐 <b>Выберите ваш пол:</b>",
            reply_markup=kb,
            parse_mode="HTML"
        )
        
        await state.set_state(UserStates.waiting_gender)
        return
    
    # Приветствие вернулся пользователю
    await message.answer(
        "🎉 <b>Anonymous Chat</b>\n\nПривет! Конфиденциальные беседы на любые темы.",
        reply_markup=main_menu_kb(),
        parse_mode="HTML"
    )
    
    await state.set_state(UserStates.main_menu)

@router.callback_query(lambda c: c.data.startswith('gender_'))
async def select_gender(
    callback: types.CallbackQuery,
    state: FSMContext
):
    """Ответ на выбор пола."""
    
    gender = callback.data.split('_')[1]
    
    # Сохранить пользователя на этом этапе
    await db.create_user(
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        gender=gender
    )
    
    await callback.answer()
    
    # теперь попросить возраст
    await callback.message.edit_text(
        "🎉 <b>Насколько вам лет?</b>",
        parse_mode="HTML"
    )
    
    await state.set_state(UserStates.waiting_age)

@router.message(UserStates.waiting_age)
async def set_age(
    message: types.Message,
    state: FSMContext
):
    """Окончить регистрацию."""
    
    try:
        age = int(message.text)
        if age < 13 or age > 120:
            await message.answer("😜 Извините, возраст должен быть не свыше 120 и не ниже 13")
            return
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число")
        return
    
    # Обновить возраст
    await db.update_user_age(message.from_user.id, age)
    
    await message.answer(
        "🎉 <b>Anonymous Chat</b>\n\nПривет! Конфиденциальные беседы на любые темы.",
        reply_markup=main_menu_kb(),
        parse_mode="HTML"
    )
    
    await state.set_state(UserStates.main_menu)
