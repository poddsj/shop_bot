import aiohttp
import logging
from datetime import datetime
from app.config import XROCKET_API_KEY, XROCKET_API_URL

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