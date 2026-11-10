import asyncio
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.states import AdminStates
from app.keyboards import admin_kb, main_kb, admin_delete_products_kb
from app.database import (
    get_user, update_balance, add_product, get_tickets, 
    reply_ticket, get_all_users, get_db, get_all_products_for_admin, delete_product
)
from app.config import ADMIN_IDS

router = Router()
bot = None

@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer("🔧 Админ-панель:", reply_markup=admin_kb())

@router.message(F.text == "➕ Добавить товар")
async def add_product_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await message.answer("Введите название товара:")
    await state.set_state(AdminStates.waiting_product_name)

@router.message(AdminStates.waiting_product_name)
async def add_product_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите описание товара (краткое):")
    await state.set_state(AdminStates.waiting_product_desc)

@router.message(AdminStates.waiting_product_desc)
async def add_product_desc(message: types.Message, state: FSMContext):
    await state.update_data(desc=message.text)
    await message.answer("Введите цену в USD (например: 9.99):")
    await state.set_state(AdminStates.waiting_product_price)

@router.message(AdminStates.waiting_product_price)
async def add_product_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Введите число:")
        return
    await state.update_data(price=price)
    await message.answer("Отправьте фотографию товара (или напишите 'нет', если без фото):")
    await state.set_state(AdminStates.waiting_product_photo)

@router.message(AdminStates.waiting_product_photo, F.photo | F.text)
async def add_product_photo(message: types.Message, state: FSMContext):
    if message.photo:
        photo_id = message.photo[-1].file_id
    else:
        photo_id = None
    await state.update_data(photo_id=photo_id)
    await message.answer("Отправьте сам товар (файл-документ, видео или текст).\nЭто получит пользователь после покупки:")
    await state.set_state(AdminStates.waiting_product_file)

@router.message(AdminStates.waiting_product_file)
async def add_product_file(message: types.Message, state: FSMContext):
    file_id = None
    file_type = None
    
    if message.document:
        file_id = message.document.file_id
        file_type = "document"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.text:
        file_id = message.text 
        file_type = "text"
    else:
        await message.answer("Пожалуйста, отправьте файл (документ, видео) или текст.")
        return

    await state.update_data(file_id=file_id, file_type=file_type)
    await message.answer("Введите количество на складе (целое число):")
    await state.set_state(AdminStates.waiting_product_stock)

@router.message(AdminStates.waiting_product_stock)
async def add_product_stock(message: types.Message, state: FSMContext):
    try:
        stock = int(message.text)
    except ValueError:
        await message.answer("Введите целое число:")
        return
    data = await state.get_data()
    
    add_product(
        data["name"], data["desc"], data["price"], 
        data["photo_id"], data["file_id"], data["file_type"], stock
    )
    await state.clear()
    await message.answer(f"✅ Товар «{data['name']}» добавлен!", reply_markup=admin_kb())

# ========== УДАЛЕНИЕ ТОВАРА ==========
@router.message(F.text == "🗑 Удалить товар")
async def admin_delete_product_start(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return
        
    products = get_all_products_for_admin() 
    
    if not products:
        await message.answer("Каталог пуст. Удалять нечего.")
        return
        
    await message.answer(
        "Выберите товар, который хотите удалить (нажмите на кнопку):",
        reply_markup=admin_delete_products_kb(products)
    )

@router.callback_query(F.data.startswith("del_prod_"))
async def admin_delete_product_confirm(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа", show_alert=True)
        return
        
    product_id = int(callback.data.split("_")[2])
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_del_{product_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_del")
        ]
    ])
    
    await callback.message.edit_text(
        "Вы уверены, что хотите удалить этот товар? Это действие нельзя отменить.",
        reply_markup=kb
    )

