# for local run: caffeinate -i python bot.py
# from dotenv import load_dotenv
# load_dotenv()

import asyncio
import os
from aiohttp import web
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

async def health(_):
    return web.Response(text="ok")

async def start_health_server():
    app = web.Application()
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("HEALTH_PORT", 8080))
    print(f"Starting health server on port {port}")
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Health server started on port {port}")

async def main():
    await start_health_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())