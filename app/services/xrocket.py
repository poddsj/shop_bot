import aiohttp
import asyncio
import logging
import uuid
from app.config import XROCKET_API_KEY, XROCKET_API_URL

async def create_xrocket_invoice(amount, user_id):
    url = f"{XROCKET_API_URL}/invoices"
    headers = {
        "Authorization": f"Bearer {XROCKET_API_KEY}",
        "Content-Type": "application/json"
    }
    
    client_inv_id = f"user_{user_id}_{uuid.uuid4().hex}"
    
    payload = {
        "priceAmount": f"{amount:.2f}",
        "priceCurrency": "USDT", 
        "payCurrencies": ["USDT"],
        "numPayments": 1,
        "clientInvoiceId": client_inv_id,
        "description": f"Top-up for user {user_id}",
        "expiresIn": 1800000
    }

    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                try:
                    data = await resp.json()
                except (aiohttp.ContentTypeError, ValueError):
                    logging.error("xRocket invoice API returned non-JSON response (HTTP %s)", resp.status)
                    return None, None, None

                if resp.status in (200, 201):
                    body = data.get("data", data) if isinstance(data, dict) else {}
                    inv_id = body.get("id")
                    links = body.get("links") or {}
                    pay_link = links.get("telegramBotLink") or links.get("web_url") or links.get("pay_url")
                    if inv_id and pay_link:
                        return inv_id, client_inv_id, pay_link
                    logging.error("xRocket response missing invoice id or payment link")
                    return None, None, None
                logging.error("xRocket Create Error: HTTP %s - %s", resp.status, data)
                return None, None, None
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logging.error("xRocket invoice request failed: %s", exc)
        return None, None, None

async def check_xrocket_payment(invoice_id, client_invoice_id=None):
    headers = {"Authorization": f"Bearer {XROCKET_API_KEY}"}
    timeout = aiohttp.ClientTimeout(total=15)
    # Only accept persisted invoice identifiers, never arbitrary URL fragments.
    invoice_id = str(invoice_id)
    if not invoice_id or len(invoice_id) > 128 or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in invoice_id):
        return "invalid_invoice_id"
    url = f"{XROCKET_API_URL}/invoices/{invoice_id}"

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    body = data.get("data", data) if isinstance(data, dict) else {}
                    status = body.get("status") or body.get("state")
                    return "paid" if status in ("paid", "completed") else str(status or "unknown")

                if resp.status != 404:
                    return f"HTTP_{resp.status}"

                # Fallback needed only when this API instance does not expose invoice-by-id.
                list_url = f"{XROCKET_API_URL}/invoices?limit=20"
                async with session.get(list_url, headers=headers) as resp_list:
                    if resp_list.status != 200:
                        return f"LIST_ERROR_{resp_list.status}"
                    data_list = await resp_list.json()

            body = data_list.get("data", data_list) if isinstance(data_list, dict) else {}
            items = body.get("items", []) if isinstance(body, dict) else []
            for item in items:
                if str(item.get("id")) == str(invoice_id) or item.get("clientInvoiceId") == client_invoice_id:
                    status = item.get("status") or item.get("state")
                    return "paid" if status in ("paid", "completed") else str(status or "unknown")
            return "not_found_in_list"
    except (aiohttp.ClientError, asyncio.TimeoutError, aiohttp.ContentTypeError, ValueError) as exc:
        logging.warning("xRocket status request failed for invoice %s: %s", invoice_id, exc)
        return "network_error"