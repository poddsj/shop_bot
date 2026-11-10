import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import BOT_TOKEN
from app.database import init_db
from app.handlers import user, admin
from app.handlers.user import bg_tasks # импортируем хранилище задач

# Передаем экземпляр бота в модули (костыль для фоновых задач)
import app.handlers.user as user_module
import app.handlers.admin as admin_module

async def main():
    logging.basicConfig(level=logging.INFO)
    
    # Инициализация БД (создаст папку data и файл shop.db)
    init_db()
    
    bot = Bot(token=BOT_TOKEN)
    
    # Передаем бота в модули, чтобы они могли отправлять сообщения
    user_module.bot = bot
    admin_module.bot = bot
    
    dp = Dispatcher(storage=MemoryStorage())
    
    # Подключаем роутеры (сначала админский, чтобы не было конфликтов)
    dp.include_router(admin.router)
    dp.include_router(user.router)
    
    print("[*] Бот запущен и готов к работе")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен")