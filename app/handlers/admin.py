import asyncio
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.states import AdminStates
from app.keyboards import admin_kb, main_kb, admin_categories_kb, admin_category_view_kb
from app.database import (
    get_user, update_balance, add_product, get_tickets, 
    reply_ticket, get_all_users, get_db, add_category, delete_category, delete_product
)
from app.config import ADMIN_IDS

router = Router()
bot = None

@router.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён.")
        return
    await state.clear()
    await message.answer("🔧 Админ-панель:", reply_markup=admin_kb())

# ========== ПРОСМОТР КАТАЛОГА (КАТЕГОРИИ) ==========
@router.message(F.text == "📂 Просмотр каталога", StateFilter("*"))
async def admin_catalog_view(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await state.clear()
    await message.answer("📂 Управление категориями:", reply_markup=admin_categories_kb())

@router.callback_query(F.data == "admin_back_cats")
async def admin_back_to_cats(callback: types.CallbackQuery):
    await callback.message.edit_text("📂 Управление категориями:", reply_markup=admin_categories_kb())

@router.callback_query(F.data == "admin_add_cat")
async def admin_add_category_prompt(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название новой категории:")
    await state.set_state(AdminStates.waiting_category_name)

@router.message(AdminStates.waiting_category_name)
async def admin_add_category_save(message: types.Message, state: FSMContext):
    add_category(message.text)
    await state.clear()
    await message.answer(f"✅ Категория «{message.text}» добавлена!", reply_markup=admin_kb())
    await message.answer("📂 Управление категориями:", reply_markup=admin_categories_kb())

@router.callback_query(F.data.startswith("admin_cat_"))
async def admin_open_category(callback: types.CallbackQuery):
    cat_id = int(callback.data.split("_")[2])
    await callback.message.edit_text("📂 Товары в категории:", reply_markup=admin_category_view_kb(cat_id))

@router.callback_query(F.data.startswith("admin_del_cat_"))
async def admin_delete_category(callback: types.CallbackQuery):
    cat_id = int(callback.data.split("_")[3])
    delete_category(cat_id)
    await callback.answer("Категория и её товары удалены.", show_alert=True)
    await callback.message.edit_text("📂 Управление категориями:", reply_markup=admin_categories_kb())

@router.callback_query(F.data.startswith("admin_del_prod_"))
async def admin_delete_product(callback: types.CallbackQuery):
    _, _, prod_id, cat_id = callback.data.split("_")
    delete_product(int(prod_id))
    await callback.answer("Товар удален.", show_alert=True)
    await callback.message.edit_text("📂 Товары в категории:", reply_markup=admin_category_view_kb(int(cat_id)))

# ========== ДОБАВЛЕНИЕ ТОВАРА (ВНУТРИ КАТЕГОРИИ) ==========
@router.callback_query(F.data.startswith("admin_add_prod_"))
async def add_product_start(callback: types.CallbackQuery, state: FSMContext):
    cat_id = int(callback.data.split("_")[3])
    await state.update_data(cat_id=cat_id)
    await callback.message.answer("Введите название товара:")
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
        data["cat_id"], data["name"], data["desc"], data["price"], 
        data["photo_id"], data["file_id"], data["file_type"], stock
    )
    await state.clear()
    await message.answer(f"✅ Товар «{data['name']}» добавлен!", reply_markup=admin_kb())
    await message.answer("📂 Товары в категории:", reply_markup=admin_category_view_kb(data["cat_id"]))

# ========== ОСТАЛЬНЫЕ ФУНКЦИИ (БАЛАНС, РАССЫЛКА, ТИКЕТЫ) ==========
@router.message(F.text == "💵 Выдать баланс", StateFilter("*"))
async def admin_give_balance_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await state.clear()
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
        await message.answer("Пользователь с таким ID не найден в базе.")
        await state.clear()
        return

    await state.update_data(target_id=target_id)
    await message.answer(f"Пользователь найден. Его баланс: {user[2]:.2f}$\nВведите сумму для выдачи:")
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
        f"✅ Баланс пользователя {target_id} пополнен на {amount:.2f}$.\n"
        f"Новый баланс: {updated_user[2]:.2f}$",
        reply_markup=admin_kb()
    )
    await state.clear()
    
    if bot:
        try:
            await bot.send_message(target_id, f"💰 Вам зачислен баланс: +{amount:.2f}$!\nТекущий баланс: {updated_user[2]:.2f}$")
        except:
            pass

@router.message(F.text == "📢 Рассылка", StateFilter("*"))
async def broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await state.clear()
    await message.answer("Введите текст для рассылки всем пользователям:")
    await state.set_state(AdminStates.waiting_broadcast)

@router.message(AdminStates.waiting_broadcast)
async def broadcast_send(message: types.Message, state: FSMContext):
    await state.clear()
    users = get_all_users()
    await message.answer(f"⏳ Начинаю фоновую рассылку для {len(users)} пользователей...", reply_markup=admin_kb())
    if bot:
        task = asyncio.create_task(process_broadcast(bot, message.text, message.from_user.id, users))
        from app.handlers.user import bg_tasks
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)

async def process_broadcast(bot_instance, text, admin_id, users):
    success, blocked, errors = 0, 0, 0
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

    report = f"✅ <b>Рассылка завершена!</b>\n\n📨 Всего: {len(users)}\n✅ Доставлено: {success}\n🚫 Блок: {blocked}\n⚠️ Ошибки: {errors}"
    try:
        await bot_instance.send_message(admin_id, report, parse_mode="HTML")
    except: pass

@router.message(F.text == "🎫 Тикеты", StateFilter("*"))
async def list_tickets(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    await state.clear()
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

@router.message(F.text == "🔙 Выйти из админки", StateFilter("*"))
async def exit_admin(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_kb())