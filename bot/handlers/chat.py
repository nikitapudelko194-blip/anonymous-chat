from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from states.user_states import UserStates
from utils.matching import find_match, remove_from_queue, get_queue_size
from utils.notifications import notify_match_found
from keyboards.main import (
    main_menu_kb, search_category_kb, chat_menu_kb,
    report_reason_kb, searching_kb
)
from database.db import Database
from config import BOT_TOKEN

router = Router()
db = Database()
bot = Bot(token=BOT_TOKEN)

# Глобальные ссылки на последние сообщения (для редактирования)
last_messages = {}  # {user_id: {other_user: message_id}}

@router.callback_query(F.data == 'start_search')
async def start_search(
    callback: types.CallbackQuery,
    state: FSMContext
):
    """Начать поиск собеседника."""
    
    user = await db.get_user(callback.from_user.id)
    
    if user['is_banned']:
        await callback.answer(
            "❌ Вы заблокированы. Разблокируйтесь через 💎 premium",
            show_alert=True
        )
        return
    
    await callback.answer()
    await callback.message.edit_text(
        "🔍 Выберите способ поиска:",
        reply_markup=search_category_kb()
    )
    
    await state.set_state(UserStates.choosing_category)

@router.callback_query(F.data == 'main_menu')
async def main_menu(callback: types.CallbackQuery, state: FSMContext):
    """Вернуться в меню."""
    await callback.answer()
    await callback.message.edit_text(
        "🎉 <b>Anonymous Chat</b>\n\nПривет! Конфиденциальные беседы на любые темы.",
        reply_markup=main_menu_kb()
    )
    await state.set_state(UserStates.main_menu)

@router.callback_query(F.data.startswith('category_'))
async def select_category(
    callback: types.CallbackQuery,
    state: FSMContext
):
    """Выбрать категорию поиска."""
    
    category = callback.data.split('_')[1]
    await state.update_data(category=category)
    
    user = await db.get_user(callback.from_user.id)
    
    # Проверка премиум для гендерного фильтра
    if category == 'gender' and not user['is_premium']:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить premium", callback_data="buy_premium")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")],
        ])
        
        await callback.message.edit_text(
            "💎 <b>Premium функция</b>\n\n"
            "Фильтр по полу доступен только для:\n"
            "✨ Premium подписчиков",
            reply_markup=kb
        )
        return
    
    await callback.answer()
    await callback.message.edit_text(
        "⏳ <b>Поиск собеседника...</b>\n\n"
        "Пожалуйста, подождите...\n",
        reply_markup=searching_kb()
    )
    
    gender_filter = None
    if category == 'gender':
        gender_filter = user['gender']
    
    # Поиск матча через очередь
    match_id = await find_match(
        callback.from_user.id,
        category,
        gender_filter=gender_filter
    )
    
    if not match_id:
        # Пользователь добавлен в очередь
        queue_size = get_queue_size(category, gender_filter)
        await state.set_state(UserStates.searching)
        await state.update_data(
            searching_category=category,
            searching_gender=gender_filter,
            search_message_id=callback.message.message_id
        )
        return
    
    # ✅ МАТЧ НАЙДЕН!
    chat_id = f"{callback.from_user.id}_{match_id}"
    await db.create_chat(callback.from_user.id, match_id, category)
    
    # Уведомить обоих
    user1_profile = user
    user2_profile = await db.get_user(match_id)
    
    # Отредактировать на для текущего
    await callback.message.edit_text(
        "🎉 <b>Собеседник найден!</b>\n\n"
        f"👤 <b>{user2_profile.get('first_name', 'Аноним')}</b>, {user2_profile.get('age', '?')} лет\n"
        f"🐐 Пол: {'👨' if user2_profile.get('gender') == 'male' else '👩' if user2_profile.get('gender') == 'female' else '🙀'}\n\n"
        "💬 Можете начинать написывать сообщения:\n\n"
        "📸 <b>В диалоге можно делиться:</b>\n"
        "📷 Фотографиями\n"
        "🎞 Голосовыми сообщениями\n"
        "👽 Стикерами\n\n"
        "/stop - завершить\n"
        "/new - новый чат\n"
        "/report - репорт",
        reply_markup=chat_menu_kb()
    )
    
    # Уведомить второго
    try:
        msg = await bot.send_message(
            match_id,
            "🎉 <b>Собеседник найден!</b>\n\n"
            f"👤 <b>{user1_profile.get('first_name', 'Аноним')}</b>, {user1_profile.get('age', '?')} лет\n"
            f"🐐 Пол: {'👨' if user1_profile.get('gender') == 'male' else '👩' if user1_profile.get('gender') == 'female' else '🙀'}\n\n"
            "💬 Можете начинать написывать сообщения:\n\n"
            "📸 <b>В диалоге можно делиться:</b>\n"
            "📷 Фотографиями\n"
            "🎞 Голосовыми сообщениями\n"
            "👽 Стикерами\n\n"
            "/stop - завершить\n"
            "/new - новый чат\n"
            "/report - репорт",
            reply_markup=chat_menu_kb()
        )
        last_messages[match_id] = {callback.from_user.id: msg.message_id}
    except Exception as e:
        print(f"❌ Ошибка стартовых сообщений: {e}")
    
    await state.set_state(UserStates.in_chat)
    await state.update_data(
        current_chat=chat_id,
        other_user=match_id,
        my_user_id=callback.from_user.id
    )

