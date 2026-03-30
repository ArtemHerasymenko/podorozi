from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def booking_actions_kb(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"confirm_booking:{booking_id}"),
        InlineKeyboardButton(text="❌ Відмовити", callback_data=f"reject_booking:{booking_id}")
    ]])

def reject_booking_kb(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Скасувати бронювання", callback_data=f"reject_booking:{booking_id}")
    ]])