@router.callback_query(F.data.startswith("confirm_del_"))
async def admin_delete_product_execute(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
        
    product_id = int(callback.data.split("_")[2])
    delete_product(product_id)
    
    await callback.message.edit_text("✅ Товар успешно удален из базы данных.")

@router.callback_query(F.data == "cancel_del")
async def admin_delete_product_cancel(callback: types.CallbackQuery):
    await callback.message.edit_text("Удаление отменено.")
# ==================================

@router.message(F.text == "💵 Выдать баланс")
async def admin_give_balance_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await message.answer("Введите Telegram ID пользователя, которому нужно выдать баланс:")
    await state.set_state(AdminStates.waiting_balance_user_id)

@router.message(AdminStates.waiting_balance_user_id)
async def admin_give_balance_user(message: types.Message, state: FSMContext):
    try:
        target_id = int(message.text)
    except ValueError:
        await message.answer("ID должен состоять только из цифр. Попробуйте снова:")
        return
        
    user = get_user(target_id)
    if not user:
        await message.answer("Пользователь с таким ID не найден в базе. Убедитесь, что он запускал бота.")
        await state.clear()
        return

    await state.update_data(target_id=target_id)
    await message.answer(f"Пользователь найден. Его текущий баланс: {user[2]:.2f}$\nВведите сумму для выдачи:")
    await state.set_state(AdminStates.waiting_balance_amount)

@router.message(AdminStates.waiting_balance_amount)
async def admin_give_balance_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0:
            await message.answer("Сумма должна быть больше нуля.")
            return
    except ValueError:
        await message.answer("Введите число.")
        return

    data = await state.get_data()
    target_id = data["target_id"]
    
    update_balance(target_id, amount)
    updated_user = get_user(target_id)
    
    await message.answer(
        f"✅ Баланс пользователя {target_id} успешно пополнен на {amount:.2f}$.\n"
        f"Новый баланс: {updated_user[2]:.2f}$",
        reply_markup=admin_kb()
    )
    await state.clear()
    
    if bot:
        try:
            await bot.send_message(target_id, f"💰 Вам зачислен баланс: +{amount:.2f}$!\nТекущий баланс: {updated_user[2]:.2f}$")
        except:
            pass

@router.message(F.text == "📢 Рассылка")
async def broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await message.answer("Введите текст для рассылки всем пользователям:")
    await state.set_state(AdminStates.waiting_broadcast)

@router.message(AdminStates.waiting_broadcast)
async def broadcast_send(message: types.Message, state: FSMContext):
    await state.clear()
    users = get_all_users()
    
    await message.answer(f"⏳ Начинаю фоновую рассылку для {len(users)} пользователей...\nРезультат пришлю сюда.", reply_markup=admin_kb())
    
    if bot:
        task = asyncio.create_task(process_broadcast(bot, message.text, message.from_user.id, users))
        from app.handlers.user import bg_tasks
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)

async def process_broadcast(bot_instance, text, admin_id, users):
    success = 0
    blocked = 0
    errors = 0
    
    for uid in users:
        try:
            await bot_instance.send_message(uid, text)
            success += 1
        except Exception as e:
            if "blocked" in str(e).lower() or "chat not found" in str(e).lower():
                blocked += 1
            else:
                errors += 1
        await asyncio.sleep(0.1)

    report = (
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📨 Всего в базе: {len(users)}\n"
        f"✅ Доставлено: {success}\n"
        f"🚫 Заблокировали бота: {blocked}\n"
        f"⚠️ Другие ошибки: {errors}"
    )
    try:
        await bot_instance.send_message(admin_id, report, parse_mode="HTML")
    except:
        pass

@router.message(F.text == "🎫 Тикеты")
async def list_tickets(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return
    tickets = get_tickets('open')
    if not tickets:
        await message.answer("Нет открытых тикетов.")
        return
    for t in tickets:
        await message.answer(
            f"🎫 Тикет #{t[0]}\nОт: {t[1]}\nСообщение: {t[2]}\nДата: {t[5][:16]}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✏️ Ответить", callback_data=f"reply_{t[0]}")]
            ])
        )

@router.callback_query(F.data.startswith("reply_"))
async def reply_ticket_start(callback: types.CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split("_")[1])
    await state.update_data(ticket_id=ticket_id)
    await callback.message.answer("Введите ответ для пользователя:")
    await state.set_state(AdminStates.waiting_ticket_reply)

@router.message(AdminStates.waiting_ticket_reply)
async def reply_ticket_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data["ticket_id"]
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM tickets WHERE id = ?", (ticket_id,))
    user_id = c.fetchone()[0]
    conn.close()
    reply_ticket(ticket_id, message.text)
    
    if bot:
        await bot.send_message(user_id, f"📩 Ответ поддержки:\n\n{message.text}")
    await message.answer("✅ Ответ отправлен.", reply_markup=admin_kb())
    await state.clear()

@router.message(F.text == "🔙 Выйти из админки")
async def exit_admin(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_kb())