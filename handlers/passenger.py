from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from states.passenger_states import PassengerStates
from database import search_trips_ids, book_trip, get_driver_id, get_driver_id_by_booking, get_trip_details, get_trip_details_by_booking, get_passenger_bookings, update_booking_status
from database import create_trip_search_list, get_current_trip_from_search_list, increase_trip_search_list_index, decrease_trip_search_list_index
from database import increment_city_popularity, add_city_if_missing
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from keyboards.city_kb import cities_keyboard
from keyboards.booking_kb import booking_actions_kb
from aiogram.types import ReplyKeyboardRemove
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Bot
import datetime
from handlers.common import generate_quick_days, quick_day_kb, validate_time, validate_city_name, generate_datetime, format_basic_details, format_booking_description_for_driver, format_booking_description_for_passenger

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
        booking_id, trip_id, from_city, to_city, dep_dt, price, seats, status, driver_id, notes, driver_notes, arrival_time, booked_seats, from_points, to_points = trip
        status_label = STATUS_LABELS.get(status, status)
        try:
            driver_chat = await message.bot.get_chat(driver_id)
            driver_name = driver_chat.full_name
        except:
            driver_name = "Водій"
        booking_desc = format_booking_description_for_passenger(from_city, to_city, dep_dt, notes, driver_notes, arrival_time, booked_seats, from_points, to_points)
        text = f"{booking_desc}\n💰 {price} грн\n👤 {driver_name}\n{status_label}"
        if status in ACTIVE_STATUSES:
            driver_url = f"https://t.me/{driver_chat.username}" if (driver_chat and driver_chat.username) else f"tg://user?id={driver_id}"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✉️ Написати водію", url=driver_url)],
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
        await message.answer("Будь ласка, обери місто зі списку або введи вручну.")
        return
    is_valid, error_msg = validate_city_name(message.text)
    if not is_valid:
        await message.answer(error_msg)
        return
    city = message.text.capitalize()
    await state.update_data(from_city=city)
    increment_city_popularity(message.from_user.id, city)
    add_city_if_missing(city)
    await message.answer("Місто прибуття:", reply_markup=cities_keyboard(message.from_user.id))
    await state.set_state(PassengerStates.to_city)

@router.message(PassengerStates.to_city)
async def to_city(message: types.Message, state: FSMContext):
    if message.text.startswith("───"):
        await message.answer("Будь ласка, обери місто зі списку або введи вручну.")
        return
    is_valid, error_msg = validate_city_name(message.text)
    if not is_valid:
        await message.answer(error_msg)
        return
    city = message.text.capitalize()
    await state.update_data(to_city=city)
    increment_city_popularity(message.from_user.id, city)
    add_city_if_missing(city)
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

def trip_keyboard(trip_id, total_cnt=1, driver_id=None, driver_username=None):
    rows = []
    if total_cnt > 1:
        rows.append([
            InlineKeyboardButton(text="⬅️", callback_data="prev"),
            InlineKeyboardButton(text="➡️", callback_data="next"),
        ])
    if driver_id:
        driver_url = f"https://t.me/{driver_username}" if driver_username else f"tg://user?id={driver_id}"
        rows.append([InlineKeyboardButton(text="✉️ Написати водію", url=driver_url)])
    rows.append([InlineKeyboardButton(text="Забронювати ✅", callback_data=f"book_trip:{trip_id}")])
    rows.append([InlineKeyboardButton(text="Скасувати пошук ❌", callback_data="cancel_search")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def format_trip(trip, index, total_cnt, driver_name=None, is_own=False):
    position_text = f"Варіант номер {index + 1}/{total_cnt}"
    name_str = driver_name or "Водій"
    if is_own:
        name_str += " (Ви)"
    driver_line = f"\n👤 {name_str}"
    return (
        f"📍 {position_text}\n"
        f"{driver_line}"
        f"{format_basic_details(trip[2], trip[4], trip[6], trip[10], trip[3], trip[5])}\n"
        f"💰 {trip[7]} грн\n"
        f"👥 Вільних місць: {trip[9]}/{trip[8]}")

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
    await state.set_state(PassengerStates.seats_requested)
    await message.answer("👥 Скільки місць вам потрібно?", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=str(i)) for i in range(1, 5)]],
        resize_keyboard=True,
        one_time_keyboard=True
    ))

