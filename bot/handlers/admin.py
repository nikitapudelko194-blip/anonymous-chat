from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import logging
from bot.config import ADMIN_ID
from bot.keyboards.inline import (
    get_admin_main_keyboard, get_admin_users_keyboard,
    get_admin_subs_keyboard, get_admin_cancel_keyboard
)

router = Router()
logger = logging.getLogger(__name__)

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_user_info = State()
    waiting_for_user_ban = State()
    waiting_for_user_premium = State()
    waiting_for_sub_add = State()
    waiting_for_sub_del = State()

def is_admin(user_id: int) -> bool:
    if ADMIN_ID is None:
        return False
    return user_id == ADMIN_ID

@router.message(Command("admin"))
async def cmd_admin_panel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("👑 <b>Добро пожаловать в Панель Администратора!</b>\n\nВыберите нужный раздел:", reply_markup=get_admin_main_keyboard())

@router.callback_query(F.data == "admin_main_menu")
async def admin_main_menu_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.clear()
    await callback.message.edit_text("👑 <b>Главное меню Администратора:</b>", reply_markup=get_admin_main_keyboard())

@router.callback_query(F.data == "admin_cancel_action")
async def admin_cancel_action_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено.\n\n👑 <b>Главное меню Администратора:</b>", reply_markup=get_admin_main_keyboard())

@router.message(Command("admin_give_premium"))
async def cmd_admin_give_premium(message: Message, db, bot):
    if not is_admin(message.from_user.id):
        await message.answer("❌ <b>Доступ запрещён!</b>\n\nЭта команда только для администратора.")
        return
    
    try:
        args = message.text.split()
        if len(args) < 3:
            await message.answer(
                "❌ <b>Неправильный формат!</b>\n\nИспользование:\n<code>/admin_give_premium 123456789 1</code>"
            )
            return
        
        user_id = int(args[1])
        months = int(args[2])
        if months >= 100: months = 3650
        
        success = await db.give_premium(user_id, months)
        if success:
            user = await db.get_user(user_id)
            username = f"@{user['username']}" if user and user['username'] else "ID: " + str(user_id)
            await message.answer(f"✅ <b>Премиум выдан!</b>\n\n👤 {username}\n⏱️ На {months} месяцев\n✨ Срок действия обновлён")
            try:
                await bot.send_message(user_id, "✨ <b>Поздравляем!</b>\n\nВам выдан ПРЕМИУМ статус!\n🎉 Теперь вам доступны все преимущества!")
            except: pass
        else:
            await message.answer("❌ <b>Ошибка!</b>\n\nНе удалось выдать премиум.")
    except ValueError:
        await message.answer("❌ <b>Ошибка!</b>\n\nID и количество месяцев должны быть числами.")
    except Exception as e:
        await message.answer(f"❌ <b>Ошибка!</b>\n\n{str(e)}")

@router.message(Command("admin_remove_premium"))
async def cmd_admin_remove_premium(message: Message, db):
    if not is_admin(message.from_user.id):
        await message.answer("❌ <b>Доступ запрещён!</b>")
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("❌ <b>Неправильный формат!</b>")
            return
        
        user_id = int(args[1])
        success = await db.remove_premium(user_id)
        if success:
            user = await db.get_user(user_id)
            username = f"@{user['username']}" if user and user['username'] else str(user_id)
            await message.answer(f"✅ <b>Премиум отозван!</b>\n\n👤 {username}")
        else:
            await message.answer("❌ <b>Ошибка!</b>")
    except ValueError:
        await message.answer("❌ <b>Ошибка!</b>")

@router.message(Command("admin_ban"))
async def cmd_admin_ban_user(message: Message, db, bot):
    if not is_admin(message.from_user.id):
        await message.answer("❌ <b>Доступ запрещён!</b>")
        return
    
    try:
        parts = message.text.split(None, 3)
        if len(parts) < 3:
            await message.answer("❌ <b>Неправильный формат!</b>")
            return
        
        user_id = int(parts[1])
        days = int(parts[2])
        reason = parts[3] if len(parts) > 3 else "Нарушение правил"
        
        await db.ban_user(user_id, reason, days if days > 0 else None)
        user = await db.get_user(user_id)
        username = f"@{user['username']}" if user and user['username'] else str(user_id)
        expire_text = f"на {days} дней" if days > 0 else "навсегда"
        
        await message.answer(f"✅ <b>Пользователь забанен!</b>\n\n👤 {username}\n⏱️ {expire_text}\n📝 Причина: {reason}")
        try:
            await bot.send_message(user_id, f"🚫 <b>Вы забанены!</b>\n\n📝 Причина: {reason}\n⏱️ {expire_text}")
        except: pass
    except ValueError:
        await message.answer("❌ <b>Ошибка!</b>\n\nID и дни должны быть числами.")

