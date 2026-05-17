from aiogram import BaseMiddleware
from aiogram.types import Update
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.methods import SendMessage, EditMessageText
from database import save_event


class IncomingLoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Update, data: dict):
        if event.message and event.message.from_user:
            save_event(event.message.from_user.id, None, event.message.text or "")
        elif event.callback_query and event.callback_query.from_user:
            save_event(event.callback_query.from_user.id, None, event.callback_query.data or "")
        return await handler(event, data)


class LoggingSession(AiohttpSession):
    async def make_request(self, bot, method, timeout=None):
        result = await super().make_request(bot, method, timeout)
        if isinstance(method, (SendMessage, EditMessageText)):
            save_event(None, method.chat_id, method.text or "")
        return result
