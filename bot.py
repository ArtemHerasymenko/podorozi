import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import TOKEN

from aiogram.filters import Command
from handlers import driver, passenger, common
from handlers.common import start
from middlewares import IncomingLoggingMiddleware, LoggingSession

bot = Bot(token=TOKEN, session=LoggingSession())
dp = Dispatcher(storage=MemoryStorage())
dp.update.outer_middleware(IncomingLoggingMiddleware())

dp.message.register(start, Command("start"))

dp.include_router(driver.router)
dp.include_router(passenger.router)
dp.include_router(common.router)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())