@router.message(Command("admin_unban"))
async def cmd_admin_unban_user(message: Message, db, bot):
    if not is_admin(message.from_user.id):
        await message.answer("❌ <b>Доступ запрещён!</b>")
        return
    
    try:
        args = message.text.split()
        if len(args) < 2: return
        user_id = int(args[1])
        
        # Разбан
        import aiosqlite
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
            await conn.commit()
            
        user = await db.get_user(user_id)
        username = f"@{user['username']}" if user and user['username'] else str(user_id)
        await message.answer(f"✅ <b>Пользователь разбанен!</b>\n\n👤 {username}")
        try:
            await bot.send_message(user_id, "✅ <b>Вас разбанили!</b>\n\n🎉 Добро пожаловать обратно!")
        except: pass
    except ValueError:
        pass

@router.message(Command("admin_info"))
async def cmd_admin_user_info(message: Message, db):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 2: return
    user_id = int(args[1])
    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ <b>Пользователь не найден!</b>")
        return
    is_banned = await db.is_user_banned(user_id)
    is_premium = await db.is_premium_active(user_id)
    
    info_text = f"""👤 <b>ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ</b>\n🆔 ID: <code>{user['user_id']}</code>
📝 Username: @{user['username']}
💳 Премиум: {"✅" if is_premium else "❌"}
⚠️ Статус: {"🚫 ЗАБАНЕН" if is_banned else "✅ Активен"}
👍 Позитивных оценок: {user['positive_votes']}
👎 Негативных оценок: {user['negative_votes']}"""
    await message.answer(info_text)

@router.message(Command("admin_stats"))
async def cmd_admin_stats(message: Message, db):
    if not is_admin(message.from_user.id): return
    stats = await db.get_stats()
    if not stats: return
    stats_text = f"""📊 <b>СТАТИСТИКА БОТА</b>\n👥 Всего пользователей: {stats['total_users']}
💳 Премиум: {stats['premium_users']}
🚫 Забанено: {stats['banned_users']}
🔴 Активных диалогов: {stats['active_chats']}
📊 Всего диалогов: {stats['total_chats']}"""
    await message.answer(stats_text)

@router.message(Command("admin_list_premium"))
async def cmd_admin_list_premium(message: Message, db):
    if not is_admin(message.from_user.id): return
    premium_users = await db.get_premium_users()
    if not premium_users:
        await message.answer("❌ <b>Нет премиум пользователей!</b>")
        return
    users_list = "📋 <b>ПРЕМИУМ ПОЛЬЗОВАТЕЛИ</b>\n\n"
    for i, user in enumerate(premium_users, 1):
        users_list += f"{i}. @{user['username'] or user['user_id']} - {user['premium_expires_at']}\n"
    await message.answer(users_list)

@router.message(Command("admin_add_sub"))
async def cmd_admin_add_sub(message: Message, db):
    if not is_admin(message.from_user.id): return
    
    args = message.text.split(maxsplit=3)
    if len(args) < 4:
        await message.answer("❌ <b>Формат:</b>\n<code>/admin_add_sub &lt;channel_id&gt; &lt;url&gt; &lt;Название&gt;</code>\nПример: <code>/admin_add_sub @durov https://t.me/durov Канал Павла Дурова</code>")
        return
        
    channel_id = args[1]
    url = args[2]
    name = args[3]
    
    success = await db.add_mandatory_channel(channel_id, url, name)
    if success:
        await message.answer(f"✅ <b>Канал добавлен в обязательную подписку!</b>\n\nID: {channel_id}\nИмя: {name}\n\n⚠️ <i>Убедитесь, что бот добавлен в этот канал как администратор!</i>")
    else:
        await message.answer("❌ <b>Ошибка при добавлении канала.</b>")

@router.message(Command("admin_del_sub"))
async def cmd_admin_del_sub(message: Message, db):
    if not is_admin(message.from_user.id): return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ <b>Формат:</b>\n<code>/admin_del_sub &lt;channel_id&gt;</code>")
        return
        
    channel_id = args[1]
    success = await db.remove_mandatory_channel(channel_id)
    if success:
        await message.answer(f"✅ <b>Канал {channel_id} удален из обязательной подписки!</b>")
    else:
        await message.answer(f"❌ <b>Канал {channel_id} не найден.</b>")

@router.message(Command("admin_list_subs"))
async def cmd_admin_list_subs(message: Message, db):
    if not is_admin(message.from_user.id): return
    
    channels = await db.get_mandatory_channels()
    if not channels:
        await message.answer("❌ <b>Список обязательной подписки пуст.</b>")
        return
        
    text = "📋 <b>ОБЯЗАТЕЛЬНАЯ ПОДПИСКА:</b>\n\n"
    for idx, ch in enumerate(channels, 1):
        text += f"{idx}. <b>{ch['name']}</b>\nID: <code>{ch['channel_id']}</code>\n🔗 {ch['url']}\n\n"
        
    await message.answer(text)

