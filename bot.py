# bot.py — магазин с каталогом, балансом, XRocket (Invoices), тикетами и админкой

import asyncio
import sqlite3
import aiohttp
import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# ========== ЗАГРУЗКА СЕКРЕТОВ ИЗ .env ==========
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
XROCKET_API_KEY = os.getenv("XROCKET_API_KEY")
XROCKET_API_URL = os.getenv("XROCKET_API_URL", "https://pay.api.xrocket.exchange/api/v1")
DB_PATH = os.getenv("DB_PATH", "shop.db")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")
if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS не задан в .env")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Хранилище для фоновых задач
bg_tasks = set()

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 0,
        registered_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        price REAL,
        photo_url TEXT,
        stock INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        product_id INTEGER,
        product_name TEXT,
        price REAL,
        purchased_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        message TEXT,
        status TEXT DEFAULT 'open',
        admin_reply TEXT,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        invoice_id TEXT,
        amount REAL,
        status TEXT DEFAULT 'pending',
        created_at TEXT
    )""")
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect(DB_PATH)

def register_user(user_id, username):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, registered_at) VALUES (?, ?, ?)",
              (user_id, username, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def update_balance(user_id, amount):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_products():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE stock > 0")
    rows = c.fetchall()
    conn.close()
    return rows

def add_product(name, description, price, photo_url, stock):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO products (name, description, price, photo_url, stock) VALUES (?, ?, ?, ?, ?)",
              (name, description, price, photo_url, stock))
    conn.commit()
    conn.close()

def get_purchases(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM purchases WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def add_purchase(user_id, product_id, product_name, price):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO purchases (user_id, product_id, product_name, price, purchased_at) VALUES (?, ?, ?, ?, ?)",
              (user_id, product_id, product_name, price, datetime.now().isoformat()))
    c.execute("UPDATE products SET stock = stock - 1 WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()

def create_ticket(user_id, message):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO tickets (user_id, message, created_at) VALUES (?, ?, ?)",
              (user_id, message, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_tickets(status='open'):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM tickets WHERE status = ? ORDER BY id DESC", (status,))
    rows = c.fetchall()
    conn.close()
    return rows

def reply_ticket(ticket_id, reply):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE tickets SET admin_reply = ?, status = 'closed' WHERE id = ?", (reply, ticket_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def create_payment(user_id, invoice_id, amount):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO payments (user_id, invoice_id, amount, created_at) VALUES (?, ?, ?, ?)",
              (user_id, invoice_id, amount, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_payment(invoice_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM payments WHERE invoice_id = ?", (invoice_id,))
    row = c.fetchone()
    conn.close()
    return row

def complete_payment(invoice_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE payments SET status = 'paid' WHERE invoice_id = ?", (invoice_id,))
    conn.commit()
    conn.close()

# ========== СОСТОЯНИЯ FSM ==========
class AdminStates(StatesGroup):
    waiting_product_name = State()
    waiting_product_desc = State()
    waiting_product_price = State()
    waiting_product_photo = State()
    waiting_product_stock = State()
    waiting_broadcast = State()
    waiting_ticket_reply = State()
    waiting_balance_user_id = State() # Новое состояние
    waiting_balance_amount = State()  # Новое состояние

class UserStates(StatesGroup):
    waiting_support = State()
    waiting_topup_amount = State()

# ========== КЛАВИАТУРЫ ==========
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛍 Каталог"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="💰 Пополнить"), KeyboardButton(text="🆘 Поддержка")],
        [KeyboardButton(text="📦 Мои покупки")]
    ], resize_keyboard=True)

def admin_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Добавить товар"), KeyboardButton(text="📢 Рассылка")],
        [KeyboardButton(text="💵 Выдать баланс"), KeyboardButton(text="🎫 Тикеты")],
        [KeyboardButton(text="🔙 Выйти из админки")]
    ], resize_keyboard=True)

def catalog_kb(products):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for p in products:
        kb.inline_keyboard.append([InlineKeyboardButton(
            text=f"{p[1]} — {p[3]}$",
            callback_data=f"buy_{p[0]}"
        )])
    return kb

# ========== XROCKET API ==========
async def create_xrocket_invoice(amount, user_id):
    url = f"{XROCKET_API_URL}/invoices"
    
    headers = {
        "Authorization": f"Bearer {XROCKET_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "priceAmount": f"{amount:.2f}",
        "priceCurrency": "USDT", 
        "payCurrencies": ["USDT"],
        "numPayments": 1,
        "clientInvoiceId": f"user_{user_id}_{int(datetime.now().timestamp())}",
        "description": f"Top-up for user {user_id}",
        "expiresIn": 1800000
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            try:
                data = await resp.json()
            except Exception:
                return None, None

            if resp.status in (200, 201):
                inv_id = data.get("id") or data.get("data", {}).get("id")
                links = data.get("links") or data.get("data", {}).get("links", {})
                
                pay_link = links.get("telegramBotLink") or links.get("web_url") or links.get("pay_url")
                
                return inv_id, pay_link
            else:
                logging.error(f"XRocket Create Error: {resp.status} - {data}")
                return None, None

async def check_xrocket_payment(invoice_id):
    url = f"{XROCKET_API_URL}/invoices/{invoice_id}"
    headers = {"Authorization": f"Bearer {XROCKET_API_KEY}"}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                status = data.get("status") or data.get("data", {}).get("status")
                return status
            return None

# ========== ОБРАБОТЧИКИ ==========
@dp.message(CommandStart())
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

@dp.message(F.text == "👤 Профиль")
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

@dp.message(F.text == "📦 Мои покупки")
async def my_purchases(message: types.Message):
    purchases = get_purchases(message.from_user.id)
    if not purchases:
        await message.answer("У вас пока нет покупок.")
        return
    text = "📦 История покупок:\n\n" + "\n".join(
        [f"• {p[3]} — {p[4]}$ ({p[5][:16]})" for p in purchases]
    )
    await message.answer(text)

@dp.message(F.text == "🛍 Каталог")
async def catalog(message: types.Message):
    products = get_products()
    if not products:
        await message.answer("Каталог пуст. Загляните позже!")
        return
    await message.answer("🛍 Выберите товар:", reply_markup=catalog_kb(products))

@dp.callback_query(F.data.startswith("buy_"))
async def buy_product(callback: types.CallbackQuery):
    product_id = int(callback.data.split("_")[1])
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

@dp.message(F.text == "💰 Пополнить")
async def topup(message: types.Message, state: FSMContext):
    await message.answer("Введите сумму пополнения в USD (минимум 1$):")
    await state.set_state(UserStates.waiting_topup_amount)

@dp.message(UserStates.waiting_topup_amount)
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
            await bot.send_message(
                user_id,
                f"✅ Баланс пополнен на {amount:.2f}$!\nТекущий баланс: {user[2]:.2f}$"
            )
            return
            
        elif status in ("expired", "cancelled"):
            await bot.send_message(user_id, "❌ Время ожидания оплаты истекло. Создайте новый счёт.")
            return
            
    await bot.send_message(user_id, "⏰ Время ожидания оплаты истекло. Если вы оплатили — обратитесь в поддержку.")

@dp.message(F.text == "🆘 Поддержка")
async def support(message: types.Message, state: FSMContext):
    await message.answer("Опишите вашу проблему — админ ответит вам в этом чате:")
    await state.set_state(UserStates.waiting_support)

@dp.message(UserStates.waiting_support)
async def process_support(message: types.Message, state: FSMContext):
    create_ticket(message.from_user.id, message.text)
    await state.clear()
    await message.answer("✅ Обращение отправлено! Админ ответит вам здесь.", reply_markup=main_kb())
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"🎫 Новый тикет от @{message.from_user.username or message.from_user.id}:\n\n{message.text}")
        except:
            pass

# ========== АДМИН-ПАНЕЛЬ ==========
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer("🔧 Админ-панель:", reply_markup=admin_kb())

@dp.message(F.text == "➕ Добавить товар")
async def add_product_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Введите название товара:")
    await state.set_state(AdminStates.waiting_product_name)

@dp.message(AdminStates.waiting_product_name)
async def add_product_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите описание товара:")
    await state.set_state(AdminStates.waiting_product_desc)

@dp.message(AdminStates.waiting_product_desc)
async def add_product_desc(message: types.Message, state: FSMContext):
    await state.update_data(desc=message.text)
    await message.answer("Введите цену в USD (например: 9.99):")
    await state.set_state(AdminStates.waiting_product_price)

@dp.message(AdminStates.waiting_product_price)
async def add_product_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Введите число:")
        return
    await state.update_data(price=price)
    await message.answer("Введите URL фото товара (или напишите 'нет'):")
    await state.set_state(AdminStates.waiting_product_photo)

@dp.message(AdminStates.waiting_product_photo)
async def add_product_photo(message: types.Message, state: FSMContext):
    photo = None if message.text.lower() == "нет" else message.text
    await state.update_data(photo=photo)
    await message.answer("Введите количество на складе:")
    await state.set_state(AdminStates.waiting_product_stock)

@dp.message(AdminStates.waiting_product_stock)
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

# ========== ВЫДАЧА БАЛАНСА АДМИНОМ ==========
@dp.message(F.text == "💵 Выдать баланс")
async def admin_give_balance_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Введите Telegram ID пользователя, которому нужно выдать баланс:")
    await state.set_state(AdminStates.waiting_balance_user_id)

@dp.message(AdminStates.waiting_balance_user_id)
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

@dp.message(AdminStates.waiting_balance_amount)
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
    
    # Уведомляем пользователя (опционально)
    try:
        await bot.send_message(target_id, f"💰 Вам зачислен баланс: +{amount:.2f}$!\nТекущий баланс: {updated_user[2]:.2f}$")
    except:
        pass

# ========== ОСТАЛЬНАЯ АДМИНКА ==========
@dp.message(F.text == "📢 Рассылка")
async def broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Введите текст для рассылки всем пользователям:")
    await state.set_state(AdminStates.waiting_broadcast)

@dp.message(AdminStates.waiting_broadcast)
async def broadcast_send(message: types.Message, state: FSMContext):
    await state.clear()
    users = get_all_users()
    success = 0
    await message.answer(f"⏳ Начинаю рассылку для {len(users)} пользователей...")
    for uid in users:
        try:
            await bot.send_message(uid, message.text)
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await message.answer(f"✅ Рассылка завершена. Доставлено: {success}/{len(users)}", reply_markup=admin_kb())

@dp.message(F.text == "🎫 Тикеты")
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

@dp.callback_query(F.data.startswith("reply_"))
async def reply_ticket_start(callback: types.CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split("_")[1])
    await state.update_data(ticket_id=ticket_id)
    await callback.message.answer("Введите ответ для пользователя:")
    await state.set_state(AdminStates.waiting_ticket_reply)

@dp.message(AdminStates.waiting_ticket_reply)
async def reply_ticket_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data["ticket_id"]
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM tickets WHERE id = ?", (ticket_id,))
    user_id = c.fetchone()[0]
    conn.close()
    reply_ticket(ticket_id, message.text)
    await bot.send_message(user_id, f"📩 Ответ поддержки:\n\n{message.text}")
    await message.answer("✅ Ответ отправлен.", reply_markup=admin_kb())
    await state.clear()

@dp.message(F.text == "🔙 Выйти из админки")
async def exit_admin(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_kb())

# ========== ЗАПУСК ==========
async def main():
    init_db()
    print("[*] Бот запущен и готов к работе")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен")