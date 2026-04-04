from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def booking_actions_kb(booking_id: int, passenger_id: int = None) -> InlineKeyboardMarkup:
    rows = []
    if passenger_id:
        rows.append([InlineKeyboardButton(text="✉️ Написати пасажиру", url=f"tg://user?id={passenger_id}")])
    rows.append([
        InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"confirm_booking:{booking_id}"),
        InlineKeyboardButton(text="❌ Відмовити", callback_data=f"reject_booking:{booking_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def reject_booking_kb(booking_id: int, passenger_id: int = None) -> InlineKeyboardMarkup:
    rows = []
    if passenger_id:
        rows.append([InlineKeyboardButton(text="✉️ Написати пасажиру", url=f"tg://user?id={passenger_id}")])
    rows.append([InlineKeyboardButton(text="❌ Скасувати бронювання", callback_data=f"reject_booking:{booking_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
