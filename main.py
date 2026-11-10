import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import BOT_TOKEN, ADMIN_IDS
from app.database import init_db
from app.handlers import user, admin

# Импортируем модули, чтобы передать в них экземпляр бота
import app.handlers.user as user_module
import app.handlers.admin as admin_module

async def main():
    logging.basicConfig(level=logging.INFO)
    
    # Инициализация БД
    init_db()
    
    bot = Bot(token=BOT_TOKEN)
    
    # Передаем бота в модули (для отправки файлов и фоновых задач)
    user_module.bot = bot
    admin_module.bot = bot
    
    dp = Dispatcher(storage=MemoryStorage())
    
    # --- ДОБАВЛЯЕМ КОМАНДУ /getdb ЗДЕСЬ ---
    @dp.message(Command("getdb"))
    async def get_database(message: types.Message):
        if message.from_user.id not in ADMIN_IDS:
            return
        try:
            db_file = FSInputFile("data/shop.db")
            await message.answer_document(db_file, caption="📁 Актуальная база данных магазина")
        except Exception as e:
            await message.answer(f"❌ Ошибка при отправке базы: {e}")
    # ---------------------------------------
    
    # Подключаем роутеры (сначала админский, чтобы команды не конфликтовали)
    dp.include_router(admin.router)
    dp.include_router(user.router)
    
    print("[*] Бот запущен и готов к работе")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен")