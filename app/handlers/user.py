import asyncio
import html
import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from aiogram import Router, types, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.states import UserStates
from app.keyboards import main_kb, payment_kb, client_categories_kb, client_products_kb, privacy_kb
from app.database import (
    register_user, get_user, get_purchases, get_products,
    purchase_product, mark_purchase_delivered, refund_undelivered_purchase, create_ticket, create_payment, get_payment, settle_payment, get_db,
    check_privacy_agreement, agree_to_privacy
)
from app.services.xrocket import create_xrocket_invoice, check_xrocket_payment
from app.config import ADMIN_IDS, PRIVACY_POLICY

router = Router()
bot = None
bg_tasks = set()

@router.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    register_user(message.from_user.id, message.from_user.username or "unknown")
    
    if not check_privacy_agreement(message.from_user.id):
        await message.answer(
            PRIVACY_POLICY,
            parse_mode="HTML",
            reply_markup=privacy_kb()
        )
    else:
        await message.answer(
            '<tg-emoji emoji-id="5345827101910016551">👋</tg-emoji> Добро пожаловать в магазин!\n\n'
            '<tg-emoji emoji-id="5348473175426508545">🛍</tg-emoji> Каталог — просмотр товаров\n'
            '<tg-emoji emoji-id="5348085180965888383">👤</tg-emoji> Профиль — баланс и история',
            parse_mode="HTML",
            reply_markup=main_kb()
        )

@router.callback_query(F.data == "accept_privacy")
async def process_privacy_accept(callback: types.CallbackQuery, state: FSMContext):
    agree_to_privacy(callback.from_user.id)
    await callback.message.delete()
    await callback.message.answer(
        "✅ Спасибо! Вы успешно зарегистрированы.\n\n"
        "🛍 Каталог — просмотр товаров\n"
        "👤 Профиль — баланс и история",
        reply_markup=main_kb()
    )

# Проверка при нажатии на кнопки
@router.message(F.text == "👤 Профиль", StateFilter("*"))
async def profile(message: types.Message, state: FSMContext):
    if not check_privacy_agreement(message.from_user.id):
        return await message.answer("⚠️ Сначала примите политику.", reply_markup=privacy_kb())
    
    await state.clear()
    user = get_user(message.from_user.id)
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

@router.message(F.text == "📦 Мои покупки", StateFilter("*"))
async def my_purchases(message: types.Message, state: FSMContext):
    if not check_privacy_agreement(message.from_user.id):
        return await message.answer("⚠️ Сначала примите политику.", reply_markup=privacy_kb())
        
    await state.clear()
    purchases = get_purchases(message.from_user.id)
    if not purchases:
        await message.answer("У вас пока нет покупок.")
        return
    text = "📦 История покупок:\n\n" + "\n".join(
        [f"• {p[3]} — {p[4]}$ ({p[5][:16]})" for p in purchases]
    )
    await message.answer(text)

@router.message(F.text == "🛍 Каталог", StateFilter("*"))
async def catalog(message: types.Message, state: FSMContext):
    if not check_privacy_agreement(message.from_user.id):
        return await message.answer("⚠️ Сначала примите политику.", reply_markup=privacy_kb())
        
    await state.clear()
    kb = client_categories_kb()
    if not kb.inline_keyboard:
        await message.answer("Каталог пуст. Загляните позже!")
        return
    await message.answer("🛍 Выберите категорию:", reply_markup=kb)

# Коллбеки для каталога
@router.callback_query(F.data.startswith("user_cat_"))
async def user_open_category(callback: types.CallbackQuery):
    if not check_privacy_agreement(callback.from_user.id):
        await callback.answer("Сначала примите политику конфиденциальности.", show_alert=True)
        return
    try:
        cat_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("Некорректная категория", show_alert=True)
        return
    await callback.message.edit_text("🛍 Выберите товар:", reply_markup=client_products_kb(cat_id))

@router.callback_query(F.data == "user_back_cats")
async def user_back_categories(callback: types.CallbackQuery):
    if not check_privacy_agreement(callback.from_user.id):
        await callback.answer("Сначала примите политику конфиденциальности.", show_alert=True)
        return
    kb = client_categories_kb()
    if not kb.inline_keyboard:
        await callback.message.edit_text("Каталог пуст.")
    else:
        await callback.message.edit_text("🛍 Выберите категорию:", reply_markup=kb)

