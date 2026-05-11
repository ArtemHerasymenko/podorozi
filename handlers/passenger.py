from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from states.passenger_states import PassengerStates
from database import search_trips_ids, book_trip, get_driver_id, get_driver_id_by_booking, get_trip_details, get_trip_details_by_booking, get_passenger_phone_by_booking, get_passenger_bookings, get_latest_passenger_past_booking, get_prev_passenger_past_booking, get_next_passenger_past_booking, get_passenger_past_booking_position, update_booking_status, get_recent_phone_numbers, save_or_update_phone_number, save_recent_search, get_recent_search_times
from database import create_trip_search_list, get_current_trip_from_search_list, increase_trip_search_list_index, decrease_trip_search_list_index
from database import increment_city_popularity, add_city_if_missing
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from keyboards.city_kb import cities_keyboard
from keyboards.booking_kb import booking_actions_kb
from aiogram.types import ReplyKeyboardRemove
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Bot
import asyncio
import datetime
from zoneinfo import ZoneInfo
from handlers.common import generate_quick_days, quick_day_kb, validate_time, validate_city_name, generate_datetime, format_basic_details, format_booking_description_for_driver, format_booking_description_for_passenger, back_only_kb

def mask_phone(phone):
    if not phone or len(phone) < 4:
        return phone
    return phone[:3] + '*' * (len(phone) - 4) + phone[-1]

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
        [KeyboardButton(text="📜 Мої минулі поїздки")],
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
        booking_id, trip_id, from_city, to_city, dep_dt, price, seats, status, driver_id, notes, pickup_at, arrival_time, booked_seats, from_points, to_points, driver_phone, passenger_phone, car_description = trip
        status_label = STATUS_LABELS.get(status, status)
        try:
            driver_chat = await message.bot.get_chat(driver_id)
            driver_name = driver_chat.full_name
        except:
            driver_chat = None
            driver_name = "Водій"
        booking_desc = format_booking_description_for_passenger(from_city, to_city, dep_dt, notes, pickup_at, arrival_time, booked_seats, from_points, to_points, car_description)
        if not driver_phone:
            driver_phone_line = "\n📞 Водій не вказав свій номер"
        elif status == "confirmed":
            driver_phone_line = f"\n📞 Телефон водія: {driver_phone}"
        else:
            driver_phone_line = f"\n📞 {mask_phone(driver_phone)}"
        passenger_phone_line = f"\n📱 Ваш телефон: {passenger_phone}" if passenger_phone else ""
        text = f"{booking_desc}\n💰 {price} грн\n👤 {driver_name}{driver_phone_line}{passenger_phone_line}\n{status_label}"
        if status in ACTIVE_STATUSES:
            driver_url = f"https://t.me/{driver_chat.username}" if (driver_chat and driver_chat.username) else f"tg://user?id={driver_id}"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✉️ Написати водію", url=driver_url)],
                [InlineKeyboardButton(text="Скасувати замовлення ❌", callback_data=f"cancel_booking:{booking_id}")]
            ])
        else:
            kb = None
        await message.answer(text, reply_markup=kb)

