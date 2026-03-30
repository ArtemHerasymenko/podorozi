from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from states.passenger_states import PassengerStates
from database import search_trips_ids, book_trip, get_driver_id, get_driver_id_by_booking, get_trip_details, get_passenger_bookings, update_booking_status
from database import create_trip_search_list, get_current_trip_from_search_list, increase_trip_search_list_index, decrease_trip_search_list_index
from database import increment_city_popularity
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from keyboards.city_kb import cities_keyboard
from keyboards.booking_kb import booking_actions_kb
from aiogram.types import ReplyKeyboardRemove
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Bot
import datetime
import zoneinfo
from handlers.common import generate_quick_days, quick_day_kb, validate_time, generate_datetime

router = Router()

STATUS_LABELS = {
    "pending": "⏳ Очікує підтвердження водієм",
    "confirmed": "✅ Підтверджено водієм",
    "rejected": "❌ Відхилено водієм",
    "cancelled_by_passenger": "🚫 Ви скасували ваше бронювання",
    "trip_cancelled": "🚫 Водій скасував цю поїздку"
}

passenger_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔎 Знайти поїздку")],
        [KeyboardButton(text="📋 Мої поїздки пасажира")],
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

@router.message(lambda m: m.text == "📋 Мої поїздки пасажира")
async def my_trips(message: types.Message):
    trips = get_passenger_bookings(message.from_user.id)
    if not trips:
        await message.answer("У вас ще немає заброньованих поїздок.")
        return

    ACTIVE_STATUSES = ("pending", "confirmed")
    trips = sorted(trips, key=lambda t: t[7] not in ACTIVE_STATUSES)

    for trip in trips:
        booking_id, trip_id, from_city, to_city, dep_dt, price, seats, status, driver_id = trip
        if dep_dt:
            local_tz = zoneinfo.ZoneInfo("Europe/Kiev")
            local_dt = dep_dt.astimezone(local_tz)
            dt_str = local_dt.strftime("%d.%m.%Y %H:%M")
        else:
            dt_str = "N/A"
        status_label = STATUS_LABELS.get(status, status)
        try:
            driver_chat = await message.bot.get_chat(driver_id)
            driver_name = driver_chat.full_name
        except:
            driver_name = "Водій"
        text = f"🚗 {from_city} → {to_city}\n📅 {dt_str}\n💰 {price} грн\n👤 {driver_name}\n{status_label}"
        if status in ACTIVE_STATUSES:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Скасувати замовлення ❌", callback_data=f"cancel_booking:{booking_id}")]
            ])
        else:
            kb = None
        await message.answer(text, reply_markup=kb)

@router.message(lambda m: m.text == "🔎 Знайти поїздку")
async def find_trip(message: types.Message, state: FSMContext):
    data = await state.get_data()
    trip_message_id = data.get("trip_message_id")
    if trip_message_id:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=trip_message_id,
                reply_markup=None
            )
        except:
            pass
    await message.answer(
    "Обери місто відправлення зі списку. Не знайшлось? Введи вручну:",
    reply_markup=cities_keyboard(message.from_user.id)
)
    await state.set_state(PassengerStates.from_city)

@router.message(PassengerStates.from_city)
async def from_city(message: types.Message, state: FSMContext):
    if message.text.startswith("───"):
        await message.answer("Будь ласка, обери місто зі списку.")
        return
    await state.update_data(from_city=message.text)
    increment_city_popularity(message.from_user.id, message.text)
    await message.answer("Місто прибуття:")
    await state.set_state(PassengerStates.to_city)

@router.message(PassengerStates.to_city)
async def to_city(message: types.Message, state: FSMContext):
    if message.text.startswith("───"):
        await message.answer("Будь ласка, обери місто зі списку.")
        return
    await state.update_data(to_city=message.text)
    increment_city_popularity(message.from_user.id, message.text)
    await message.answer("Обери день:", reply_markup=quick_day_kb())
    await state.set_state(PassengerStates.day)

@router.message(PassengerStates.day)
async def day_handler(message: types.Message, state: FSMContext):
    quick_days = generate_quick_days()
    day_dict = {label: date_str for label, date_str in quick_days}
    if message.text not in day_dict:
        await message.answer("Обери день зі списку.")
        return
    await state.update_data(day=day_dict[message.text])
    await message.answer("Введи бажаний час виїзду у форматі ГГ:ХХ", reply_markup=ReplyKeyboardRemove())
    await state.set_state(PassengerStates.datetime)

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
        ],
        [
            InlineKeyboardButton(
                text="Скасувати пошук ❌",
                callback_data="cancel_search"
            )
        ]
    ])

def format_trip(trip, index, total_cnt):
    position_text = f"Номер {index + 1}/{total_cnt}"
    # trip[6] is departure_datetime (timestamptz)
    dt_utc = trip[6]
    if dt_utc:
        local_tz = zoneinfo.ZoneInfo("Europe/Kiev")
        dt_local = dt_utc.astimezone(local_tz)
        day = dt_local.strftime("%Y-%m-%d")
        time = dt_local.strftime("%H:%M")
    else:
        day = "N/A"
        time = "N/A"
    return (
        f"📍 {position_text}\n\n"
        f"🚗 {trip[2]} → {trip[4]}\n"
        f"📅 {day}\n"
        f"⏰ {time}\n"
        f"💰 {trip[7]} грн\n"
        f"👥 {trip[8]} місць"
    )

