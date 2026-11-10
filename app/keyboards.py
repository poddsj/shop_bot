from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛍 Каталог"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="💰 Пополнить"), KeyboardButton(text="🆘 Поддержка")],
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