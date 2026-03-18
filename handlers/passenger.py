from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from states.passenger_states import PassengerStates
from database import search_trips
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

router = Router()

passenger_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔎 Знайти поїздку")],
        [KeyboardButton(text="⬅️ Назад")]
    ],
    resize_keyboard=True
)

@router.message(lambda m: m.text == "👤 Я пасажир")
async def passenger_menu(message: types.Message):
    await message.answer(
        "Меню пасажира:",
        reply_markup=passenger_menu_kb
    )

@router.message(lambda m: m.text == "🔎 Знайти поїздку")
async def find_trip(message: types.Message, state: FSMContext):
    await message.answer("Місто відправлення:")
    await state.set_state(PassengerStates.from_city)

@router.message(PassengerStates.from_city)
async def from_city(message: types.Message, state: FSMContext):
    await state.update_data(from_city=message.text)
    await message.answer("Місто прибуття:")
    await state.set_state(PassengerStates.to_city)

@router.message(PassengerStates.to_city)
async def to_city(message: types.Message, state: FSMContext):
    await state.update_data(to_city=message.text)
    await message.answer("Час:")
    await state.set_state(PassengerStates.time)

@router.message(PassengerStates.time)
async def search(message: types.Message, state: FSMContext):
    data = await state.get_data()
    trips = search_trips(data["from_city"], data["to_city"])

    if trips:
        text = ""
        for t in trips:
            text += f"{t[2]} → {t[4]} | {t[6]} | {t[7]}\n"
    else:
        text = "Нічого не знайдено"

    await message.answer(text)
    await state.clear()