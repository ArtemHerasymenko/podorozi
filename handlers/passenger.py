from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from states.passenger_states import PassengerStates
from database import search_trips_ids, book_trip, get_driver_id
from database import create_trip_search_list, get_current_trip_from_search_list, increase_trip_search_list_index, decrease_trip_search_list_index
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from keyboards.city_kb import cities_keyboard
from aiogram.types import ReplyKeyboardRemove
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Bot

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

def trip_keyboard(trip_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬅️", callback_data="prev"),
            InlineKeyboardButton(text="➡️", callback_data="next"),
        ],
        [
            InlineKeyboardButton(
                text="Забронювати ✅",
                callback_data=f"book_trip:{trip_id}"
            )
        ]
    ])

def format_trip(trip):
    return (
        f"🚗 {trip[1]} → {trip[2]}\n"
        f"📅 {trip[3]}\n"
        f"⏰ {trip[4]}\n"
        f"💰 {trip[5]} грн\n"
        f"👥 {trip[6]} місць"
    )

@router.message(PassengerStates.time)
async def search(message: types.Message, state: FSMContext):
    data = await state.get_data()
    trips_ids = search_trips_ids(data["from_city"], data["to_city"])

    if not trips_ids:
        await message.answer("Нічого не знайдено")
        await state.clear()
        return

    create_trip_search_list(message.from_user.id, [t for t in trips_ids])
    trip = get_current_trip_from_search_list(message.from_user.id)

    await message.answer(
        format_trip(trip),
        reply_markup=trip_keyboard(trip[0])
    )

@router.callback_query(lambda c: c.data == "next")
async def next_handler(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id

    increase_trip_search_list_index(user_id)
    trip = get_current_trip_from_search_list(user_id)

    if not trip:
        await callback.answer("❌ Це остання поїздка", show_alert=True)
        return

    await callback.message.edit_text(
        format_trip(trip),
        reply_markup=trip_keyboard(trip[0])
    )

    await callback.answer()

@router.callback_query(lambda c: c.data == "prev")
async def prev_handler(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id

    decrease_trip_search_list_index(user_id)
    trip = get_current_trip_from_search_list(user_id)

    await callback.message.edit_text(
        format_trip(trip),
        reply_markup=trip_keyboard(trip[0])
    )

    await callback.answer()

def booking_confirmation_keyboard(booking_id: int):
    """
    Кнопки для водія: підтвердити або відмовити бронь
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"confirm_booking:{booking_id}"),
                InlineKeyboardButton(text="❌ Відмовити", callback_data=f"reject_booking:{booking_id}")
            ]
        ]
    )
    return keyboard

@router.callback_query(lambda c: c.data and c.data.startswith("book_trip:"))
async def book_trip_callback(callback: types.CallbackQuery, bot: Bot):
    trip_id = int(callback.data.split(":")[1])
    passenger_id = callback.from_user.id 
    passenger_name = callback.from_user.full_name

    success, booking_id = book_trip(trip_id, passenger_id)

    if success:
        await callback.answer("✅ Поїздка заброньована!")
        await callback.message.edit_reply_markup()  # прибираємо кнопку
    else:
        await callback.answer("❌ Місць більше немає", show_alert=True)

     # Отримуємо id водія з поїздки
    driver_id = get_driver_id(trip_id)

    # Текст для водія
    text = (
        f"🚨 Пасажир {passenger_name} хоче поїхати з пункту "
        f"A → B в {trip_id}"  # тут можна підставити час/місто з бази
    )

    await bot.send_message(
        driver_id,
        text,
        reply_markup=booking_confirmation_keyboard(booking_id)
    )
