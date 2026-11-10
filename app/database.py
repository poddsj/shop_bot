import sqlite3
import os
from datetime import datetime
from app.config import DB_PATH

def init_db():
    db_path = DB_PATH if DB_PATH else "data/shop.db"
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 0,
        registered_at TEXT
    )""")
    
    # УДАЛЯЕМ СТАРУЮ ТАБЛИЦУ ТОВАРОВ (так как изменилась структура)
    c.execute("DROP TABLE IF EXISTS products")
    
    # Новая таблица товаров
    c.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        description TEXT,
        price REAL,
        photo_id TEXT,
        file_id TEXT,
        file_type TEXT,
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
    return sqlite3.connect(DB_PATH if DB_PATH else "data/shop.db")

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

def add_product(name, description, price, photo_id, file_id, file_type, stock):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO products (name, description, price, photo_id, file_id, file_type, stock) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (name, description, price, photo_id, file_id, file_type, stock))
    conn.commit()
    conn.close()

def delete_product(product_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = ?", (product_id,))
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