@router.callback_query(F.data == 'cancel_search')
async def cancel_search(callback: types.CallbackQuery, state: FSMContext):
    """Отменить поиск."""
    data = await state.get_data()
    category = data.get('searching_category')
    gender_filter = data.get('searching_gender')
    
    await remove_from_queue(callback.from_user.id, category, gender_filter)
    
    await callback.answer()
    await callback.message.edit_text(
        "🎉 <b>Anonymous Chat</b>\n\nПривет! Конфиденциальные беседы на любые темы.",
        reply_markup=main_menu_kb()
    )
    await state.set_state(UserStates.main_menu)

# 📤 ИСПРАВЛЕННЫЙ ОБРАБОТЧИК ДЛЯ ВСЕХ ТИПОВ СООБЩЕНИЙ
@router.message(UserStates.in_chat)
async def handle_chat_message(
    message: types.Message,
    state: FSMContext
):
    """Обработать сообщения в чате (текст, фото, голос, стикер) и команды."""
    
    # Команды
    if message.text and message.text == '/stop':
        await stop_chat(message, state)
        return
    elif message.text and message.text == '/new':
        await new_chat(message, state)
        return
    elif message.text and message.text == '/report':
        await start_report(message, state)
        return
    
    data = await state.get_data()
    chat_id = data['current_chat']
    other_user = data['other_user']
    my_user_id = data['my_user_id']
    
    # Не отправлять пустые текстовые сообщения
    if message.text and (not message.text or message.text.startswith('/')):
        return
    
    # 💾 Определить тип сообщения и сохранить
    message_type = None
    if message.text:
        message_type = 'text'
        db_content = message.text
    elif message.photo:
        message_type = 'photo'
        db_content = f"[📷 Фото]"
    elif message.voice:
        message_type = 'voice'
        db_content = f"[🎞 Голос]"
    elif message.sticker:
        message_type = 'sticker'
        db_content = f"[👽 Стикер]"
    else:
        # Неподдерживаемый тип
        return
    
    # Сохранить в БД
    try:
        await db.save_message(
            chat_id=chat_id,
            sender_id=my_user_id,
            receiver_id=other_user,
            content=db_content
        )
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
    
    # 📤 Отправить собеседнику (НОВОЕ СООБЩЕНИЕ, не редактирование!)
    try:
        if message_type == 'text':
            # Текстовое сообщение
            await bot.send_message(
                other_user,
                f"💬 <i>{message.text}</i>",
                parse_mode="HTML"
            )
        elif message_type == 'photo':
            # Фотография с подписью если есть
            caption = f"📷 {message.caption}" if message.caption else None
            await bot.send_photo(
                other_user,
                message.photo[-1].file_id,
                caption=caption
            )
        elif message_type == 'voice':
            # Голосовое сообщение
            await bot.send_voice(
                other_user,
                message.voice.file_id
            )
        elif message_type == 'sticker':
            # Стикер
            await bot.send_sticker(
                other_user,
                message.sticker.file_id
            )
    except Exception as e:
        print(f"❌ Ошибка отправки ({message_type}): {e}")
        await message.answer(
            f"❌ Ошибка отправки. Возможно, собеседник вышел из чата.",
            parse_mode="HTML"
        )
        # Завершить чат при ошибке
        try:
            await db.end_chat(chat_id)
        except:
            pass
        await state.set_state(UserStates.main_menu)

async def stop_chat(message: types.Message, state: FSMContext):
    """Завершить чат."""
    data = await state.get_data()
    chat_id = data['current_chat']
    other_user = data['other_user']
    
    # Уведомить партнера
    try:
        await bot.send_message(
            other_user,
            "🖤 <b>Собеседник завершил чат</b>",
            parse_mode="HTML"
        )
    except:
        pass
    
    # Цочистить стек
    if other_user in last_messages:
        del last_messages[other_user]
    
    # Закончить чат
    await db.end_chat(chat_id)
    
    await message.answer(
        "🎉 <b>Anonymous Chat</b>\n\nПривет! Конфиденциальные беседы на любые темы.",
        reply_markup=main_menu_kb(),
        parse_mode="HTML"
    )
    await state.set_state(UserStates.main_menu)

