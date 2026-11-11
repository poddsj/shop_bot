from aiogram.fsm.state import State, StatesGroup

class AdminStates(StatesGroup):
    waiting_category_name = State() # Новое
    waiting_product_name = State()
    waiting_product_desc = State()
    waiting_product_price = State()
    waiting_product_stock = State()
    waiting_product_photo = State()
    waiting_product_file = State()
    waiting_broadcast = State()
    waiting_ticket_reply = State()
    waiting_balance_user_id = State()
    waiting_balance_amount = State()

class UserStates(StatesGroup):
    waiting_support = State()
    waiting_topup_amount = State()