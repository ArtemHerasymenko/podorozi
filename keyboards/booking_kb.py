from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def booking_actions_kb(booking_id: int, passenger_id: int = None, passenger_username: str = None) -> InlineKeyboardMarkup:
    rows = []
    if passenger_id:
        passenger_url = f"https://t.me/{passenger_username}" if passenger_username else f"tg://user?id={passenger_id}"
        rows.append([InlineKeyboardButton(text="✉️ Написати пасажиру", url=passenger_url)])
    rows.append([
        InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"confirm_booking:{booking_id}"),
        InlineKeyboardButton(text="❌ Відмовити", callback_data=f"reject_booking:{booking_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def reject_booking_kb(booking_id: int, passenger_id: int = None, passenger_username: str = None) -> InlineKeyboardMarkup:
    rows = []
    if passenger_id:
        passenger_url = f"https://t.me/{passenger_username}" if passenger_username else f"tg://user?id={passenger_id}"
        rows.append([InlineKeyboardButton(text="✉️ Написати пасажиру", url=passenger_url)])
    rows.append([InlineKeyboardButton(text="❌ Скасувати бронювання", callback_data=f"reject_booking:{booking_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
