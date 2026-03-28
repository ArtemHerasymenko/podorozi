from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from states.driver_states import DriverStates
from database import save_trip_to_db
from database import increment_city_popularity
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from keyboards.city_kb import cities_keyboard
from aiogram.types import ReplyKeyboardRemove
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import update_booking_status, get_passenger_id
from aiogram import Bot
import datetime
from handlers.common import generate_quick_days, quick_day_kb, validate_time, generate_datetime

router = Router()

driver_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚗 Створити поїздку")],
        [KeyboardButton(text="📋 Мої поїздки водія")],
        [KeyboardButton(text="⬅️ Назад")]
    ],
    resize_keyboard=True
)

@router.message(lambda m: m.text == "🚗 Я водій")
async def driver_menu(message: types.Message):
    await message.answer(
        "Меню водія:",
        reply_markup=driver_menu_kb
    )

@router.message(lambda m: m.text == "🚗 Створити поїздку")
async def create_trip(message: types.Message, state: FSMContext):
    await message.answer(
    "Оберіть місто відправлення:",
    reply_markup=cities_keyboard(message.from_user.id)
    )
    await state.set_state(DriverStates.from_city)

@router.message(DriverStates.from_city)
async def from_city(message: types.Message, state: FSMContext):
    await state.update_data(from_city=message.text)
    increment_city_popularity(message.from_user.id, message.text)
    await message.answer(
        "Введіть точки маршруту через кому:", 
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(DriverStates.from_points)

@router.message(DriverStates.from_points)
async def from_points(message: types.Message, state: FSMContext):
    await state.update_data(from_points=message.text)
    await message.answer("Місто прибуття:",reply_markup=cities_keyboard(message.from_user.id))
    await state.set_state(DriverStates.to_city)

@router.message(DriverStates.to_city)
async def to_city(message: types.Message, state: FSMContext):
    await state.update_data(to_city=message.text)
    increment_city_popularity(message.from_user.id, message.text)
    await message.answer("Точки прибуття:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(DriverStates.to_points)

@router.message(DriverStates.to_points)
async def to_points(message: types.Message, state: FSMContext):
    await state.update_data(to_points=message.text)
    await message.answer("Обери день:", reply_markup=quick_day_kb())
    await state.set_state(DriverStates.day)

@router.message(DriverStates.day)
async def day(message: types.Message, state: FSMContext):
    quick_days = generate_quick_days()
    day_dict = {label: date_str for label, date_str in quick_days}
    if message.text not in day_dict:
        await message.answer("Обери день зі списку.")
        return
    await state.update_data(day=day_dict[message.text])
    await message.answer("Введи запланований час виїзду у форматі ГГ:ХХ:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(DriverStates.datetime)

@router.message(DriverStates.datetime)
async def time(message: types.Message, state: FSMContext):
    time_str = message.text

    # Validate time format and values
    is_valid, error_msg = validate_time(time_str)
    if not is_valid:
        await message.answer(error_msg)
        return

    data = await state.get_data()
    is_valid, response = generate_datetime(data.get("day"), time_str)
    if not is_valid:
        await message.answer(response)
        return

    await state.update_data(datetime=response)
    await message.answer("Ціна:")
    await state.set_state(DriverStates.price)

@router.message(DriverStates.price)
async def price(message: types.Message, state: FSMContext):
    await state.update_data(price=message.text)
    await message.answer("Місця:")
    await state.set_state(DriverStates.seats)

@router.message(DriverStates.seats)
async def seats(message: types.Message, state: FSMContext):
    await state.update_data(seats=message.text)
    data = await state.get_data()

    save_trip_to_db(message.from_user.id, data)

    await message.answer("Поїздка збережена ✅", reply_markup=driver_menu_kb)
    await state.clear()


# Обробка підтвердження броні
@router.callback_query(lambda c: c.data.startswith("confirm_booking:"))
async def confirm_booking(callback: types.CallbackQuery, bot: Bot):
    booking_id = int(callback.data.split(":")[1])
    updated = update_booking_status(booking_id, "confirmed")
    if not updated:
        await callback.answer()
        await callback.message.edit_text(callback.message.text + "\n\nПасажир вже відмінив бронювання", reply_markup=None)
    else:
        await callback.answer()
        await callback.message.edit_text(callback.message.text + "\n\nБронювання підтверджено", reply_markup=None)

    await callback.message.edit_reply_markup()  # прибираємо кнопки

    passenger_id = get_passenger_id(booking_id)
    await bot.send_message(
        passenger_id,
        "✅ Вашу бронь підтвердив водій!"
    )

@router.callback_query(lambda c: c.data.startswith("reject_booking:"))
async def reject_booking(callback: types.CallbackQuery, bot: Bot):
    booking_id = int(callback.data.split(":")[1])
    update_booking_status(booking_id, "rejected")
    await callback.message.edit_text(callback.message.text + "\n\n❌ Ви відмовили цьому пасажиру", reply_markup=None)

    await callback.message.edit_reply_markup()  # прибираємо кнопки

    passenger_id = get_passenger_id(booking_id)
    await bot.send_message(
        passenger_id,
        "❌ Вибачте, водій відмовив у бронюванні поїздки."
    )