async def new_chat(message: types.Message, state: FSMContext):
    """Начать новый чат."""
    data = await state.get_data()
    chat_id = data['current_chat']
    other_user = data['other_user']
    
    # Завершить текущий
    try:
        await bot.send_message(
            other_user,
            "🖤 <b>Собеседник запросил новый чат</b>",
            parse_mode="HTML"
        )
    except:
        pass
    
    # Цочистить
    if other_user in last_messages:
        del last_messages[other_user]
    
    await db.end_chat(chat_id)
    await message.answer(
        "⏳ <b>Поиск нового собеседника...</b>\n\nПожалуйста, подождите...",
        reply_markup=searching_kb(),
        parse_mode="HTML"
    )
    
    # Начать новый поиск
    data = await state.get_data()
    category = data.get('category', 'random')
    gender_filter = data.get('searching_gender')
    
    user = await db.get_user(message.from_user.id)
    if category == 'gender':
        gender_filter = user['gender']
    
    match_id = await find_match(
        message.from_user.id,
        category,
        gender_filter=gender_filter
    )
    
    if not match_id:
        # В очереди
        await state.set_state(UserStates.searching)
        return
    
    # Матч принят в /new_chat исполнения
    chat_id = f"{message.from_user.id}_{match_id}"
    await db.create_chat(message.from_user.id, match_id, category)
    
    user1_profile = user
    user2_profile = await db.get_user(match_id)
    
    await message.answer(
        "🎉 <b>Собеседник найден!</b>\n\n"
        f"👤 <b>{user2_profile.get('first_name', 'Аноним')}</b>, {user2_profile.get('age', '?')} лет\n"
        f"🐐 Пол: {'👨' if user2_profile.get('gender') == 'male' else '👩' if user2_profile.get('gender') == 'female' else '🙀'}\n\n"
        "💬 Можете начинать написывать сообщения:",
        reply_markup=chat_menu_kb(),
        parse_mode="HTML"
    )
    
    # Уведомить второго
    try:
        msg = await bot.send_message(
            match_id,
            "🎉 <b>Собеседник найден!</b>\n\n"
            f"👤 <b>{user1_profile.get('first_name', 'Аноним')}</b>, {user1_profile.get('age', '?')} лет\n"
            f"🐐 Пол: {'👨' if user1_profile.get('gender') == 'male' else '👩' if user1_profile.get('gender') == 'female' else '🙀'}\n\n"
            "💬 Можете начинать написывать сообщения:",
            reply_markup=chat_menu_kb(),
            parse_mode="HTML"
        )
        last_messages[match_id] = {message.from_user.id: msg.message_id}
    except:
        pass
    
    await state.set_state(UserStates.in_chat)
    await state.update_data(
        current_chat=chat_id,
        other_user=match_id,
        my_user_id=message.from_user.id
    )

async def start_report(message: types.Message, state: FSMContext):
    """Начать репорт."""
    
    await message.answer(
        "📋 <b>Выберите причину репорта:</b>",
        reply_markup=report_reason_kb(),
        parse_mode="HTML"
    )
    
    await state.set_state(UserStates.report_reason)

@router.callback_query(F.data.startswith('report_'))
async def handle_report_reason(
    callback: types.CallbackQuery,
    state: FSMContext
):
    """Обработать репорт."""
    
    reason = callback.data.split('_')[1]
    data = await state.get_data()
    
    chat_id = data['current_chat']
    reported_user_id = data['other_user']
    
    # Сохранить репорт
    await db.create_report(
        chat_id=chat_id,
        reporter_id=callback.from_user.id,
        reported_user_id=reported_user_id,
        reason=reason
    )
    
    # Инкрементировать
    await db.increment_reports(reported_user_id)
    
    # Проверить бан
    from utils.ban import check_and_apply_ban
    is_banned = await check_and_apply_ban(reported_user_id, db)
    
    if is_banned:
        from utils.notifications import notify_ban
        await notify_ban(
            reported_user_id,
            "Слишком много репортов",
            "через 7 дней"
        )
    
    await callback.answer("✅ Репорт отправлен", show_alert=True)
    
    # Завершить чат
    await db.end_chat(chat_id)
    
    await callback.message.edit_text(
        "🎉 <b>Anonymous Chat</b>\n\nПривет! Конфиденциальные беседы на любые темы.",
        reply_markup=main_menu_kb(),
        parse_mode="HTML"
    )
    
    await state.set_state(UserStates.main_menu)
