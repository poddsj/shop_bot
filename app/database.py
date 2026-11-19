import sqlite3
import os
import math
from datetime import datetime
from app.config import DB_PATH

def init_db():
    db_path = DB_PATH if DB_PATH else "data/shop.db"
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Добавлена колонка agreed_to_privacy
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0, 
        registered_at TEXT, agreed_to_privacy INTEGER DEFAULT 0
    )""")
    # Existing databases created before privacy consent was added need this column.
    user_columns = {row[1] for row in c.execute("PRAGMA table_info(users)").fetchall()}
    if "agreed_to_privacy" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN agreed_to_privacy INTEGER NOT NULL DEFAULT 0")

    c.execute("""CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER, name TEXT, description TEXT, price REAL, 
        photo_id TEXT, file_id TEXT, file_type TEXT, stock INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER, 
        product_name TEXT, price REAL, purchased_at TEXT,
        delivery_status TEXT NOT NULL DEFAULT 'delivered'
    )""")
    # Migrate existing installations without changing historical purchases.
    purchase_columns = {row[1] for row in c.execute("PRAGMA table_info(purchases)").fetchall()}
    if "delivery_status" not in purchase_columns:
        c.execute("ALTER TABLE purchases ADD COLUMN delivery_status TEXT NOT NULL DEFAULT 'delivered'")
    c.execute("""CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, message TEXT, 
        status TEXT DEFAULT 'open', admin_reply TEXT, created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, invoice_id TEXT, 
        client_invoice_id TEXT, amount REAL, status TEXT DEFAULT 'pending', created_at TEXT
    )""")
    # Enforce uniqueness for new invoices, but keep old databases with historical
    # duplicates usable; settlement also handles identical legacy duplicates safely.
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_invoice_id ON payments(invoice_id)")
    except sqlite3.IntegrityError:
        pass
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_client_invoice_id ON payments(client_invoice_id)")
    except sqlite3.IntegrityError:
        pass
    
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect(DB_PATH if DB_PATH else "data/shop.db")

def register_user(user_id, username):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, registered_at) VALUES (?, ?, ?)",
              (user_id, username, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def check_privacy_agreement(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT agreed_to_privacy FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row or row[0] == 0:
        return False
    return True

def agree_to_privacy(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET agreed_to_privacy = 1 WHERE user_id = ?", (user_id,))
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

# ================= КАТЕГОРИИ =================
def add_category(name):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO categories (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()

def get_categories():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM categories")
    rows = c.fetchall()
    conn.close()
    return rows

def delete_category(category_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE category_id = ?", (category_id,))
    c.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.commit()
    conn.close()

# ================= ТОВАРЫ =================
def get_products(category_id=None):
    conn = get_db()
    c = conn.cursor()
    if category_id:
        c.execute("SELECT * FROM products WHERE category_id = ? AND stock > 0", (category_id,))
    else:
        c.execute("SELECT * FROM products WHERE stock > 0")
    rows = c.fetchall()
    conn.close()
    return rows

def get_admin_products(category_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE category_id = ?", (category_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def add_product(category_id, name, description, price, photo_id, file_id, file_type, stock):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO products (category_id, name, description, price, photo_id, file_id, file_type, stock) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (category_id, name, description, price, photo_id, file_id, file_type, stock))
    conn.commit()
    conn.close()

def delete_product(product_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()

# ================= ПОКУПКИ И ТИКЕТЫ =================
def get_purchases(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM purchases WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def purchase_product(user_id, product_id):
    """Atomically check stock/balance, debit the user, and record a purchase."""
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        c = conn.cursor()
        c.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        product = c.fetchone()
        if not product or product[8] is None or product[8] <= 0:
            conn.rollback()
            return "out_of_stock", None, None

        price = product[4]
        # Never allow malformed legacy rows (NULL, negative, NaN/inf) to debit balances.
        if price is None or not math.isfinite(float(price)) or float(price) <= 0:
            conn.rollback()
            return "invalid_product", product, None
        c.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
            (price, user_id, price),
        )
        if c.rowcount != 1:
            conn.rollback()
            return "insufficient_funds", product, None

        c.execute("UPDATE products SET stock = stock - 1 WHERE id = ? AND stock > 0", (product_id,))
        if c.rowcount != 1:
            conn.rollback()
            return "out_of_stock", product, None

        c.execute(
            "INSERT INTO purchases (user_id, product_id, product_name, price, purchased_at, delivery_status) VALUES (?, ?, ?, ?, ?, 'pending')",
            (user_id, product[0], product[2], price, datetime.now().isoformat()),
        )
        purchase_id = c.lastrowid
        conn.commit()
        return "ok", product, purchase_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def mark_purchase_delivered(purchase_id):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("UPDATE purchases SET delivery_status = 'delivered' WHERE id = ? AND delivery_status = 'pending'", (purchase_id,))
        conn.commit()
        return c.rowcount == 1
    finally:
        conn.close()


def refund_undelivered_purchase(purchase_id):
    """Refund once and restore stock when delivery failed."""
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        c = conn.cursor()
        c.execute("SELECT user_id, product_id, price FROM purchases WHERE id = ? AND delivery_status = 'pending'", (purchase_id,))
        purchase = c.fetchone()
        if not purchase:
            conn.rollback()
            return False
        user_id, product_id, price = purchase
        c.execute("UPDATE purchases SET delivery_status = 'refunded' WHERE id = ? AND delivery_status = 'pending'", (purchase_id,))
        if c.rowcount != 1:
            conn.rollback()
            return False
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (price, user_id))
        if c.rowcount != 1:
            conn.rollback()
            raise ValueError(f"Purchase {purchase_id} references a missing user")
        c.execute("UPDATE products SET stock = stock + 1 WHERE id = ?", (product_id,))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
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

# ================= ПЛАТЕЖИ =================
def create_payment(user_id, invoice_id, client_invoice_id, amount):
    """Persist a payment only when its identifiers and positive amount are valid."""
    if not invoice_id or not client_invoice_id:
        raise ValueError("Payment invoice identifiers must not be empty")
    amount = float(amount)
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("Payment amount must be finite and positive")
    conn = get_db()
    try:
        conn.execute("INSERT INTO payments (user_id, invoice_id, client_invoice_id, amount, created_at) VALUES (?, ?, ?, ?, ?)",
                     (user_id, str(invoice_id), str(client_invoice_id), amount, datetime.now().isoformat()))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_payment(invoice_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM payments WHERE invoice_id = ? ORDER BY id DESC LIMIT 1", (str(invoice_id),))
    row = c.fetchone()
    conn.close()
    return row

def settle_payment(invoice_id):
    """Mark one pending invoice paid and credit its user exactly once."""
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        c = conn.cursor()
        c.execute(
            "SELECT id, user_id, amount FROM payments WHERE invoice_id = ? AND status = 'pending' ORDER BY id LIMIT 1",
            (str(invoice_id),),
        )
        payment = c.fetchone()
        if not payment:
            conn.rollback()
            return None

        payment_id, user_id, amount = payment
        # If a legacy database already contains duplicate rows for one invoice,
        # settle all of them together so later polling cannot credit it again.
        c.execute(
            "UPDATE payments SET status = 'paid' WHERE invoice_id = ? AND status = 'pending'",
            (str(invoice_id),),
        )
        if c.rowcount < 1:
            conn.rollback()
            return None
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        if c.rowcount != 1:
            conn.rollback()
            raise ValueError(f"Payment {invoice_id} references a missing user")
        conn.commit()
        return user_id, amount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()