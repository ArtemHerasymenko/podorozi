from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from database import get_cities, get_cities_for_user_sorted

def cities_keyboard(user_id=None):
    if user_id:
        popular, others = get_cities_for_user_sorted(user_id)
    else:
        popular = []
        others = get_cities()

    keyboard = []
    if popular:
        keyboard.append([KeyboardButton(text="─── Нещодавно ти обирав ───")])
        for i in range(0, len(popular), 1):
            row = [KeyboardButton(text=city) for city in popular[i:i+1]]
            keyboard.append(row)
        keyboard.append([KeyboardButton(text="─── Інші міста ───")])
    for i in range(0, len(others), 1):
        row = [KeyboardButton(text=city) for city in others[i:i+1]]
        keyboard.append(row)

    keyboard.append([KeyboardButton(text="⬅️ Назад")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )