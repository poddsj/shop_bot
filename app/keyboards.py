from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

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
        # callback_data изменен с buy_ на view_
        kb.inline_keyboard.append([InlineKeyboardButton(
            text=f"{p[1]} — {p[3]}$",
            callback_data=f"view_{p[0]}"
        )])
    return kb

def payment_kb(invoice_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_pay_{invoice_id}")]
    ])