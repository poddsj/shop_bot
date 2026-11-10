import asyncio
from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.states import UserStates
from app.keyboards import main_kb, catalog_kb, payment_kb  # Добавили payment_kb
from app.database import (
    register_user, get_user, get_purchases, get_products, update_balance,
    add_purchase, create_ticket, create_payment, get_payment, complete_payment, get_db
)
from app.services.xrocket import create_xrocket_invoice, check_xrocket_payment
from app.config import ADMIN_IDS

router = Router()
bot = None
bg_tasks = set()

@router.message(CommandStart())
async def start(message: types.Message):
    register_user(message.from_user.id, message.from_user.username or "unknown")
    await message.answer(
        "Добро пожаловать в Trinadtac Shop!\n\n"
        "🛍 Каталог — просмотр товаров\n"
        "👤 Профиль — баланс и история",
        reply_markup=main_kb()
    )

@router.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Ошибка: пользователь не найден.")
        return
    purchases = get_purchases(message.from_user.id)
    history = "\n".join([f"• {p[3]} — {p[4]}$ ({p[5][:10]})" for p in purchases[:10]]) or "Покупок пока нет"
    await message.answer(
        f"👤 Ваш профиль\n\n"
        f"ID: {user[0]}\n"
        f"Username: @{user[1] or 'не указан'}\n"
        f"💰 Баланс: {user[2]:.2f} $\n\n"
        f"📦 Последние покупки:\n{history}",
        reply_markup=main_kb()
    )

@router.message(F.text == "📦 Мои покупки")
async def my_purchases(message: types.Message):
    purchases = get_purchases(message.from_user.id)
    if not purchases:
        await message.answer("У вас пока нет покупок.")
        return
    text = "📦 История покупок:\n\n" + "\n".join(
        [f"• {p[3]} — {p[4]}$ ({p[5][:16]})" for p in purchases]
    )
    await message.answer(text)

@router.message(F.text == "🛍 Каталог")
async def catalog(message: types.Message):
    products = get_products()
    if not products:
        await message.answer("Каталог пуст. Загляните позже!")
        return
    await message.answer("🛍 Выберите товар:", reply_markup=catalog_kb(products))

@router.callback_query(F.data.startswith("view_"))
async def view_product(callback: types.CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = c.fetchone()
    conn.close()

    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return

    text = f"📦 {product[1]}\n\n{product[2]}\n\n💰 Цена: {product[3]:.2f}$\n📊 В наличии: {product[7]} шт."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Купить", callback_data=f"confirm_buy_{product_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_view")]
    ])

    if product[4]: 
        await callback.message.answer_photo(photo=product[4], caption=text, reply_markup=kb)
        await callback.message.delete()
    else:
        await callback.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "cancel_view")
