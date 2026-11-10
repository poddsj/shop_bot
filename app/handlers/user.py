import asyncio
from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from app.states import UserStates
from app.keyboards import main_kb, catalog_kb
from app.database import (
    register_user, get_user, get_purchases, get_products, update_balance,
    add_purchase, create_ticket, create_payment, get_payment, complete_payment
)
from app.services.xrocket import create_xrocket_invoice, check_xrocket_payment
from app.config import ADMIN_IDS

router = Router()

# Хранилище для фоновых задач
bg_tasks = set()

# Передаем экземпляр бота для отправки сообщений из фоновых задач
# Примечание: лучше использовать middleware, но для простоты передадим глобально в main.py
from aiogram import Bot
bot = None # будет установлен в main.py

@router.message(CommandStart())
async def start(message: types.Message):
    register_user(message.from_user.id, message.from_user.username or "unknown")
    await message.answer(
        "Добро пожаловать в магазин!\n\n"
        "🛍 Каталог — просмотр товаров\n"
        "👤 Профиль — баланс и история\n"
        "💰 Пополнить — через XRocket (от 1$)\n"
        "🆘 Поддержка — связь с админом",
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

@router.callback_query(F.data.startswith("buy_"))
async def buy_product(callback: types.CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    # Импортируем функцию работы с БД внутри или выносим в database
    from app.database import get_db
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = c.fetchone()
    conn.close()
    
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
        
    user = get_user(callback.from_user.id)
    if user[2] < product[3]:
        await callback.answer(
            f"Недостаточно средств!\nВаш баланс: {user[2]:.2f}$\nЦена: {product[3]:.2f}$",
            show_alert=True
        )
        return
        
    update_balance(callback.from_user.id, -product[3])
    add_purchase(callback.from_user.id, product[0], product[1], product[3])
    
    updated_user = get_user(callback.from_user.id)
    await callback.message.edit_text(
        f"✅ Покупка совершена!\n\n"
        f"Товар: {product[1]}\n"
        f"Цена: {product[3]:.2f}$\n"
        f"Остаток баланса: {updated_user[2]:.2f}$"
    )

@router.message(F.text == "💰 Пополнить")
async def topup(message: types.Message, state: FSMContext):
    await message.answer("Введите сумму пополнения в USD (минимум 1$):")
    await state.set_state(UserStates.waiting_topup_amount)

@router.message(UserStates.waiting_topup_amount)
async def process_topup(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        if amount < 1:
            await message.answer("Минимальная сумма — 1$. Попробуйте снова:")
            return
    except ValueError:
        await message.answer("Введите число (например: 5 или 10.5):")
        return
        
    await state.clear()
    wait_msg = await message.answer("⏳ Создаем счет для оплаты...")
    
    invoice_id, link = await create_xrocket_invoice(amount, message.from_user.id)
    
    if not invoice_id or not link:
        await wait_msg.edit_text("❌ Ошибка создания счёта. Попробуйте позже.")
        return
        
    create_payment(message.from_user.id, invoice_id, amount)
    
    await wait_msg.edit_text(
        f"💰 Счёт на {amount:.2f}$ создан!\n\n"
        f"👉 <a href='{link}'>Оплатить по ссылке</a>\n\n"
        f"После оплаты баланс пополнится автоматически (в течение 1–2 минут).",
        parse_mode="HTML"
    )
    
    task = asyncio.create_task(poll_payment(invoice_id, message.from_user.id, amount))
    bg_tasks.add(task)
    task.add_done_callback(bg_tasks.discard)

async def poll_payment(invoice_id, user_id, amount):
    for _ in range(360):
        await asyncio.sleep(5)
        status = await check_xrocket_payment(invoice_id)
        
        if status == "paid":
            payment = get_payment(invoice_id)
            if payment and payment[4] == "paid":
                return 
                
            complete_payment(invoice_id)
            update_balance(user_id, amount)
            
            user = get_user(user_id)
            if bot: # Проверка на случай, если бот не передан
                await bot.send_message(
                    user_id,
                    f"✅ Баланс пополнен на {amount:.2f}$!\nТекущий баланс: {user[2]:.2f}$"
                )
            return
            
        elif status in ("expired", "cancelled"):
            if bot:
                await bot.send_message(user_id, "❌ Время ожидания оплаты истекло. Создайте новый счёт.")
            return
            
    if bot:
        await bot.send_message(user_id, "⏰ Время ожидания оплаты истекло. Если вы оплатили — обратитесь в поддержку.")

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