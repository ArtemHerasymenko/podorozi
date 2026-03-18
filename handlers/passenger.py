from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from states.passenger_states import PassengerStates
from database import search_trips, book_trip
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from keyboards.city_kb import cities_keyboard
from aiogram.types import ReplyKeyboardRemove
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

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
    await message.answer(
    "Оберіть місто відправлення:",
    reply_markup=cities_keyboard()
)
    await state.set_state(PassengerStates.from_city)

@router.message(PassengerStates.from_city)
async def from_city(message: types.Message, state: FSMContext):
    await state.update_data(from_city=message.text)
    await message.answer("Місто прибуття:")
    await state.set_state(PassengerStates.to_city)

@router.message(PassengerStates.to_city)
async def to_city(message: types.Message, state: FSMContext):
    await state.update_data(to_city=message.text)
    await message.answer("Час:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(PassengerStates.time)

def trip_booking_keyboard(trip_id: int):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Забронювати ✅",
                callback_data=f"book_trip:{trip_id}"
            )]
        ]
    )
    return keyboard

@router.message(PassengerStates.time)
async def search(message: types.Message, state: FSMContext):
    data = await state.get_data()
    trips = search_trips(data["from_city"], data["to_city"])

    if not trips:
        await message.answer("Нічого не знайдено")
        await state.clear()
        return

    # Для кожної поїздки відправляємо окреме повідомлення з кнопкою
    for t in trips:
        text = (
            f"🚗 {t[2]}({t[3]}) → {t[4]}({t[5]})\n"
            f"День: {t[6]}\n"
            f"Час: {t[7]}\n"
            f"Ціна: {t[8]}\n"
            f"Місця: {t[9]}"
        )
        await message.answer(text, reply_markup=trip_booking_keyboard(t[0]))

    await state.clear()

@router.callback_query(lambda c: c.data and c.data.startswith("book_trip:"))
async def book_trip_callback(callback: types.CallbackQuery):
    trip_id = int(callback.data.split(":")[1])

    success = book_trip(trip_id)

    if result:
        await callback.answer("✅ Поїздка заброньована!")
        await callback.message.edit_reply_markup()  # прибираємо кнопку
    else:
        await callback.answer("❌ Місць більше немає", show_alert=True)