@router.callback_query(F.data.startswith("view_"))
async def view_product(callback: types.CallbackQuery):
    if not check_privacy_agreement(callback.from_user.id):
        await callback.answer("Сначала примите политику конфиденциальности.", show_alert=True)
        return
    try:
        product_id = int(callback.data.split("_")[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный товар", show_alert=True)
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = c.fetchone()
    conn.close()

    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return

    # Индексы: 0-id, 1-cat_id, 2-name, 3-desc, 4-price, 5-photo, 6-file, 7-type, 8-stock
    text = f"📦 {product[2]}\n\n{product[3]}\n\n💰 Цена: {product[4]:.2f}$\n📊 В наличии: {product[8]} шт."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Купить", callback_data=f"confirm_buy_{product_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_view")]
    ])

    if product[5]: # photo_id
        await callback.message.answer_photo(photo=product[5], caption=text, reply_markup=kb)
        await callback.message.delete()
    else:
        await callback.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "cancel_view")
async def cancel_view(callback: types.CallbackQuery):
    if not check_privacy_agreement(callback.from_user.id):
        await callback.answer("Сначала примите политику конфиденциальности.", show_alert=True)
        return
    await callback.message.delete()
    await callback.message.answer("Вы вернулись в меню.", reply_markup=main_kb())

@router.callback_query(F.data.startswith("confirm_buy_"))
async def confirm_buy(callback: types.CallbackQuery):
    if not check_privacy_agreement(callback.from_user.id):
        await callback.answer("Сначала примите политику конфиденциальности.", show_alert=True)
        return
    try:
        product_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("Некорректный товар", show_alert=True)
        return

    result, product, purchase_id = purchase_product(callback.from_user.id, product_id)
    if result == "out_of_stock":
        await callback.answer("Товара нет в наличии!", show_alert=True)
        return
    if result == "invalid_product":
        await callback.answer("У товара некорректная цена. Обратитесь в поддержку.", show_alert=True)
        return
    if result == "insufficient_funds":
        user = get_user(callback.from_user.id)
        balance = user[2] if user else 0
        await callback.answer(f"Недостаточно средств!\nВаш баланс: {balance:.2f}$\nЦена: {product[4]:.2f}$", show_alert=True)
        return

    await callback.answer("Покупка оформлена")
    try:
        await callback.message.delete()
    except Exception:
        pass

    try:
        if product[7] == "document":
            await bot.send_document(callback.from_user.id, document=product[6], caption=f"✅ Спасибо за покупку!\nТовар: {product[2]}")
        elif product[7] == "video":
            await bot.send_video(callback.from_user.id, video=product[6], caption=f"✅ Спасибо за покупку!\nТовар: {product[2]}")
        elif product[7] == "text":
            await bot.send_message(callback.from_user.id, f"✅ Спасибо за покупку!\n\nТовар: {product[2]}\n\nВаш товар:\n{product[6]}")
        else:
            raise ValueError(f"Unsupported product type: {product[7]}")
    except Exception:
        refunded = refund_undelivered_purchase(purchase_id)
        if refunded:
            await bot.send_message(
                callback.from_user.id,
                f"Не удалось выдать товар. Деньги возвращены на баланс, остаток восстановлен. ID покупки: {purchase_id}.",
            )
        else:
            await bot.send_message(
                callback.from_user.id,
                f"Покупка записана, но выдать товар не удалось автоматически. ID покупки: {purchase_id}. Обратитесь в поддержку.",
            )
        return

    mark_purchase_delivered(purchase_id)

@router.message(F.text == "💰 Пополнить", StateFilter("*"))
async def topup(message: types.Message, state: FSMContext):
    if not check_privacy_agreement(message.from_user.id):
        return await message.answer("⚠️ Сначала примите политику.", reply_markup=privacy_kb())
        
    await state.clear()
    await message.answer("Введите сумму пополнения в USD (минимум 1$):")
    await state.set_state(UserStates.waiting_topup_amount)

