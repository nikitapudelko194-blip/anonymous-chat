from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from states.user_states import UserStates
from utils.matching import find_match, remove_from_queue, get_queue_size
from utils.notifications import notify_match_found
from database.db import Database

router = Router()
db = Database()

@router.callback_query(F.data == 'start_search')
async def start_search(
    callback: types.CallbackQuery,
    state: FSMContext
):
    """Начать поиск собеседника."""
    
    user = await db.get_user(callback.from_user.id)
    
    if user['is_banned']:
        await callback.answer(
            "❌ Вы заблокированы. Разблокируйтесь через премиум подписку",
            show_alert=True
        )
        return
    
    await callback.answer()
    
    # Выбор категории
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Случайный", callback_data="category_random")],
        [InlineKeyboardButton(text="👥 По полу", callback_data="category_gender")],
    ])
    
    await callback.message.edit_text(
        "🔍 Выберите способ поиска собеседника:",
        reply_markup=kb
    )
    
    await state.set_state(UserStates.choosing_category)

@router.callback_query(F.data.startswith('category_'))
async def select_category(
    callback: types.CallbackQuery,
    state: FSMContext
):
    """Выбрать категорию поиска."""
    
    category = callback.data.split('_')[1]
    await state.update_data(category=category)
    
    user = await db.get_user(callback.from_user.id)
    
    # Для фильтра по полу нужна премиум подписка
    if category == 'gender' and not user['is_premium']:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить премиум", callback_data="buy_premium")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="start_search")],
        ])
        
        await callback.message.edit_text(
            "💎 Фильтр по полу доступен только для премиум пользователей\n\n"
            "Получите доступ к:\n"
            "✨ Выбору пола собеседника\n"
            "✨ Удалению рекламы\n"
            "✨ Приоритету в поиске",
            reply_markup=kb
        )
        return
    
    # Начать поиск
    await callback.answer()
    await callback.message.edit_text("🔍 Ищем собеседника...")
    
    gender_filter = None
    if category == 'gender':
        gender_filter = user['gender']
    
    # Найти матч ЧЕРЕЗ ОЧЕРЕДЬ
    match_id = await find_match(
        callback.from_user.id,
        category,
        gender_filter=gender_filter
    )
    
    if not match_id:
        # Пользователь добавлен в очередь - ждем
        queue_size = get_queue_size(category, gender_filter)
        await callback.message.edit_text(
            f"⏳ Поиск собеседника...\n\n"
            f"В очереди: {queue_size} человек\n\n"
            f"Отменить: /cancel"
        )
        await state.set_state(UserStates.searching)
        await state.update_data(searching_category=category, searching_gender=gender_filter)
        return
    
    # ✅ МАТЧ НАЙДЕН!
    chat_id = f"{callback.from_user.id}_{match_id}"
    await db.create_chat(callback.from_user.id, match_id, category)
    
    # Уведомить обоих
    user1_profile = user
    user2_profile = await db.get_user(match_id)
    
    await notify_match_found(
        callback.from_user.id,
        match_id,
        user1_profile,
        user2_profile
    )
    
    # НАЧАТЬ ЧАТ для обоих
    await callback.message.edit_text(
        f"🎉 Собеседник найден!\n\n"
        f"👤 {user2_profile['first_name']}, {user2_profile['age']} лет\n\n"
        f"💬 Можете начать писать сообщения\n\n"
        f"Командировка: /stop или /report"
    )
    
    await state.set_state(UserStates.in_chat)
    await state.update_data(current_chat=chat_id, other_user=match_id)

@router.message(UserStates.searching)
async def cancel_search(
    message: types.Message,
    state: FSMContext
):
    """Отменить поиск собеседника."""
    
    if message.text == '/cancel':
        data = await state.get_data()
        category = data.get('searching_category')
        gender_filter = data.get('searching_gender')
        
        await remove_from_queue(message.from_user.id, category, gender_filter)
        await message.answer("❌ Поиск отменен")
        await state.clear()

@router.message(UserStates.in_chat)
async def handle_chat_message(
    message: types.Message,
    state: FSMContext
):
    """Обработать сообщение в чате."""
    
    if message.text in ['/stop', '/report']:
        if message.text == '/stop':
            await handle_stop_chat(message, state)
        elif message.text == '/report':
            await start_report(message, state)
        return
    
    data = await state.get_data()
    chat_id = data['current_chat']
    other_user = data['other_user']
    
    # 💾 Сохранить сообщение
    await db.save_message(
        chat_id=chat_id,
        sender_id=message.from_user.id,
        receiver_id=other_user,
        content=message.text
    )
    
    # 📤 Отправить собеседнику БЕЗ КНОПОК
    try:
        await message.bot.send_message(
            other_user,
            f"💬 {message.text}"
        )
    except Exception as e:
        print(f"❌ Ошибка при отправке сообщения {other_user}: {e}")

async def handle_stop_chat(
    message: types.Message,
    state: FSMContext
):
    """Завершить чат."""
    
    data = await state.get_data()
    chat_id = data['current_chat']
    other_user = data['other_user']
    
    # Уведомить партнера
    try:
        await message.bot.send_message(
            other_user,
            "❌ Собеседник завершил чат"
        )
    except:
        pass
    
    # Завершить чат
    await db.end_chat(chat_id)
    await message.answer("✅ Чат завершен")
    await state.clear()

async def start_report(
    message: types.Message,
    state: FSMContext
):
    """Начать жалобу на пользователя."""
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Спам", callback_data="report_spam")],
        [InlineKeyboardButton(text="😤 Оскорбление", callback_data="report_abuse")],
        [InlineKeyboardButton(text="🔞 Неприличный контент", callback_data="report_inappropriate")],
        [InlineKeyboardButton(text="😠 Домогательство", callback_data="report_harassment")],
        [InlineKeyboardButton(text="❌ Другое", callback_data="report_other")],
    ])
    
    await message.answer(
        "📋 Выберите причину жалобы:",
        reply_markup=kb
    )
    
    await state.set_state(UserStates.report_reason)

@router.callback_query(F.data.startswith('report_'))
async def handle_report_reason(
    callback: types.CallbackQuery,
    state: FSMContext
):
    """Обработать жалобу."""
    
    reason = callback.data.split('_')[1]
    data = await state.get_data()
    
    chat_id = data['current_chat']
    reported_user_id = data['other_user']
    
    # Сохранить жалобу
    await db.create_report(
        chat_id=chat_id,
        reporter_id=callback.from_user.id,
        reported_user_id=reported_user_id,
        reason=reason
    )
    
    # Инкрементировать счетчик жалоб
    await db.increment_reports(reported_user_id)
    
    # Проверить бан
    from utils.ban import check_and_apply_ban
    is_banned = await check_and_apply_ban(reported_user_id, db)
    
    if is_banned:
        from utils.notifications import notify_ban
        await notify_ban(
            reported_user_id,
            "Слишком много жалоб от других пользователей",
            "через 7 дней"
        )
    
    await callback.answer("✅ Жалоба отправлена", show_alert=True)
    
    # Закончить чат
    await db.end_chat(chat_id)
    await state.clear()
