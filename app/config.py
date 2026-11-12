import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
XROCKET_API_KEY = os.getenv("XROCKET_API_KEY")
XROCKET_API_URL = os.getenv("XROCKET_API_URL", "https://pay.api.xrocket.exchange/api/v1")
DB_PATH = os.getenv("DB_PATH", "data/shop.db")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")
if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS не задан в .env")

PRIVACY_POLICY = """
<b>Политика конфиденциальности</b>

Перед использованием магазина, пожалуйста, ознакомьтесь с тем, как мы обрабатываем ваши данные.

<b>1. Какие данные мы собираем:</b>
• Ваш Telegram ID и Username (для идентификации вас как покупателя).
• Историю покупок и баланс внутри бота.
• Данные о пополнениях (ID транзакций xRocket).

<b>2. Как мы используем данные:</b>
• Для предоставления доступа к купленным товарам.
• Для зачисления средств и работы системы поддержки.

<b>3. Передача данных третьим лицам:</b>
• Мы не передаем ваши данные рекламным сетям или сторонним лицам.
• Платежи обрабатываются через защищенный шлюз xRocket (xrocket.exchange).

<b>4. Ваши права:</b>
• Вы можете запросить удаление ваших данных, обратившись в поддержку.

Нажимая кнопку «Я согласен», вы подтверждаете, что ознакомились с данной политикой и принимаете её условия.
"""