# Обработка Inline кнопок админ панели

@router.callback_query(F.data == "admin_stats")
async def admin_stats_cb(callback: CallbackQuery, db):
    if not is_admin(callback.from_user.id): return
    stats = await db.get_stats()
    if not stats:
        await callback.answer("Ошибка получения статистики", show_alert=True)
        return
    stats_text = f"""📊 <b>СТАТИСТИКА БОТА</b>
👥 Всего пользователей: {stats['total_users']}
💳 Премиум: {stats['premium_users']}
🚫 Забанено: {stats['banned_users']}
🔴 Активных диалогов: {stats['active_chats']}
📊 Всего диалогов: {stats['total_chats']}"""
    await callback.message.edit_text(stats_text, reply_markup=get_admin_cancel_keyboard())

@router.callback_query(F.data == "admin_users_menu")
async def admin_users_menu_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.message.edit_text("👥 <b>Управление пользователями:</b>", reply_markup=get_admin_users_keyboard())

@router.callback_query(F.data == "admin_subs_menu")
async def admin_subs_menu_cb(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return
    await callback.message.edit_text("🔗 <b>Управление обязательной подпиской:</b>", reply_markup=get_admin_subs_keyboard())

@router.callback_query(F.data == "admin_subs_list")
async def admin_subs_list_cb(callback: CallbackQuery, db):
    if not is_admin(callback.from_user.id): return
    channels = await db.get_mandatory_channels()
    if not channels:
        await callback.message.edit_text("❌ <b>Список обязательной подписки пуст.</b>", reply_markup=get_admin_subs_keyboard())
        return
        
    text = "📋 <b>ОБЯЗАТЕЛЬНАЯ ПОДПИСКА:</b>\n\n"
    for idx, ch in enumerate(channels, 1):
        text += f"{idx}. <b>{ch['name']}</b>\nID: <code>{ch['channel_id']}</code>\n🔗 {ch['url']}\n\n"
        
    await callback.message.edit_text(text, reply_markup=get_admin_subs_keyboard())

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.message.edit_text("📢 <b>Рассылка сообщений</b>\n\nОтправьте сообщение (текст, фото, видео), которое вы хотите разослать всем пользователям бота.", reply_markup=get_admin_cancel_keyboard())

@router.message(AdminStates.waiting_for_broadcast)
async def process_broadcast(message: Message, state: FSMContext, db, bot: Bot):
    if not is_admin(message.from_user.id): return
    await state.clear()
    
    users = await db.get_all_users()
    if not users:
        await message.answer("❌ Нет пользователей для рассылки.")
        return
        
    status_msg = await message.answer(f"⏳ Начинаю рассылку для {len(users)} пользователей...")
    
    success = 0
    failed = 0
    
    for user_id in users:
        try:
            await message.send_copy(user_id)
            success += 1
        except Exception:
            failed += 1
            
    await status_msg.edit_text(f"✅ <b>Рассылка завершена!</b>\n\nУспешно доставлено: {success}\nОшибок (заблокировали бота): {failed}")

@router.callback_query(F.data == "admin_user_info")
async def admin_user_info_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_user_info)
    await callback.message.edit_text("🔎 Отправьте ID пользователя, чтобы получить информацию о нем:", reply_markup=get_admin_cancel_keyboard())

