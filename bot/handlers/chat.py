from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from bot.keyboards.inline import get_chat_actions_keyboard, get_vote_keyboard, get_cancel_search_keyboard
import asyncio
import logging

router = Router()
logger = logging.getLogger(__name__)

waiting_users = {"random": [], "gender_filter": [], "💬 Общение": [], "🏳️‍🌈 LGBT": []}
active_chats = {}
user_fsm_contexts = {}
partner_search_lock = asyncio.Lock()

async def find_partner(user_id: int, category: str, search_filters: dict, bot: Bot, state: FSMContext, db):
    global waiting_users, active_chats, user_fsm_contexts
    
    async with partner_search_lock:
        user = await db.get_user(user_id)
        user_interests = user.get('interests', '') if user else ''
        
        # Убираем из всех очередей
        for cat in waiting_users:
            if user_id in waiting_users[cat]:
                waiting_users[cat].remove(user_id)
        
        # Если категория пустая или нет в словаре
        if category not in waiting_users:
            waiting_users[category] = []

        if waiting_users[category]:
            partner_id = waiting_users[category].pop(0)
            partner = await db.get_user(partner_id)
            
            if search_filters.get('gender') and search_filters['gender'] != 'any':
                partner_gender = partner.get('gender') if partner else None
                if partner_gender != search_filters['gender']:
                    waiting_users[category].append(partner_id)
                    waiting_users[category].append(user_id)
                    return None, None
            
            partner_interests = partner.get('interests', '') if partner else ''
            if user_interests and partner_interests and user_interests != partner_interests:
                waiting_users[category].append(partner_id)
                waiting_users[category].append(user_id)
                return None, None
            
            chat_id = await db.create_chat(user_id, partner_id, category)
            active_chats[user_id] = {'partner_id': partner_id, 'chat_id': chat_id}
            active_chats[partner_id] = {'partner_id': user_id, 'chat_id': chat_id}
            
            if partner_id in user_fsm_contexts:
                partner_state = user_fsm_contexts[partner_id]
                from bot.handlers.user import UserStates
                await partner_state.set_state(UserStates.in_chat)
                await partner_state.update_data(chat_id=chat_id, partner_id=user_id, category=category)
                
                try:
                    await bot.send_message(
                        partner_id,
                        "🌟 <b>Новый собеседник найден!</b>\n\n🏳️ Диалог начат. Напишите /next чтобы перейти к следующему собеседнику",
                        reply_markup=get_chat_actions_keyboard()
                    )
                except: pass
            return partner_id, chat_id
        else:
            waiting_users[category].append(user_id)
            return None, None

@router.callback_query(F.data == "search_start")
async def search_start_callback(callback: CallbackQuery, state: FSMContext, db):
    user_id = callback.from_user.id
    if await db.is_user_banned(user_id):
        await callback.answer("❌ Вы заблокированы в этом боте", show_alert=True)
        return
    user_fsm_contexts[user_id] = state
    if user_id in active_chats:
        await callback.answer("⚠️ Вы уже в диалоге! Используйте /next или /stop")
        return
    
    from bot.keyboards.inline import get_search_menu
    await callback.answer()
    await callback.message.edit_text("🔍 <b>Выберите тип поиска:</b>", reply_markup=get_search_menu())

@router.callback_query(F.data == "search_random")
async def search_random_callback(callback: CallbackQuery, state: FSMContext, bot: Bot, db):
    user_id = callback.from_user.id
    await callback.answer()
    await callback.message.edit_text("🔍 <b>Поиск собеседника...</b>")
    
    partner_id, chat_id = await find_partner(user_id, 'random', {}, bot, state, db)
    from bot.handlers.user import UserStates
    if partner_id:
        await state.set_state(UserStates.in_chat)
        await state.update_data(chat_id=chat_id, partner_id=partner_id, category='random')
        await callback.message.edit_text("🌟 <b>Новый собеседник!</b>\n\n💬 Диалог начат. Напишите /next чтобы перейти к следующему собеседнику", reply_markup=get_chat_actions_keyboard())
    else:
        await callback.message.edit_text("⏳ <b>Ожидание собеседника...</b>\n\n🔍 Мы ищем нового собеседника для вас", reply_markup=get_cancel_search_keyboard())
        await state.set_state(UserStates.in_chat)
        await state.update_data(chat_id=None, partner_id=None, category='random', waiting=True)

