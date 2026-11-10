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
    
    client_inv_id = f"user_{user_id}_{int(datetime.now().timestamp())}"
    
    payload = {
        "priceAmount": f"{amount:.2f}",
        "priceCurrency": "USDT", 
        "payCurrencies": ["USDT"],
        "numPayments": 1,
        "clientInvoiceId": client_inv_id,
        "description": f"Top-up for user {user_id}",
        "expiresIn": 1800000
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            try:
                data = await resp.json()
            except Exception:
                return None, None, None

            if resp.status in (200, 201):
                inv_id = data.get("id") or data.get("data", {}).get("id")
                links = data.get("links") or data.get("data", {}).get("links", {})
                pay_link = links.get("telegramBotLink") or links.get("web_url") or links.get("pay_url")
                return inv_id, client_inv_id, pay_link
            else:
                logging.error(f"XRocket Create Error: {resp.status} - {data}")
                return None, None, None

async def check_xrocket_payment(invoice_id, client_invoice_id=None):
    headers = {"Authorization": f"Bearer {XROCKET_API_KEY}"}
    
    # 1. Пробуем найти по ID
    url = f"{XROCKET_API_URL}/invoices/{invoice_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                status = data.get("status") or data.get("state")
                if status in ("paid", "completed"):
                    return "paid"
                return str(status)
            
            # 2. Если 404, ищем в списке
            if resp.status == 404:
                list_url = f"{XROCKET_API_URL}/invoices?limit=20"
                async with session.get(list_url, headers=headers) as resp_list:
                    if resp_list.status == 200:
                        data_list = await resp_list.json()
                        
                        # ИСПРАВЛЕНИЕ: Берем ключ "items"
                        items = data_list.get("items", [])
                        
                        for item in items:
                            # Сравниваем ID
                            if str(item.get("id")) == str(invoice_id) or item.get("clientInvoiceId") == client_invoice_id:
                                status = item.get("status") or item.get("state")
                                # Если нашли, проверяем статус
                                if status in ("paid", "completed"):
                                    return "paid"
                                return str(status) # Вернет "active" или "pending", если еще не оплачен
                        
                        # Если прошлись по списку и не нашли
                        return "not_found_in_list"
                    else:
                        return f"LIST_ERROR_{resp_list.status}"
            return f"HTTP_{resp.status}"