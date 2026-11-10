import asyncio
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.states import AdminStates
from app.keyboards import admin_kb, main_kb
from app.database import (
    get_user, update_balance, add_product, get_tickets, 
    reply_ticket, get_all_users, get_db
)
from app.config import ADMIN_IDS

router = Router()

from aiogram import Bot
bot = None

@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer("🔧 Админ-панель:", reply_markup=admin_kb())

@router.message(F.text == "➕ Добавить товар")
async def add_product_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Введите название товара:")
    await state.set_state(AdminStates.waiting_product_name)

@router.message(AdminStates.waiting_product_name)
async def add_product_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите описание товара:")
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
    await message.answer("Введите URL фото товара (или напишите 'нет'):")
    await state.set_state(AdminStates.waiting_product_photo)

@router.message(AdminStates.waiting_product_photo)
async def add_product_photo(message: types.Message, state: FSMContext):
    photo = None if message.text.lower() == "нет" else message.text
    await state.update_data(photo=photo)
    await message.answer("Введите количество на складе:")
    await state.set_state(AdminStates.waiting_product_stock)

@router.message(AdminStates.waiting_product_stock)
async def add_product_stock(message: types.Message, state: FSMContext):
    try:
        stock = int(message.text)
    except ValueError:
        await message.answer("Введите целое число:")
        return
    data = await state.get_data()
    add_product(data["name"], data["desc"], data["price"], data["photo"], stock)
    await state.clear()
    await message.answer(f"✅ Товар «{data['name']}» добавлен!", reply_markup=admin_kb())

@router.message(F.text == "💵 Выдать баланс")
async def admin_give_balance_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
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
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Введите текст для рассылки всем пользователям:")
    await state.set_state(AdminStates.waiting_broadcast)

@router.message(AdminStates.waiting_broadcast)
async def broadcast_send(message: types.Message, state: FSMContext):
    await state.clear()
    users = get_all_users()
    success = 0
    await message.answer(f"⏳ Начинаю рассылку для {len(users)} пользователей...")
    
    if bot:
        for uid in users:
            try:
                await bot.send_message(uid, message.text)
                success += 1
                await asyncio.sleep(0.05)
            except:
                pass
    await message.answer(f"✅ Рассылка завершена. Доставлено: {success}/{len(users)}", reply_markup=admin_kb())

@router.message(F.text == "🎫 Тикеты")
async def list_tickets(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
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