@router.message(lambda m: m.text == "📜 Мої минулі поїздки")
async def my_past_trips(message: types.Message):
    booking = get_latest_passenger_past_booking(message.from_user.id)
    if not booking:
        await message.answer("У вас ще немає завершених поїздок.")
        return
    text, kb = await _build_past_passenger_booking_msg(booking, message.bot, message.from_user.id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


async def _build_past_passenger_booking_msg(booking_row, bot, passenger_id):
    booking_id, from_city, to_city, dep_dt, price, status, driver_id, notes, pickup_at, arrival_time, booked_seats, from_points, to_points, driver_phone, passenger_phone, car_description = booking_row
    status_label = STATUS_LABELS.get(status, status)
    pos = get_passenger_past_booking_position(passenger_id, booking_id)
    position_line = f"🗓 Бронювання #{pos[0]} з {pos[1]}\n" if pos else ""
    try:
        driver_chat = await bot.get_chat(driver_id)
        driver_name = driver_chat.full_name
    except:
        driver_chat = None
        driver_name = "Водій"
    booking_desc = format_booking_description_for_passenger(from_city, to_city, dep_dt, notes, pickup_at, arrival_time, booked_seats, from_points, to_points, car_description)
    if not driver_phone:
        driver_phone_line = "\n📞 Водій не вказав свій номер"
    elif status == "confirmed":
        driver_phone_line = f"\n📞 Телефон водія: {driver_phone}"
    else:
        driver_phone_line = f"\n📞 {mask_phone(driver_phone)}"
    passenger_phone_line = f"\n📱 Ваш телефон: {passenger_phone}" if passenger_phone else ""
    text = f"{position_line}{booking_desc}\n💰 {price} грн\n👤 {driver_name}{driver_phone_line}{passenger_phone_line}\n{status_label}"

    rows = []
    if driver_chat:
        driver_url = f"https://t.me/{driver_chat.username}" if driver_chat.username else f"tg://user?id={driver_id}"
        rows.append([InlineKeyboardButton(text="✉️ Написати водію", url=driver_url)])

    nav_row = []
    if get_prev_passenger_past_booking(passenger_id, booking_id):
        nav_row.append(InlineKeyboardButton(text="⬅️ Старіша", callback_data=f"ph_prev:{booking_id}"))
    if get_next_passenger_past_booking(passenger_id, booking_id):
        nav_row.append(InlineKeyboardButton(text="Новіша ➡️", callback_data=f"ph_next:{booking_id}"))
    if nav_row:
        rows.append(nav_row)

    kb = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
    return text, kb


@router.callback_query(lambda c: c.data and (c.data.startswith("ph_prev:") or c.data.startswith("ph_next:")))
async def passenger_history_nav(callback: types.CallbackQuery, bot: Bot):
    action, booking_id_str = callback.data.split(":")
    current_booking_id = int(booking_id_str)
    passenger_id = callback.from_user.id

    if action == "ph_prev":
        booking = get_prev_passenger_past_booking(passenger_id, current_booking_id)
    else:
        booking = get_next_passenger_past_booking(passenger_id, current_booking_id)

    if not booking:
        await callback.answer()
        return

    text, kb = await _build_past_passenger_booking_msg(booking, bot, passenger_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(StateFilter(PassengerStates), lambda m: m.text == "⬅️ Назад")
async def passenger_flow_back(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Меню пасажира:", reply_markup=passenger_menu_kb)

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
    city = message.text.title()
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
    city = message.text.title()
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
    day = day_dict[message.text]
    await state.update_data(day=day)
    data = await state.get_data()
    recent_times = get_recent_search_times(message.from_user.id, data["from_city"], data["to_city"], day)
    await message.answer(
        "Введи бажаний час виїзду у форматі ГГ:ХХ або обери один із варіантів:",
        reply_markup=quick_time_kb(day, recent_times)
    )
    await state.set_state(PassengerStates.search_from_datetime)

QUICK_TIME_OPTIONS = [10, 30, 60, 120]


def round_to_nearest_10_minutes(dt: datetime.datetime) -> datetime.datetime:
    rounded_minutes = ((dt.minute + 5) // 10) * 10
    if rounded_minutes == 60:
        dt = dt + datetime.timedelta(hours=1)
        rounded_minutes = 0
    return dt.replace(minute=rounded_minutes, second=0, microsecond=0)


TOMORROW_TIME_OPTIONS = ["07:00", "08:00"]

def quick_time_kb(day_str: str, recent_times: list = None) -> ReplyKeyboardMarkup:
    now_kyiv = datetime.datetime.now(ZoneInfo('Europe/Kyiv'))
    today = now_kyiv.strftime("%Y-%m-%d")
    is_today = day_str == today
    options = []
    if recent_times:
        for t in recent_times:
            if is_today:
                h, m = map(int, t.split(":"))
                if now_kyiv.replace(hour=h, minute=m, second=0, microsecond=0) <= now_kyiv + datetime.timedelta(minutes=10):
                    continue
            options.append([KeyboardButton(text=t)])
    options.sort(key=lambda row: row[0].text)

    if not options:
        if not is_today:
            options = [[KeyboardButton(text=t)] for t in TOMORROW_TIME_OPTIONS]
        else:
            base = round_to_nearest_10_minutes(now_kyiv)
            options = []
            for minutes in QUICK_TIME_OPTIONS:
                option_time = base + datetime.timedelta(minutes=minutes)
                if option_time.date() == base.date():
                    options.append([KeyboardButton(text=option_time.strftime("%H:%M"))])
    options.append([KeyboardButton(text="Показати всі поїздки")])
    options.append([KeyboardButton(text="⬅️ Назад")])
    return ReplyKeyboardMarkup(keyboard=options, resize_keyboard=True, one_time_keyboard=True)

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
    if trip[2]:
        phone_line = f"\n📞 {mask_phone(trip[2])}"
    else:
        phone_line = "\n📞 Водій не вказав свій номер"
    car_line = f"\n🚘 {trip[12]}" if trip[12] else ""
    return (
        f"📍 {position_text}\n"
        f"{driver_line}"
        f"{phone_line}"
        f"{format_basic_details(trip[3], trip[5], trip[7], trip[11], trip[4], trip[6])}\n"
        f"💰 {trip[8]} грн\n"
        f"👥 Вільних місць: {trip[10]}/{trip[9]}{car_line}")

@router.message(PassengerStates.search_from_datetime)
async def search(message: types.Message, state: FSMContext):
    time_str = message.text if message.text == "Показати всі поїздки" else message.text.zfill(5)

    if time_str != "Показати всі поїздки":
        is_valid, error_msg = validate_time(time_str)
        if not is_valid:
            await message.answer(error_msg)
            return

    now_kyiv = datetime.datetime.now(ZoneInfo('Europe/Kyiv'))
    data = await state.get_data()
    if time_str != "Показати всі поїздки":
        save_recent_search(message.from_user.id, data["from_city"], data["to_city"], time_str, data["day"])
    selected_day = data.get("day")
    is_today = selected_day == now_kyiv.strftime("%Y-%m-%d")
    kyiv_end_of_day = now_kyiv.replace(hour=23, minute=59, second=59, microsecond=0)
    kyiv_next_day = now_kyiv + datetime.timedelta(days=1)

    if message.text == "Показати всі поїздки":
        if is_today:
            kyiv_from = now_kyiv
            kyiv_to = kyiv_end_of_day
        else:
            kyiv_from = kyiv_next_day.replace(hour=0, minute=0, second=0, microsecond=0)
            kyiv_to = kyiv_next_day.replace(hour=23, minute=59, second=59, microsecond=0)
        utc_from = kyiv_from.astimezone(datetime.timezone.utc)
        utc_to = kyiv_to.astimezone(datetime.timezone.utc)
    else:
        success, input_dt = generate_datetime(selected_day, time_str)
        if not success:
            await message.answer(input_dt)
            return
        utc_from = round_to_nearest_10_minutes(input_dt - datetime.timedelta(minutes=30))
        utc_to = round_to_nearest_10_minutes(input_dt + datetime.timedelta(hours=1))
        if is_today:
            utc_from = max(utc_from, now_kyiv.astimezone(datetime.timezone.utc))
            utc_to = min(utc_to, kyiv_end_of_day.astimezone(datetime.timezone.utc))
        else:
            utc_from = max(utc_from, kyiv_next_day.replace(
                hour=0, minute=0, second=0, microsecond=0).astimezone(datetime.timezone.utc))
            utc_to = min(utc_to, kyiv_next_day.replace(
                hour=23, minute=59, second=59, microsecond=0).astimezone(datetime.timezone.utc))

    await state.update_data(search_from_datetime=utc_from, search_to_datetime=utc_to)
    await state.set_state(PassengerStates.seats_requested)
    await message.answer("👥 Скільки місць вам потрібно?", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=str(i))] for i in range(1, 5)] + [[KeyboardButton(text="⬅️ Назад")]],
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
    
    search_from_datetime = data["search_from_datetime"]
    search_to_datetime = data["search_to_datetime"]
    await message.answer(
        f"🔎 Шукаємо поїздки на { 'сьогодні' if data['day'] == datetime.datetime.now(ZoneInfo('Europe/Kyiv')).strftime('%Y-%m-%d') else 'завтра' }\n"
        f"з {search_from_datetime.astimezone(ZoneInfo('Europe/Kyiv')).strftime('%H:%M')} до {search_to_datetime.astimezone(ZoneInfo('Europe/Kyiv')).strftime('%H:%M')}",
        reply_markup=back_only_kb
    )
    await asyncio.sleep(3)
    
    # if now is 19:43, we will say that we are looking for 19:43-XX:MM, 
    # but actually we look from 19:48, just to make sure we don't show already departed trips, 
    # or close to departure ones.
    min_from = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
    search_from_datetime = max(search_from_datetime, min_from)
    all_trips = search_trips_ids(data["from_city"], data["to_city"], search_from_datetime, search_to_datetime)
    total = len(all_trips)
    trips_ids = [t_id for t_id, free_seats in all_trips if free_seats >= seats]

    def trip_word(n):
        last2, last1 = n % 100, n % 10
        if 11 <= last2 <= 14:
            return "Поїздок"
        if last1 == 1:
            return "Поїздку"
        if 2 <= last1 <= 4:
            return "Поїздки"
        return "Поїздок"

    if not trips_ids:
        if total == 0:
            await message.answer("Поїздок на цей час не знайдено, спробуйте пізніше.", reply_markup=passenger_menu_kb)
        else:
            await message.answer(f"Знайдено {total} {trip_word(total)}, але вільних місць вже немає.", reply_markup=passenger_menu_kb)
        await state.clear()
        return

    await message.answer(f"Знайдено {total} {trip_word(total)}, {len(trips_ids)} з них мають вільні місця.")
    create_trip_search_list(message.from_user.id, trips_ids)
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
        "📍 Вкажіть місце де вас підібрати. Рекомендуємо ввести орієнтир, який водій легко зможе " \
        "знайти, наприклад: біля школи",
        reply_markup=back_only_kb
    )

@router.message(PassengerStates.booking_notes)
async def booking_notes_handler(message: types.Message, state: FSMContext):
    notes = message.text
    await state.update_data(booking_notes=notes)

    recent_phones = get_recent_phone_numbers(message.from_user.id, limit=4)
    phone_kb_buttons = []
    if recent_phones:
        phone_kb_buttons.extend([[KeyboardButton(text=phone)] for phone in recent_phones])
    phone_kb_buttons.extend([
        [KeyboardButton(text="📱 Поділитися моїм номером з телеграму", request_contact=True)],
        [KeyboardButton(text="Не ділитися")],
        [KeyboardButton(text="⬅️ Назад")],
    ])

    phone_kb = ReplyKeyboardMarkup(
        keyboard=phone_kb_buttons,
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(
        "Якщо хочете, поділіться номером телефону або напишіть вручну. Його бачитиме лише цей водій.",
        reply_markup=phone_kb,
    )
    await state.set_state(PassengerStates.booking_phone)


@router.message(PassengerStates.booking_phone)
async def booking_phone_handler(message: types.Message, state: FSMContext):
    phone = None
    if message.text == "Не ділитися":
        phone = None
    elif message.contact:
        if message.contact.user_id and message.contact.user_id != message.from_user.id:
            await message.answer("Будь ласка, надішліть ваш власний контакт.")
            return
        phone = message.contact.phone_number
    else:
        phone = (message.text or "").strip()
        if phone:
            save_or_update_phone_number(message.from_user.id, phone)

    data = await state.get_data()
    trip_id = data["booking_trip_id"]
    notes = data.get("booking_notes")
    seats_requested = data.get("seats_requested", 1)
    passenger_id = message.from_user.id
    passenger_name = message.from_user.full_name

    success, booking_id = book_trip(trip_id, passenger_id, notes, seats_requested, phone)

    BOOK_ERRORS = {
        "not_found": "❌ Поїздку не знайдено. Спробуйте знайти іншу.",
        "cancelled":  "❌ Водій скасував цю поїздку. Спробуйте знайти іншу.",
        "departed":   "❌ Ця поїздка вже відправилась. Спробуйте знайти іншу.",
        "no_seats":   "❌ На жаль, хтось щойно зайняв вільні місця. Спробуйте знайти іншу поїздку.",
        "overlap":    "❌ У вас вже є активне бронювання на цей час. Можете його скасувати і спробувати ще раз.",
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
    booking_desc = format_booking_description_for_driver(trip_details[0], trip_details[1], trip_details[2], notes=notes, arrival_dt=trip_details[3], seats=seats_requested, from_points=trip_details[4], to_points=trip_details[5], passenger_phone=phone) if trip_details else "N/A"

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
        if arrival_dt <= datetime.datetime.now(datetime.timezone.utc):
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
        passenger_phone = get_passenger_phone_by_booking(booking_id)
        booking_desc = (
            format_booking_description_for_driver(
                trip[0], trip[1], trip[2],
                notes=trip[3], pickup_at=trip[4], arrival_dt=trip[5],
                seats=trip[6], from_points=trip[7], to_points=trip[8],
                passenger_phone=passenger_phone,
            ) if trip else ""
        )
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
