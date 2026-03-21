from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from database import get_cities, get_cities_for_user

def cities_keyboard(user_id=None):
    if user_id:
        cities = get_cities_for_user(user_id)
    else:
        cities = get_cities()
    keyboard = []

    # робимо по 2 кнопки в ряд
    for i in range(0, len(cities), 1):
        row = [KeyboardButton(text=city) for city in cities[i:i+1]]
        keyboard.append(row)

    keyboard.append([KeyboardButton(text="⬅️ Назад")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )