# for local run: caffeinate -i python bot.py
# from dotenv import load_dotenv
# load_dotenv()

import asyncio
import logging
import os
import psycopg2
from aiohttp import web
from aiogram import Bot, Dispatcher
from config import DATABASE_URL
from aiogram.fsm.storage.memory import MemoryStorage
from config import TOKEN

from aiogram.filters import Command
from handlers import driver, passenger, common
from handlers import template
from handlers import passenger_search
from handlers.common import start
from middlewares import IncomingLoggingMiddleware, LoggingSession

bot = Bot(token=TOKEN, session=LoggingSession())
dp = Dispatcher(storage=MemoryStorage())
dp.update.outer_middleware(IncomingLoggingMiddleware())

dp.message.register(start, Command("start"))

dp.include_router(template.router)
dp.include_router(driver.router)
dp.include_router(passenger.router)
dp.include_router(passenger_search.router)
dp.include_router(common.router)

async def health(_):
    try:
        hc_conn = psycopg2.connect(DATABASE_URL)
        with hc_conn.cursor() as cur:
            cur.execute("SELECT 1")
        hc_conn.close()
    except Exception as e:
        logging.error("Health check DB error: %s", e)
        return web.Response(text=f"db error: {e}", status=503)
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