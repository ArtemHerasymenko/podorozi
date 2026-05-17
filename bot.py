import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import TOKEN

from handlers import driver, passenger, common
from middlewares import IncomingLoggingMiddleware, LoggingSession

bot = Bot(token=TOKEN, session=LoggingSession())
dp = Dispatcher(storage=MemoryStorage())
dp.update.outer_middleware(IncomingLoggingMiddleware())

dp.include_router(driver.router)
dp.include_router(passenger.router)
dp.include_router(common.router)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())