async def cancel_view(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Вы вернулись в меню.", reply_markup=main_kb())

@router.callback_query(F.data.startswith("confirm_buy_"))
async def confirm_buy(callback: types.CallbackQuery):
    product_id = int(callback.data.split("_")[2])
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = c.fetchone()
    conn.close()

    user = get_user(callback.from_user.id)
    
    if not product or product[7] <= 0:
        await callback.answer("Товара нет в наличии!", show_alert=True)
        return
    if user[2] < product[3]:
        await callback.answer(f"Недостаточно средств!\nВаш баланс: {user[2]:.2f}$\nЦена: {product[3]:.2f}$", show_alert=True)
        return

    update_balance(callback.from_user.id, -product[3])
    add_purchase(callback.from_user.id, product[0], product[1], product[3])
    
    await callback.message.delete()
    
    if product[6] == "document":
        await bot.send_document(callback.from_user.id, document=product[5], caption=f"✅ Спасибо за покупку!\nТовар: {product[1]}")
    elif product[6] == "video":
        await bot.send_video(callback.from_user.id, video=product[5], caption=f"✅ Спасибо за покупку!\nТовар: {product[1]}")
    elif product[6] == "text":
        await bot.send_message(callback.from_user.id, f"✅ Спасибо за покупку!\n\nТовар: {product[1]}\n\nВаш товар:\n{product[5]}")

@router.message(F.text == "💰 Пополнить")
async def topup(message: types.Message, state: FSMContext):
    await message.answer("Введите сумму пополнения в USD (минимум 0.01$):")
    await state.set_state(UserStates.waiting_topup_amount)

@router.message(UserStates.waiting_topup_amount)
async def process_topup(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount < 0.01:
            await message.answer("Минимальная сумма — 0.01$. Попробуйте снова:")
            return
    except ValueError:
        await message.answer("Введите число (например: 0.5 или 10):")
        return
        
    await state.clear()
    wait_msg = await message.answer("⏳ Создаем счет для оплаты...")
    
    invoice_id, link = await create_xrocket_invoice(amount, message.from_user.id)
    
    if not invoice_id or not link:
        await wait_msg.edit_text("❌ Ошибка создания счёта. Попробуйте позже.")
        return
        
    create_payment(message.from_user.id, invoice_id, amount)
    
    # Отправляем ссылку и добавляем кнопку "Я оплатил"
    await wait_msg.edit_text(
        f"💰 Счёт на {amount:.2f}$ создан!\n\n"
        f"👉 <a href='{link}'>Оплатить по ссылке</a>\n\n"
        f"После оплаты нажмите кнопку ниже (или подождите 1-2 минуты).",
        parse_mode="HTML",
        reply_markup=payment_kb(invoice_id)
    )
    
    task = asyncio.create_task(poll_payment(invoice_id, message.from_user.id, amount))
    bg_tasks.add(task)
    task.add_done_callback(bg_tasks.discard)

@router.callback_query(F.data.startswith("check_pay_"))
async def manual_check_payment(callback: types.CallbackQuery):
    invoice_id = callback.data.split("_")[2]
    
    # Отвечаем сразу, чтобы кнопка не висела (не более 3 сек)
    await callback.answer("Проверяем...")
    
    payment = get_payment(invoice_id)
    if payment and payment[4] == "paid":
        await callback.message.delete()
        await callback.message.answer("✅ Этот платёж уже был зачислен ранее!", reply_markup=main_kb())
        return

    # Опрашиваем API 5 раз (ждем 10 секунд)
    status = "unknown"
    for _ in range(5):
        status = await check_xrocket_payment(invoice_id)
        if status == "paid":
            break
        await asyncio.sleep(2)
        
    if status == "paid":
        amount = payment[3] if payment else 0
        user_id = payment[1] if payment else 0
        
        complete_payment(invoice_id)
        update_balance(user_id, amount)
        
        user = get_user(user_id)
        await callback.message.delete()
        await bot.send_message(
            user_id,
            f"✅ Оплата подтверждена! Баланс пополнен на {amount:.2f}$.\nТекущий баланс: {user[2]:.2f}$",
            reply_markup=main_kb()
        )
    else:
        # Отправляем ОБЫЧНОЕ СООБЩЕНИЕ, а не всплывающее окно
        await callback.message.answer(
            f"❌ Оплата пока не найдена.\nСтатус от xRocket: <code>{status}</code>\n\n"
            f"Если вы точно оплатили, подождите 1-2 минуты. Бот сам пришлет уведомление, когда платеж пройдет.",
            parse_mode="HTML"
        )


# ЕДИНАЯ ЛОГИКА ЗАЧИСЛЕНИЯ (ДЛЯ ТАЙМЕРА)
async def process_successful_payment(invoice_id, user_id, amount):
    payment = get_payment(invoice_id)
    if payment and payment[4] == "paid":
        return # Уже зачислено
        
    complete_payment(invoice_id)
    update_balance(user_id, amount)
    
    user = get_user(user_id)
    if bot:
        await bot.send_message(
            user_id,
            f"✅ Баланс пополнен на {amount:.2f}$!\nТекущий баланс: {user[2]:.2f}$"
        )

async def poll_payment(invoice_id, user_id, amount):
    for _ in range(360):
        await asyncio.sleep(5)
        status = await check_xrocket_payment(invoice_id)
        
        if status == "paid":
            await process_successful_payment(invoice_id, user_id, amount)
            return
        elif status in ("expired", "cancelled"):
            if bot:
                await bot.send_message(user_id, "❌ Время ожидания оплаты истекло. Создайте новый счёт.")
            return
            
    if bot:
        await bot.send_message(user_id, "⏰ Время ожидания оплаты истекло. Если вы оплатили — нажмите 'Я оплатил' или обратитесь в поддержку.")

@router.message(F.text == "🆘 Поддержка")
async def support(message: types.Message, state: FSMContext):
    await message.answer("Опишите вашу проблему — админ ответит вам в этом чате:")
    await state.set_state(UserStates.waiting_support)

@router.message(UserStates.waiting_support)
async def process_support(message: types.Message, state: FSMContext):
    create_ticket(message.from_user.id, message.text)
    await state.clear()
    await message.answer("✅ Обращение отправлено! Админ ответит вам здесь.", reply_markup=main_kb())
    if bot:
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, f"🎫 Новый тикет от @{message.from_user.username or message.from_user.id}:\n\n{message.text}")
            except:
                pass