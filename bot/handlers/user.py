from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import sqlite3
import logging

from bot.keyboards.inline import (
    get_main_menu, get_gender_registration_keyboard, get_interests_keyboard,
    get_premium_keyboard, get_search_menu
)

router = Router()
logger = logging.getLogger(__name__)

class UserStates(StatesGroup):
    waiting_gender = State()
    waiting_age = State()
    waiting_search_gender = State()
    in_chat = State()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, db):
    user_id = message.from_user.id
    if await db.is_user_banned(user_id):
        await message.answer("❌ <b>Вы заблокированы в этом боте</b>")
        return
    
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, message.from_user.username, message.from_user.first_name)
        await message.answer(
            "👋 <b>Привет! Добро пожаловать!</b>\n\n👨‍👩 <b>Сначала укажите ваш пол:</b>",
            reply_markup=get_gender_registration_keyboard()
        )
        await state.set_state(UserStates.waiting_gender)
    else:
        await message.answer(
            "👋 <b>Привет! Добро пожаловать обратно!</b>",
            reply_markup=get_main_menu()
        )
        await state.clear()

@router.callback_query(F.data.startswith("register_gender_"))
async def register_gender_callback(callback: CallbackQuery, state: FSMContext, db):
    user_id = callback.from_user.id
    gender_map = {
        "register_gender_male": "👨 Парень",
        "register_gender_female": "👩 Девушка",
    }
    gender_text = gender_map.get(callback.data)
    if not gender_text: return
    
    await db.update_user(user_id, gender=gender_text)
    await callback.answer()
    await callback.message.edit_text(
        f"✅ <b>Спасибо!</b>\n\nВы выбрали: {gender_text}\n\n🎂 <b>Теперь укажите ваш возраст:</b>\n\n⚠️ <b>Минимальный возраст: 18 лет</b>"
    )
    await state.set_state(UserStates.waiting_age)

@router.message(UserStates.waiting_age)
async def handle_age_input(message: Message, state: FSMContext, db):
    user_id = message.from_user.id
    try:
        age = int(message.text)
    except ValueError:
        await message.answer("❌ <b>Пожалуйста, введите число.</b>")
        return
    
    if age < 18:
        await message.answer("❌ <b>Минимальный возраст 18 лет.</b>")
        await state.clear()
        return
        
    await db.update_user(user_id, age=age)
    await message.answer("✅ <b>Регистрация завершена!</b>", reply_markup=get_main_menu())
    await state.clear()

@router.message(Command("rules"))
async def cmd_rules(message: Message):
    rules_text = "👋 <b>Добро пожаловать в анонимный чат!</b>\nНе проси личные данные, не спамь и не оскорбляй. Удачи!"
    await message.answer(rules_text)

@router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = "❓ <b>ПОМОЩЬ</b>\n/search - поиск\n/next - следующий\n/stop - завершить"
    await message.answer(help_text)

@router.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("❓ <b>ПОМОЩЬ</b>\n/search - поиск\n/next - следующий\n/stop - завершить", reply_markup=get_main_menu())

@router.callback_query(F.data == "rules")
async def rules_callback(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("👋 <b>Правила:</b> Не проси личные данные, не спамь и не оскорбляй.", reply_markup=get_main_menu())

@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery, db):
    await callback.answer("Проверка подписки...")
    await callback.message.delete()
    await callback.message.answer("👋 <b>Главное меню</b>", reply_markup=get_main_menu())

@router.message(Command("delete_my_data"))
async def cmd_delete_my_data(message: Message, db):
    success = await db.delete_user_data(message.from_user.id)
    if success:
        await message.answer("🗑️ <b>Успех!</b>\n\nВсе ваши данные удалены.")
    else:
        await message.answer("❌ Ошибка при удалении данных")

@router.callback_query(F.data == "choose_interests")
async def choose_interests_callback(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("📖 <b>Выберите категорию интересов:</b>", reply_markup=get_interests_keyboard())

@router.callback_query(F.data.startswith("interest_"))
async def interest_select_callback(callback: CallbackQuery, db):
    interest_map = {"interest_general": "💬 Общение", "interest_lgbt": "🏳️‍🌈 LGBT"}
    interest_text = interest_map.get(callback.data)
    if interest_text:
        await db.update_user(callback.from_user.id, interests=interest_text)
        await callback.answer()
        await callback.message.edit_text(f"✅ <b>Интересы сохранены:</b> {interest_text}", reply_markup=get_main_menu())

@router.callback_query(F.data == "premium")
async def premium_callback(callback: CallbackQuery, db):
    if await db.is_premium_active(callback.from_user.id):
        await callback.answer("🎉 У вас уже есть ПРЕМИУМ!", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text("💳 <b>ПЛАНЫ ПРЕМИУМА</b>\n• 1 МЕСЯЦ - 99₽\n• ПОЖИЗНЕННО - 499₽", reply_markup=get_premium_keyboard())

@router.message(Command("pay"))
async def cmd_pay(message: Message):
    await message.answer("💳 <b>ПРЕМИУМ И ПОИСК ПО ПОЛУ</b>", reply_markup=get_premium_keyboard())

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("👋 <b>Главное меню</b>", reply_markup=get_main_menu())
