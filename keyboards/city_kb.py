from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from data.cities import CITIES

def cities_keyboard():
    keyboard = []

    # робимо по 2 кнопки в ряд
    for i in range(0, len(CITIES), 2):
        row = [KeyboardButton(text=city) for city in CITIES[i:i+2]]
        keyboard.append(row)

    keyboard.append([KeyboardButton(text="⬅️ Назад")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )