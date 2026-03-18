from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from states.driver_states import DriverStates
from database import save_trip
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from keyboards.city_kb import cities_keyboard

router = Router()

driver_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚗 Створити поїздку")],
        [KeyboardButton(text="📋 Мої поїздки")],
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
    reply_markup=cities_keyboard()
    )
    await state.set_state(DriverStates.from_city)

@router.message(DriverStates.from_city)
async def from_city(message: types.Message, state: FSMContext):
    await state.update_data(from_city=message.text)
    await message.answer("Введіть точки маршруту через кому:" , 
        reply_markup=ReplyKeyboardRemove())
    await state.set_state(DriverStates.from_points)

@router.message(DriverStates.from_points)
async def from_points(message: types.Message, state: FSMContext):
    await state.update_data(from_points=message.text)
    await message.answer("Місто прибуття:")
    await state.set_state(DriverStates.to_city)

@router.message(DriverStates.to_city)
async def to_city(message: types.Message, state: FSMContext):
    await state.update_data(to_city=message.text)
    await message.answer("Точки прибуття:")
    await state.set_state(DriverStates.to_points)

@router.message(DriverStates.to_points)
async def to_points(message: types.Message, state: FSMContext):
    await state.update_data(to_points=message.text)
    await message.answer("День:")
    await state.set_state(DriverStates.day)

@router.message(DriverStates.day)
async def day(message: types.Message, state: FSMContext):
    await state.update_data(day=message.text)
    await message.answer("Час:")
    await state.set_state(DriverStates.time)

@router.message(DriverStates.time)
async def time(message: types.Message, state: FSMContext):
    await state.update_data(time=message.text)
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

    save_trip(message.from_user.id, data)

    await message.answer("Поїздка збережена ✅")
    await state.clear()