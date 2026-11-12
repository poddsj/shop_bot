from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from app.database import get_categories, get_products, get_admin_products

def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛍 Каталог"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="💰 Пополнить"), KeyboardButton(text="🆘 Поддержка")],
        [KeyboardButton(text="📦 Мои покупки")]
    ], resize_keyboard=True)

def admin_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📂 Просмотр каталога"), KeyboardButton(text="💵 Выдать баланс")],
        [KeyboardButton(text="📢 Рассылка"), KeyboardButton(text="🎫 Тикеты")],
        [KeyboardButton(text="🔙 Выйти из админки")]
    ], resize_keyboard=True)

def privacy_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я согласен с политикой", callback_data="accept_privacy")]
    ])

def payment_kb(invoice_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_pay_{invoice_id}")]
    ])

# === АДМИН КАТЕГОРИИ ===
def admin_categories_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    kb.inline_keyboard.append([InlineKeyboardButton(text="➕ Добавить категорию", callback_data="admin_add_cat")])
    
    categories = get_categories()
    for cat in categories:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"📁 {cat[1]}", callback_data=f"admin_cat_{cat[0]}")])
    return kb

def admin_category_view_kb(category_id):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    kb.inline_keyboard.append([InlineKeyboardButton(text="➕ Добавить товар", callback_data=f"admin_add_prod_{category_id}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🗑 Удалить категорию", callback_data=f"admin_del_cat_{category_id}")])
    
    products = get_admin_products(category_id)
    for p in products:
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"❌ {p[2]}", callback_data=f"admin_del_prod_{p[0]}_{category_id}")
        ])
        
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back_cats")])
    return kb

# === КЛИЕНТ КАТЕГОРИИ ===
def client_categories_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    categories = get_categories()
    for cat in categories:
        if get_products(cat[0]): 
            kb.inline_keyboard.append([InlineKeyboardButton(text=f"📁 {cat[1]}", callback_data=f"user_cat_{cat[0]}")])
    return kb

def client_products_kb(category_id):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    products = get_products(category_id)
    for p in products:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{p[2]} — {p[4]}$", callback_data=f"view_{p[0]}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="user_back_cats")])
    return kb