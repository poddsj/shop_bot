import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
XROCKET_API_KEY = os.getenv("XROCKET_API_KEY")
XROCKET_API_URL = os.getenv("XROCKET_API_URL", "https://pay.api.xrocket.exchange/api/v1")
# Сохраняем БД в папку data
DB_PATH = os.getenv("DB_PATH", "data/shop.db")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")
if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS не задан в .env")