@router.message(AdminStates.waiting_for_user_info)
async def process_admin_user_info(message: Message, state: FSMContext, db):
    if not is_admin(message.from_user.id): return
    try:
        user_id = int(message.text)
        user = await db.get_user(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден.", reply_markup=get_admin_cancel_keyboard())
            return
            
        is_banned = await db.is_user_banned(user_id)
        is_premium = await db.is_premium_active(user_id)
        info_text = f"👤 <b>ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ</b>\n🆔 ID: <code>{user['user_id']}</code>\n📝 Username: @{user['username']}\n💳 Премиум: {'✅' if is_premium else '❌'}\n⚠️ Статус: {'🚫 ЗАБАНЕН' if is_banned else '✅ Активен'}\n👍 Позитивных оценок: {user['positive_votes']}\n👎 Негативных оценок: {user['negative_votes']}"
        
        await message.answer(info_text, reply_markup=get_admin_users_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите корректный числовой ID.", reply_markup=get_admin_cancel_keyboard())

@router.callback_query(F.data == "admin_user_ban")
async def admin_user_ban_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_user_ban)
    await callback.message.edit_text("🚫 Отправьте команду для бана или разбана:\n\nБан: <code>&lt;ID&gt; &lt;Дни (0=навсегда)&gt; &lt;Причина&gt;</code>\nПример: <code>1234567 7 Спам</code>\n\nРазбан: <code>&lt;ID&gt; unban</code>\nПример: <code>1234567 unban</code>", reply_markup=get_admin_cancel_keyboard())

@router.message(AdminStates.waiting_for_user_ban)
async def process_admin_user_ban(message: Message, state: FSMContext, db, bot: Bot):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    try:
        user_id = int(args[0])
        if len(args) == 2 and args[1].lower() == 'unban':
            import aiosqlite
            async with aiosqlite.connect(db.db_path) as conn:
                await conn.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
                await conn.commit()
            await message.answer(f"✅ Пользователь {user_id} разбанен.", reply_markup=get_admin_users_keyboard())
            try: await bot.send_message(user_id, "✅ <b>Вас разбанили!</b>\n\n🎉 Добро пожаловать обратно!")
            except: pass
            await state.clear()
            return
            
        days = int(args[1])
        reason = " ".join(args[2:]) if len(args) > 2 else "Нарушение правил"
        await db.ban_user(user_id, reason, days if days > 0 else None)
        await message.answer(f"✅ Пользователь {user_id} забанен на {days} дней. Причина: {reason}", reply_markup=get_admin_users_keyboard())
        try: await bot.send_message(user_id, f"🚫 <b>Вы забанены!</b>\n\n📝 Причина: {reason}\n⏱️ Срок: {days} дней")
        except: pass
        await state.clear()
    except Exception:
        await message.answer("❌ Ошибка формата.", reply_markup=get_admin_cancel_keyboard())

@router.callback_query(F.data == "admin_user_premium")
async def admin_user_premium_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_user_premium)
    await callback.message.edit_text("💳 Отправьте ID и количество месяцев для выдачи премиума (или 0 чтобы забрать):\nПример: <code>1234567 1</code>", reply_markup=get_admin_cancel_keyboard())

@router.message(AdminStates.waiting_for_user_premium)
async def process_admin_user_premium(message: Message, state: FSMContext, db, bot: Bot):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    try:
        user_id = int(args[0])
        months = int(args[1])
        if months == 0:
            await db.remove_premium(user_id)
            await message.answer(f"✅ Премиум у {user_id} отозван.", reply_markup=get_admin_users_keyboard())
        else:
            await db.give_premium(user_id, months)
            await message.answer(f"✅ Премиум на {months} мес. выдан {user_id}.", reply_markup=get_admin_users_keyboard())
            try: await bot.send_message(user_id, "✨ <b>Вам выдан ПРЕМИУМ статус!</b>")
            except: pass
        await state.clear()
    except Exception:
        await message.answer("❌ Ошибка формата.", reply_markup=get_admin_cancel_keyboard())

@router.callback_query(F.data == "admin_subs_add")
async def admin_subs_add_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_sub_add)
    await callback.message.edit_text("➕ Отправьте данные канала:\n\n<code>&lt;ID канала&gt; &lt;Ссылка&gt; &lt;Название для кнопки&gt;</code>\nПример: <code>@durov https://t.me/durov Канал Павла Дурова</code>", reply_markup=get_admin_cancel_keyboard())

@router.message(AdminStates.waiting_for_sub_add)
async def process_admin_subs_add(message: Message, state: FSMContext, db):
    if not is_admin(message.from_user.id): return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("❌ Ошибка формата.", reply_markup=get_admin_cancel_keyboard())
        return
    success = await db.add_mandatory_channel(args[0], args[1], args[2])
    if success:
        await message.answer(f"✅ Канал {args[2]} добавлен!", reply_markup=get_admin_subs_keyboard())
        await state.clear()
    else:
        await message.answer("❌ Ошибка добавления.", reply_markup=get_admin_cancel_keyboard())

@router.callback_query(F.data == "admin_subs_del")
async def admin_subs_del_cb(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    await state.set_state(AdminStates.waiting_for_sub_del)
    await callback.message.edit_text("➖ Отправьте ID канала для удаления:\nПример: <code>@durov</code>", reply_markup=get_admin_cancel_keyboard())

@router.message(AdminStates.waiting_for_sub_del)
async def process_admin_subs_del(message: Message, state: FSMContext, db):
    if not is_admin(message.from_user.id): return
    channel_id = message.text.strip()
    success = await db.remove_mandatory_channel(channel_id)
    if success:
        await message.answer(f"✅ Канал {channel_id} удален!", reply_markup=get_admin_subs_keyboard())
        await state.clear()
    else:
        await message.answer("❌ Канал не найден.", reply_markup=get_admin_subs_keyboard())
        await state.clear()