@router.message(UserStates.waiting_topup_amount)
async def process_topup(message: types.Message, state: FSMContext):
    try:
        decimal_amount = Decimal(message.text.replace(",", ".").strip()).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if not decimal_amount.is_finite() or decimal_amount < Decimal("1") or decimal_amount > Decimal("100000"):
            await message.answer("Введите сумму от 1$ до 100000$.")
            return
        amount = float(decimal_amount)
    except (InvalidOperation, ValueError, AttributeError):
        await message.answer("Введите число (например: 5 или 10):")
        return
        
    await state.clear()
    wait_msg = await message.answer("⏳ Создаем счет для оплаты...")
    
    invoice_id, client_inv_id, link = await create_xrocket_invoice(amount, message.from_user.id)
    
    if not invoice_id or not link:
        await wait_msg.edit_text("❌ Ошибка создания счёта. Попробуйте позже.")
        return
        
    try:
        create_payment(message.from_user.id, invoice_id, client_inv_id, amount)
    except Exception:
        logging.exception("Failed to save xRocket invoice %s", invoice_id)
        await wait_msg.edit_text("❌ Не удалось зарегистрировать счёт. Не оплачивайте его; повторите попытку позже.")
        return
    
    await wait_msg.edit_text(
        f"💰 Счёт на {amount:.2f}$ создан!\n\n"
        f"👉 <a href='{html.escape(str(link), quote=True)}'>Оплатить по ссылке</a>\n\n"
        f"После оплаты нажмите кнопку ниже (или подождите 1-2 минуты).",
        parse_mode="HTML",
        reply_markup=payment_kb(invoice_id)
    )
    
    task = asyncio.create_task(poll_payment(invoice_id, client_inv_id, message.from_user.id, amount))
    bg_tasks.add(task)
    task.add_done_callback(bg_tasks.discard)

# ... (функции check_pay и poll_payment остаются без изменений) ...

@router.callback_query(F.data.startswith("check_pay_"))
async def manual_check_payment(callback: types.CallbackQuery):
    if not check_privacy_agreement(callback.from_user.id):
        await callback.answer("Сначала примите политику конфиденциальности.", show_alert=True)
        return
    invoice_id = callback.data.removeprefix("check_pay_").strip()
    await callback.answer("Проверяем...")
    
    payment = get_payment(invoice_id)
    if not payment or payment[1] != callback.from_user.id:
        await callback.message.answer("❌ Платёж не найден.")
        return
        
    if payment[5] == "paid": 
        await callback.message.delete()
        await callback.message.answer("✅ Этот платёж уже был зачислен ранее!", reply_markup=main_kb())
        return

    client_inv_id = payment[3]
    
    status = "unknown"
    for _ in range(5):
        status = await check_xrocket_payment(invoice_id, client_inv_id)
        if status == "paid":
            break
        await asyncio.sleep(2)
        
    if status == "paid":
        amount = payment[4] 
        user_id = payment[1] 
        
        settled = settle_payment(invoice_id)
        if settled:
            user_id, amount = settled
            user = get_user(user_id)
            await callback.message.delete()
            await bot.send_message(
                user_id,
                f"✅ Оплата подтверждена! Баланс пополнен на {amount:.2f}$.\nТекущий баланс: {user[2]:.2f}$",
                reply_markup=main_kb()
            )
        else:
            await callback.answer("Платёж уже обработан", show_alert=True)
    else:
        await callback.message.answer(
            f"❌ Оплата пока не найдена.\nСтатус от xRocket: <code>{status}</code>\nID инвойса: <code>{invoice_id}</code>\n\n"
            f"Если вы точно оплатили, подождите 1-2 минуты.",
            parse_mode="HTML"
        )

async def poll_payment(invoice_id, client_inv_id, user_id, amount):
    for _ in range(360):
        await asyncio.sleep(5)
        status = await check_xrocket_payment(invoice_id, client_inv_id)
        
        if status == "paid":
            settled = settle_payment(invoice_id)
            if settled:
                settled_user_id, settled_amount = settled
                user = get_user(settled_user_id)
                if bot and user:
                    await bot.send_message(
                        settled_user_id,
                        f"✅ Баланс пополнен на {settled_amount:.2f}$!\nТекущий баланс: {user[2]:.2f}$",
                    )
            return
            
        elif status in ("expired", "cancelled"):
            if bot:
                await bot.send_message(user_id, "❌ Время ожидания оплаты истекло. Создайте новый счёт.")
            return
            
    if bot:
        await bot.send_message(user_id, "⏰ Время ожидания оплаты истекло. Если вы оплатили — обратитесь в поддержку.")

@router.message(F.text == "🆘 Поддержка", StateFilter("*"))
async def support(message: types.Message, state: FSMContext):
    if not check_privacy_agreement(message.from_user.id):
        return await message.answer("⚠️ Сначала примите политику.", reply_markup=privacy_kb())
        
    await state.clear()
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