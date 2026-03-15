import asyncio
import os
from datetime import datetime, timedelta
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# =============================
# TOKEN з Environment Variables
TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")  # PostgreSQL URL з Railway

# =============================
# Ініціалізація бота та FSM
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# =============================
# Підключення до PostgreSQL
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# =============================
# Створення таблиці trips
cursor.execute("""
CREATE TABLE IF NOT EXISTS trips (
    id SERIAL PRIMARY KEY,
    driver_id BIGINT,
    from_city TEXT,
    from_points TEXT,
    to_city TEXT,
    to_points TEXT,
    day TEXT,
    time TEXT,
    price TEXT,
    seats TEXT
)
""")
conn.commit()

# =============================
# СТАНИ FSM
class DriverStates(StatesGroup):
    from_city = State()
    from_points = State()
    to_city = State()
    to_points = State()
    day = State()
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
# Мапа днів тижня українською
UKRAINIAN_WEEKDAYS = {
    "Monday": "понеділок",
    "Tuesday": "вівторок",
    "Wednesday": "середа",
    "Thursday": "четвер",
    "Friday": "п’ятниця",
    "Saturday": "субота",
    "Sunday": "неділя"
}

# =============================
# Кнопки для вибору дня українською з датою
def day_menu():
    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    today_str = today.strftime("%d-%m-%Y")
    tomorrow_str = tomorrow.strftime("%d-%m-%Y")
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"Сьогодні ({UKRAINIAN_WEEKDAYS[today.strftime('%A')]}, {today_str})")],
            [KeyboardButton(text=f"Завтра ({UKRAINIAN_WEEKDAYS[tomorrow.strftime('%A')]}, {tomorrow_str})")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    return keyboard

# =============================
# Функції роботи з базою
def save_trip(driver_id, data):
    cursor.execute("""
        INSERT INTO trips (driver_id, from_city, from_points, to_city, to_points, day, time, price, seats)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        driver_id,
        data["from_city"],
        data["from_points"],
        data["to_city"],
        data["to_points"],
        data["day"],
        data["time"],
        data["price"],
        data["seats"]
    ))
    conn.commit()

def search_trips(from_city, to_city):
    cursor.execute("""
        SELECT driver_id, from_city, from_points, to_city, to_points, day, time, price, seats
        FROM trips
        WHERE from_city ILIKE %s AND to_city ILIKE %s
    """, (f"%{from_city}%", f"%{to_city}%"))
    return cursor.fetchall()

# =============================
# /start
@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Привіт! Оберіть вашу роль:", reply_markup=role_menu)

# =============================
# Обробка кнопок
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
# FSM водія
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
    
    # Зберігаємо поїздку в PostgreSQL
    save_trip(message.from_user.id, data)
    
    await message.answer(
        f"Поїздка створена та збережена!\n\n"
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
# FSM пасажира
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
    
    trips = search_trips(data["from_city"], data["to_city"])
    
    if trips:
        text = "Знайдено поїздки:\n\n"
        for trip in trips:
            text += (
                f"{trip[1]} → {trip[3]}\n"
                f"Маршрут: {trip[2]} → {trip[4]}\n"
                f"День: {trip[5]}\n"
                f"Час: {trip[6]}\n"
                f"Ціна: {trip[7]}\n"
                f"Місця: {trip[8]}\n\n"
            )
    else:
        text = "На жаль, поїздок не знайдено."
    
    await message.answer(text, reply_markup=passenger_menu)
    await state.clear()

# =============================
# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())