import asyncio
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# =============================
# TOKEN з Environment Variables (Railway)
TOKEN = os.getenv("BOT_TOKEN")

# =============================
# Ініціалізація бота та FSM
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# =============================
# СТАНИ FSM
class DriverStates(StatesGroup):
    from_city = State()
    from_points = State()
    to_city = State()
    to_points = State()
    day = State()  # новий стан для дня
    time = State()
    price = State()
    seats = State()

class PassengerStates(StatesGroup):
    from_city = State()
    to_city = State()
    time = State()

# =============================
# Меню кнопок
role_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚗 Я водій")],
        [KeyboardButton(text="👤 Я пасажир")]
    ],
    resize_keyboard=True
)

driver_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚗 Створити поїздку")],
        [KeyboardButton(text="📋 Мої поїздки")],
        [KeyboardButton(text="⬅️ Назад")]
    ],
    resize_keyboard=True
)

passenger_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔎 Знайти поїздку")],
        [KeyboardButton(text="📋 Мої бронювання")],
        [KeyboardButton(text="⬅️ Назад")]
    ],
    resize_keyboard=True
)

# =============================
# Кнопки для вибору дня
def day_menu():
    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"Сьогодні ({today.strftime('%A')})")],
            [KeyboardButton(text=f"Завтра ({tomorrow.strftime('%A')})")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    return keyboard

# =============================
# /start
@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Привіт! Оберіть вашу роль:", reply_markup=role_menu)

# =============================
# Обробка кнопок (lambda-фільтри)
@dp.message(lambda message: message.text == "🚗 Я водій")
async def choose_driver(message: types.Message):
    await message.answer("Ви обрали роль водія", reply_markup=driver_menu)

@dp.message(lambda message: message.text == "👤 Я пасажир")
async def choose_passenger(message: types.Message):
    await message.answer("Ви обрали роль пасажира", reply_markup=passenger_menu)

@dp.message(lambda message: message.text == "⬅️ Назад")
async def go_back(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Привіт! Оберіть вашу роль:", reply_markup=role_menu)

@dp.message(lambda message: message.text == "🚗 Створити поїздку")
async def create_trip_driver(message: types.Message, state: FSMContext):
    await message.answer("Введіть місто відправлення:")
    await state.set_state(DriverStates.from_city)

@dp.message(lambda message: message.text == "🔎 Знайти поїздку")
async def search_trip_passenger(message: types.Message, state: FSMContext):
    await message.answer("Введіть місто відправлення:")
    await state.set_state(PassengerStates.from_city)

# =============================
# FSM для водія
@dp.message(DriverStates.from_city)
async def driver_from_city(message: types.Message, state: FSMContext):
    await state.update_data(from_city=message.text)
    await message.answer("Через які точки маршруту проїдете? (через кому)")
    await state.set_state(DriverStates.from_points)

@dp.message(DriverStates.from_points)
async def driver_from_points(message: types.Message, state: FSMContext):
    await state.update_data(from_points=message.text)
    await message.answer("Місто прибуття:")
    await state.set_state(DriverStates.to_city)

@dp.message(DriverStates.to_city)
async def driver_to_city(message: types.Message, state: FSMContext):
    await state.update_data(to_city=message.text)
    await message.answer("Через які точки прибуття проїдете? (через кому)")
    await state.set_state(DriverStates.to_points)

@dp.message(DriverStates.to_points)
async def driver_to_points(message: types.Message, state: FSMContext):
    await state.update_data(to_points=message.text)
    # запит на день поїздки
    await message.answer("Оберіть день поїздки:", reply_markup=day_menu())
    await state.set_state(DriverStates.day)

@dp.message(DriverStates.day)
async def driver_day(message: types.Message, state: FSMContext):
    await state.update_data(day=message.text)
    await message.answer("Вкажіть час виїзду (наприклад 17:30):")
    await state.set_state(DriverStates.time)

@dp.message(DriverStates.time)
async def driver_time(message: types.Message, state: FSMContext):
    await state.update_data(time=message.text)
    await message.answer("Вкажіть ціну за місце:")
    await state.set_state(DriverStates.price)

@dp.message(DriverStates.price)
async def driver_price(message: types.Message, state: FSMContext):
    await state.update_data(price=message.text)
    await message.answer("Вкажіть кількість вільних місць:")
    await state.set_state(DriverStates.seats)

@dp.message(DriverStates.seats)
async def driver_seats(message: types.Message, state: FSMContext):
    await state.update_data(seats=message.text)
    data = await state.get_data()
    await message.answer(
        f"Поїздка створена!\n\n"
        f"{data['from_city']} → {data['to_city']}\n"
        f"Маршрут: {data['from_points']} → {data['to_points']}\n"
        f"День: {data['day']}\n"
        f"Час: {data['time']}\n"
        f"Ціна: {data['price']}\n"
        f"Місця: {data['seats']}",
        reply_markup=driver_menu
    )
    await state.clear()

# =============================
# FSM для пасажира
@dp.message(PassengerStates.from_city)
async def passenger_from_city(message: types.Message, state: FSMContext):
    await state.update_data(from_city=message.text)
    await message.answer("Місто прибуття:")
    await state.set_state(PassengerStates.to_city)

@dp.message(PassengerStates.to_city)
async def passenger_to_city(message: types.Message, state: FSMContext):
    await state.update_data(to_city=message.text)
    await message.answer("Бажаний час виїзду (наприклад 17:00):")
    await state.set_state(PassengerStates.time)

@dp.message(PassengerStates.time)
async def passenger_time(message: types.Message, state: FSMContext):
    await state.update_data(time=message.text)
    data = await state.get_data()
    await message.answer(
        f"Шукаємо поїздки:\n\n"
        f"{data['from_city']} → {data['to_city']}\n"
        f"Бажаний час: {data['time']}\n\n"
        "Список водіїв поки що пустий (будемо підключати базу).",
        reply_markup=passenger_menu
    )
    await state.clear()

# =============================
# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())