@router.message(PassengerStates.datetime)
async def search(message: types.Message, state: FSMContext):
    time_str = message.text

    is_valid, error_msg = validate_time(time_str)
    if not is_valid:
        await message.answer(error_msg)
        return

    success, response = generate_datetime((await state.get_data()).get("day"), time_str)
    if not success:
        await message.answer(response)
        return

    await state.update_data(datetime=response)

    #TODO: search by day/time as well, not just cities
    # Also do not show cancelled trips in search results
    data = await state.get_data()
    trips_ids = search_trips_ids(data["from_city"], data["to_city"])

    if not trips_ids:
        await message.answer("Нічого не знайдено", reply_markup=passenger_menu_kb)
        await state.clear()
        return

    create_trip_search_list(message.from_user.id, [t for t in trips_ids])
    trip, index, total_cnt = get_current_trip_from_search_list(message.from_user.id)

    trip_message = await message.answer(
        format_trip(trip, index, total_cnt),
        reply_markup=trip_keyboard(trip[0])
    )
    
    await state.set_state(PassengerStates.browsing_trips)
    await state.update_data(trip_message_id=trip_message.message_id)

@router.message(PassengerStates.browsing_trips)
async def remove_buttons_on_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    trip_message_id = data.get("trip_message_id")
    
    if trip_message_id:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=trip_message_id,
                reply_markup=None
            )
        except:
            pass
    
    await state.clear()
    await message.answer(
        "Повернення в меню пасажира:",
        reply_markup=passenger_menu_kb
    )

@router.callback_query(lambda c: c.data == "next")
async def next_handler(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id

    increase_trip_search_list_index(user_id)
    result = get_current_trip_from_search_list(user_id)

    if not result:
        await callback.answer("❌ Виникла помилка, спробуйте знайти поїздку ще раз", show_alert=True)
        return

    trip, index, total_cnt = result
    await callback.message.edit_text(
        format_trip(trip, index, total_cnt),
        reply_markup=trip_keyboard(trip[0])
    )

    await callback.answer()

@router.callback_query(lambda c: c.data == "prev")
async def prev_handler(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id

    decrease_trip_search_list_index(user_id)
    result = get_current_trip_from_search_list(user_id)

    if not result:
        await callback.answer("❌ Виникла помилка, спробуйте знайти поїздку ще раз", show_alert=True)
        return

    trip, index, total_cnt = result
    await callback.message.edit_text(
        format_trip(trip, index, total_cnt),
        reply_markup=trip_keyboard(trip[0])
    )

    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("book_trip:"))
async def book_trip_callback(callback: types.CallbackQuery, bot: Bot):
    trip_id = int(callback.data.split(":")[1])
    passenger_id = callback.from_user.id 
    passenger_name = callback.from_user.full_name

    success, booking_id = book_trip(trip_id, passenger_id)

    if not success:
        await callback.answer("❌ Водій скасував цю поїздку", show_alert=True)
        return

    await callback.answer("✅ Поїздка заброньована!")
    await callback.message.edit_reply_markup()  # прибираємо кнопку
    await callback.message.answer(
        "⏳ Ми відправили запит водієві, очікуйте підтвердження.",
        reply_markup=passenger_menu_kb
    )

     # Отримуємо id водія з поїздки
    driver_id = get_driver_id(trip_id)

    # Отримуємо деталі поїздки
    trip_details = get_trip_details(trip_id)
    if trip_details:
        from_city, to_city, dep_dt = trip_details
        if dep_dt:
            local_tz = zoneinfo.ZoneInfo("Europe/Kiev")
            local_dt = dep_dt.astimezone(local_tz)
            time_str = local_dt.strftime("%d.%m %H:%M")
        else:
            time_str = "N/A"
        route = f"{from_city} → {to_city}"
    else:
        route = "N/A"
        time_str = "N/A"

    # Текст для водія
    text = (
        f"🚨 Пасажир {passenger_name} хоче поїхати з вами:\n"
        f"📍 {route}\n"
        f"⏰ {time_str}"
    )

    await bot.send_message(
        driver_id,
        text,
        reply_markup=booking_actions_kb(booking_id)
    )

@router.callback_query(lambda c: c.data == "cancel_search")
async def cancel_search(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.clear()
    await callback.message.answer("Пошук скасовано. Повернення в меню пасажира:", reply_markup=passenger_menu_kb)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("cancel_booking:"))
async def cancel_booking_callback(callback: types.CallbackQuery, bot: Bot):
    booking_id = int(callback.data.split(":")[1])
    prev_status, _ = update_booking_status(booking_id, "cancelled_by_passenger", ["pending", "confirmed"])
    lines = callback.message.text.rsplit("\n", 1)
    if prev_status in ("pending", "confirmed"):
        new_text = lines[0] + "\n" + STATUS_LABELS["cancelled_by_passenger"]
        await callback.message.edit_text(new_text, reply_markup=None)
        await callback.answer("")
        driver_id = get_driver_id_by_booking(booking_id)
        passenger_name = callback.from_user.full_name
        await bot.send_message(driver_id, f"🚫 Пасажир {passenger_name} скасував своє бронювання.")
    elif prev_status == "cancelled_by_passenger":
        new_text = lines[0] + "\n" + "🚫 Ви вже скасували цю бронь раніше"
        await callback.message.edit_text(new_text, reply_markup=None)
        await callback.answer("")
    elif prev_status == "rejected":
        new_text = lines[0] + "\n" + "🚫 Водій вже відхилив вашу бронь раніше"
        await callback.message.edit_text(new_text, reply_markup=None)
        await callback.answer("")
    elif prev_status == "trip_cancelled":
        new_text = lines[0] + "\n" + STATUS_LABELS["trip_cancelled"]
        await callback.message.edit_text(new_text, reply_markup=None)
        await callback.answer("")
    else:
        new_text = lines[0] + "\n" + "🚫 Не вдалося скасувати бронь. Виникла помилка, спробуйте ще."
        await callback.message.edit_text(new_text, reply_markup=None)
        await callback.answer()