@router.message(PassengerStates.seats_requested)
async def seats_requested_handler(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) < 1:
        await message.answer("Введіть ціле число, наприклад 1:")
        return
    seats = int(message.text)
    await state.update_data(seats_requested=seats)

    data = await state.get_data()
    trips_ids = search_trips_ids(data["from_city"], data["to_city"], data.get("datetime"), seats)

    if not trips_ids:
        await message.answer("Нічого не знайдено", reply_markup=passenger_menu_kb)
        await state.clear()
        return

    create_trip_search_list(message.from_user.id, [t for t in trips_ids])
    # This can come as expired, very unlikely.
    trip, index, total_cnt = get_current_trip_from_search_list(message.from_user.id)

    driver_chat = None
    try:
        driver_chat = await message.bot.get_chat(trip[1])
        driver_name = driver_chat.full_name
    except:
        driver_name = None

    trip_message = await message.answer(
        format_trip(trip, index, total_cnt, driver_name, is_own=(trip[1] == message.from_user.id)),
        reply_markup=trip_keyboard(trip[0], total_cnt, trip[1], driver_chat.username if driver_chat else None)
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

    if result == "expired":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("⏱ Цей пошук застарів. Будь ласка, почніть новий!", reply_markup=passenger_menu_kb)
        await callback.answer()
        return

    if not result:
        await callback.answer("❌ Виникла помилка, спробуйте знайти поїздку ще раз", show_alert=True)
        return

    trip, index, total_cnt = result
    driver_chat = None
    try:
        driver_chat = await callback.bot.get_chat(trip[1])
        driver_name = driver_chat.full_name
    except:
        driver_name = None
    await callback.message.edit_text(
        format_trip(trip, index, total_cnt, driver_name, is_own=(trip[1] == callback.from_user.id)),
        reply_markup=trip_keyboard(trip[0], total_cnt, trip[1], driver_chat.username if driver_chat else None)
    )

    await callback.answer()

@router.callback_query(lambda c: c.data == "prev")
async def prev_handler(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id

    decrease_trip_search_list_index(user_id)
    result = get_current_trip_from_search_list(user_id)

    if result == "expired":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("⏱ Цей пошук застарів. Будь ласка, розпочніть новий!", reply_markup=passenger_menu_kb)
        await callback.answer()
        return

    if not result:
        await callback.answer("❌ Виникла помилка, спробуйте знайти поїздку ще раз", show_alert=True)
        return

    trip, index, total_cnt = result
    driver_chat = None
    try:
        driver_chat = await callback.bot.get_chat(trip[1])
        driver_name = driver_chat.full_name
    except:
        driver_name = None
    await callback.message.edit_text(
        format_trip(trip, index, total_cnt, driver_name, is_own=(trip[1] == callback.from_user.id)),
        reply_markup=trip_keyboard(trip[0], total_cnt, trip[1], driver_chat.username if driver_chat else None)
    )

    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("book_trip:"))
async def book_trip_callback(callback: types.CallbackQuery, state: FSMContext):
    trip_id = int(callback.data.split(":")[1])

    result = get_current_trip_from_search_list(callback.from_user.id)
    if result == "expired":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("⏱ Цей пошук застарів. Будь ласка, розпочніть новий!", reply_markup=passenger_menu_kb)
        await callback.answer()
        return

    trip, _, _ = result
    # if trip[1] == callback.from_user.id:
    #     await callback.answer("❌ Ви не можете забронювати власну поїздку.", show_alert=True)
    #     return

    await callback.answer()
    await callback.message.edit_reply_markup()
    await state.update_data(booking_trip_id=trip_id)
    await state.set_state(PassengerStates.booking_notes)

    await callback.message.answer(
        "📝 Вкажіть місце де вас підібрати, наприклад: 'біля магазину Нектар'",
        reply_markup=ReplyKeyboardRemove()
    )

@router.message(PassengerStates.booking_notes)
async def booking_notes_handler(message: types.Message, state: FSMContext):
    notes = message.text
    data = await state.get_data()
    trip_id = data["booking_trip_id"]
    seats_requested = data.get("seats_requested", 1)
    passenger_id = message.from_user.id
    passenger_name = message.from_user.full_name

    success, booking_id = book_trip(trip_id, passenger_id, notes, seats_requested)

    BOOK_ERRORS = {
        "not_found": "❌ Поїздку не знайдено.",
        "cancelled":  "❌ Водій скасував цю поїздку.",
        "departed":   "❌ Ця поїздка вже відправилась.",
        "no_seats":   "❌ На жаль, недостатньо вільних місць.",
        "overlap":    "❌ У вас вже є активне бронювання на цей час.",
    }
    if not success:
        await message.answer(BOOK_ERRORS.get(booking_id, "❌ Не вдалося забронювати поїздку."), reply_markup=passenger_menu_kb)
        await state.clear()
        return
    await state.clear()
    await message.answer(
        "⏳ Ми відправили запит водієві, очікуйте підтвердження.",
        reply_markup=passenger_menu_kb
    )

    driver_id = get_driver_id(trip_id)
    trip_details = get_trip_details(trip_id)
    booking_desc = format_booking_description_for_driver(trip_details[0], trip_details[1], trip_details[2], notes=notes, arrival_dt=trip_details[3], seats=seats_requested, from_points=trip_details[4], to_points=trip_details[5]) if trip_details else "N/A"

    text = (
        f"🚨 Пасажир {passenger_name} хоче поїхати з вами:\n"
        f"{booking_desc}"
    )

    await message.bot.send_message(
        driver_id,
        text,
        reply_markup=booking_actions_kb(booking_id, passenger_id, message.from_user.username)
    )

@router.callback_query(lambda c: c.data == "cancel_search")
async def cancel_search(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.clear()
    await callback.message.answer("Пошук скасовано. Повернення в меню пасажира:", reply_markup=passenger_menu_kb)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("cancel_booking:"))
async def cancel_booking_callback(callback: types.CallbackQuery, bot: Bot):
    import datetime
    booking_id = int(callback.data.split(":")[1])

    trip = get_trip_details_by_booking(booking_id)
    if trip:
        arrival_dt = trip[5]
        if arrival_dt <= datetime.datetime.now(tz=arrival_dt.tzinfo):
            await callback.answer("❌ Поїздка вже відбулась, скасування неможливе.", show_alert=True)
            return

    prev_status, _ = update_booking_status(booking_id, "cancelled_by_passenger", ["pending", "confirmed"])
    lines = callback.message.text.rsplit("\n", 1)
    if prev_status in ("pending", "confirmed"):
        new_text = lines[0] + "\n" + STATUS_LABELS["cancelled_by_passenger"]
        await callback.message.edit_text(new_text, reply_markup=None)
        await callback.answer("")
        driver_id = get_driver_id_by_booking(booking_id)
        passenger_name = callback.from_user.full_name
        booking_desc = format_booking_description_for_driver(*trip) if trip else ""
        await bot.send_message(driver_id, f"🚫 Пасажир {passenger_name} скасував своє бронювання.\n{booking_desc}")
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