@router.callback_query(F.data == "search_gender_check")
async def search_gender_check_callback(callback: CallbackQuery, state: FSMContext, db):
    user_id = callback.from_user.id
    if not await db.is_premium_active(user_id):
        await callback.answer("💳 ПОИСК ПО ПОЛУ Доступен только для ПРЕМИУМ!", show_alert=True)
        return
    from bot.keyboards.inline import get_gender_keyboard
    from bot.handlers.user import UserStates
    await callback.answer()
    await callback.message.edit_text("👨‍👩 <b>Выберите кого вы хотите найти:</b>", reply_markup=get_gender_keyboard())
    await state.set_state(UserStates.waiting_search_gender)

@router.callback_query(F.data.startswith("search_gender_"))
async def search_gender_callback(callback: CallbackQuery, state: FSMContext, bot: Bot, db):
    user_id = callback.from_user.id
    gender_map = {"search_gender_male": "👨 Парень", "search_gender_female": "👩 Девушка", "search_gender_any": "any"}
    gender = gender_map.get(callback.data)
    if not gender: return
    
    await callback.answer()
    await callback.message.edit_text("🔍 <b>Поиск собеседника...</b>")
    partner_id, chat_id = await find_partner(user_id, 'gender_filter', {'gender': gender}, bot, state, db)
    from bot.handlers.user import UserStates
    
    if partner_id:
        await state.set_state(UserStates.in_chat)
        await state.update_data(chat_id=chat_id, partner_id=partner_id, category='gender_filter', search_gender=gender)
        await callback.message.edit_text("🌟 <b>Новый собеседник найден!</b>\n\n💬 Диалог начат. Напишите /next чтобы перейти к следующему собеседнику", reply_markup=get_chat_actions_keyboard())
    else:
        await callback.message.edit_text("⏳ <b>Ожидание собеседника...</b>\n\n🔍 Мы ищем нового собеседника для вас с фильтром по полу", reply_markup=get_cancel_search_keyboard())
        await state.set_state(UserStates.in_chat)
        await state.update_data(chat_id=None, partner_id=None, category='gender_filter', waiting=True, search_gender=gender)

@router.callback_query(F.data == "next_partner")
async def next_partner_callback(callback: CallbackQuery, state: FSMContext, db, bot: Bot):
    await callback.answer()
    await _handle_next_partner(callback.from_user.id, callback.message, state, db, bot)

async def _handle_next_partner(user_id, message_or_callback, state: FSMContext, db, bot: Bot):
    data = await state.get_data()
    chat_id = data.get('chat_id')
    partner_id = data.get('partner_id')
    category = data.get('category', 'random')
    search_gender = data.get('search_gender')
    
    await callback.answer()
    
    if chat_id and partner_id:
        await db.end_chat(chat_id)
        active_chats.pop(user_id, None)
        active_chats.pop(partner_id, None)
        
        for cat in waiting_users:
            if user_id in waiting_users[cat]: waiting_users[cat].remove(user_id)
            if partner_id in waiting_users[cat]: waiting_users[cat].remove(partner_id)
        
        voting_message = "📋 <b>Оцените собеседника</b>\n\n👍 Нравится или Не нравится? Ваша оценка важна!"
        try:
            await bot.send_message(user_id, voting_message, reply_markup=get_vote_keyboard(chat_id, partner_id))
            await bot.send_message(partner_id, voting_message, reply_markup=get_vote_keyboard(chat_id, user_id))
        except: pass
        
    await state.clear()
    
    # Запускаем новый поиск в зависимости от предыдущей категории
    if category == 'gender_filter' and search_gender:
        from bot.handlers.user import UserStates
        await state.set_state(UserStates.waiting_search_gender)
        # Имитируем коллбэк для поиска
        class FakeCallback:
            def __init__(self, from_user, data):
                self.from_user = from_user
                self.data = data
                self.message = message_or_callback
            async def answer(self): pass
        fake_cb = FakeCallback(message_or_callback.from_user if hasattr(message_or_callback, 'from_user') else type('User', (), {'id': user_id})(), f"search_gender_{search_gender}")
        await search_gender_callback(fake_cb, state, bot, db)
    else:
        # Имитируем коллбэк для рандомного поиска
        class FakeCallback:
            def __init__(self, from_user):
                self.from_user = from_user
                self.message = message_or_callback
            async def answer(self): pass
        fake_cb = FakeCallback(message_or_callback.from_user if hasattr(message_or_callback, 'from_user') else type('User', (), {'id': user_id})())
        await search_random_callback(fake_cb, state, bot, db)

@router.callback_query(F.data == "end_chat")
async def end_chat_callback(callback: CallbackQuery, state: FSMContext, db, bot: Bot):
    await callback.answer()
    await _handle_end_chat(callback.from_user.id, callback.message, state, db, bot)

async def _handle_end_chat(user_id, message_or_callback, state: FSMContext, db, bot: Bot):
    data = await state.get_data()
    chat_id = data.get('chat_id')
    partner_id = data.get('partner_id')
    
    if chat_id and partner_id:
        await db.end_chat(chat_id)
        active_chats.pop(user_id, None)
        active_chats.pop(partner_id, None)
        
        for cat in waiting_users:
            if user_id in waiting_users[cat]: waiting_users[cat].remove(user_id)
            if partner_id in waiting_users[cat]: waiting_users[cat].remove(partner_id)
            
        voting_message = "📋 <b>Оцените собеседника</b>\n\n👍 Нравится или Не нравится? Ваша оценка важна!"
        try:
            await bot.send_message(partner_id, voting_message, reply_markup=get_vote_keyboard(chat_id, user_id))
        except: pass
        if hasattr(message_or_callback, 'edit_text'):
            await message_or_callback.edit_text(voting_message, reply_markup=get_vote_keyboard(chat_id, partner_id))
        else:
            await message_or_callback.answer(voting_message, reply_markup=get_vote_keyboard(chat_id, partner_id))
    else:
        # Удаляем из ожидания
        for cat in waiting_users:
            if user_id in waiting_users[cat]: waiting_users[cat].remove(user_id)
        from bot.keyboards.inline import get_main_menu
        msg = "👋 <b>Поиск отменен. Главное меню</b>"
        if hasattr(message_or_callback, 'edit_text'):
            await message_or_callback.edit_text(msg, reply_markup=get_main_menu())
        else:
            await message_or_callback.answer(msg, reply_markup=get_main_menu())
            
    await state.clear()

@router.callback_query(F.data == "cancel_search")
async def cancel_search_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    # Удаляем из всех очередей ожидания
    for cat in waiting_users:
        if user_id in waiting_users[cat]:
            waiting_users[cat].remove(user_id)
            
    await state.clear()
    await callback.answer("Поиск отменен")
    
    from bot.keyboards.inline import get_main_menu
    await callback.message.edit_text("👋 <b>Главное меню</b>", reply_markup=get_main_menu())

@router.callback_query(F.data.startswith("vote_"))
async def vote_callback(callback: CallbackQuery, db):
    user_id = callback.from_user.id
    parts = callback.data.split("_")
    vote_type = parts[1]
    chat_id = parts[2]
    votee_id = int(parts[3])
    
    await db.save_vote(user_id, votee_id, chat_id, vote_type)
    await callback.answer("✅ Ваш голос учтен!")
    from bot.keyboards.inline import get_main_menu
    await callback.message.edit_text("👋 <b>Спасибо за отзыв!</b>", reply_markup=get_main_menu())

@router.callback_query(F.data.startswith("report_"))
async def report_callback(callback: CallbackQuery, db):
    user_id = callback.from_user.id
    parts = callback.data.split("_")
    chat_id = parts[1]
    reported_id = int(parts[2])
    
    await db.save_report(chat_id, user_id, reported_id, "Жалоба от пользователя")
    await callback.answer("🚨 Жалоба отправлена администраторам!", show_alert=True)
    from bot.keyboards.inline import get_main_menu
    await callback.message.edit_text("👋 <b>Спасибо за бдительность!</b>", reply_markup=get_main_menu())

@router.message()
async def chat_message_handler(message: Message, state: FSMContext, bot: Bot, db):
    user_id = message.from_user.id
    data = await state.get_data()
    
    # Обработка команд завершения чата
    if message.text in ["/stop", "/end"]:
        await _handle_end_chat(user_id, message, state, db, bot)
        return
    elif message.text == "/next":
        await _handle_next_partner(user_id, message, state, db, bot)
        return
        
    if not data.get("partner_id"):
        return
        
    partner_id = data["partner_id"]
    
    if message.text == "/link":
        user = await db.get_user(user_id)
        if user and user['username']:
            link_text = f"🔗 <b>Мой профиль:</b> @{user['username']}"
        else:
            link_text = f"🔗 <b>Мой профиль:</b> <a href='tg://user?id={user_id}'>Нажмите здесь</a>"
            
        try:
            await bot.send_message(partner_id, link_text)
            await message.answer("✅ <b>Ссылка отправлена собеседнику!</b>")
        except: pass
        return
    
    try:
        await message.send_copy(partner_id)
    except BaseException as e:
        logger.error(f"❌ Ошибка отправки: {e}")
        await message.answer("❌ Собеседник отключился или заблокировал бота. Нажмите /stop")
