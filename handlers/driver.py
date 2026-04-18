from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from states.driver_states import DriverStates
from database import save_trip_to_db
from database import increment_city_popularity, add_city_if_missing
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from keyboards.city_kb import cities_keyboard
from aiogram.types import ReplyKeyboardRemove
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from keyboards.booking_kb import booking_actions_kb, reject_booking_kb
from database import update_booking_status, get_passenger_id, get_driver_trips, get_latest_driver_past_trip, get_prev_driver_past_trip, get_next_driver_past_trip, get_driver_past_trip_position, get_driver_trip_by_id, get_trip_id_for_booking, cancel_trip, get_bookings_for_trip, get_trip_details, get_trip_details_by_booking, get_driver_phone_by_booking, set_booking_pickup_at, get_route_descriptions, save_route_description, get_city_modified_name, get_driver_recent_car_descriptions, save_or_update_driver_car_description, get_recent_phone_numbers, save_or_update_phone_number
from aiogram import Bot
import datetime
from zoneinfo import ZoneInfo
from handlers.common import generate_quick_days, quick_day_kb, validate_time, validate_city_name, generate_datetime, format_basic_details, format_booking_description_for_passenger, format_notes_details_for_driver

router = Router()


async def _build_driver_trip_details_msg(trip_row, bot):
    trip_id, from_city, to_city, dep_dt, price, seats, status, confirmed_count, pending_count, arrival_time, from_points, to_points, driver_phone, car_description = trip_row
    phone_line = f"\n📞 Ваш телефон: {driver_phone}" if driver_phone else ""
    car_line = f"\n🚘 {car_description}" if car_description else ""
    text = (
        f"{format_basic_details(from_city, to_city, dep_dt, arrival_time, from_points, to_points)}\n"
        f"💰 {price} грн | 👥 {seats} місць{phone_line}{car_line}\n"
        f"✅ Підтверджено: {confirmed_count} | ⏳ Очікують: {pending_count}"
    )
    rows = []

    pending_bookings = get_bookings_for_trip(trip_id, 'pending')
    if pending_bookings:
        text += "\n\n⏳ <b>Очікують:</b>"
        for booking_id, passenger_id, notes, pickup_at, booking_seats, passenger_phone in pending_bookings:
            try:
                passenger_chat = await bot.get_chat(passenger_id)
                passenger_name = passenger_chat.full_name
            except:
                passenger_name = "Пасажир"
            notes_line = format_notes_details_for_driver(notes, None, passenger_phone)
            text += f"\n👤 {passenger_name} ({booking_seats} міс.) {notes_line}"
            msg_url = f"https://t.me/{passenger_chat.username}" if (passenger_chat and passenger_chat.username) else f"tg://user?id={passenger_id}"
            rows.append([
                InlineKeyboardButton(text=f"✅ {passenger_name}", callback_data=f"confirm_booking:{booking_id}"),
                InlineKeyboardButton(text=f"❌ {passenger_name}", callback_data=f"reject_booking:{booking_id}"),
                InlineKeyboardButton(text="✉️", url=msg_url),
            ])

    confirmed_bookings = get_bookings_for_trip(trip_id, 'confirmed')
    if confirmed_bookings:
        text += "\n\n✅ <b>Підтверджені:</b>"
        for booking_id, passenger_id, notes, pickup_at, booking_seats, passenger_phone in confirmed_bookings:
            try:
                passenger_chat = await bot.get_chat(passenger_id)
                passenger_name = passenger_chat.full_name
            except:
                passenger_name = "Пасажир"
            notes_line = format_notes_details_for_driver(notes, pickup_at, passenger_phone)
            text += f"\n👤 {passenger_name} ({booking_seats} міс.){notes_line}"
            msg_url = f"https://t.me/{passenger_chat.username}" if (passenger_chat and passenger_chat.username) else f"tg://user?id={passenger_id}"
            rows.append([
                InlineKeyboardButton(text=f"❌ Скасувати {passenger_name}", callback_data=f"reject_booking:{booking_id}"),
                InlineKeyboardButton(text="✉️", url=msg_url),
            ])

    rows.append([InlineKeyboardButton(text="Скасувати поїздку ❌", callback_data=f"cancel_trip:{trip_id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    return text, kb


driver_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚗 Створити поїздку")],
        [KeyboardButton(text="📋 Мої поїздки водія")],
        [KeyboardButton(text="📜 Минулі поїздки")],
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
    modified_city = get_city_modified_name(city)
    suggestions = get_route_descriptions(city, True, message.from_user.id)
    keyboard = []
    if suggestions:
        for s in suggestions:
            keyboard.append([KeyboardButton(text=s)])
    if keyboard:
        kb = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)
    else:
        kb = ReplyKeyboardRemove()
    await message.answer(
        f"Допоможіть пасажирам зрозуміти ваш маршрут по {modified_city}: опишіть його в довільній формі " \
        f"або виберіть готовий опис внизу:" if keyboard else f"Допоможіть пасажирам зрозуміти ваш маршрут по {modified_city}: опишіть його в довільній формі:",
        reply_markup=kb
    )
    await state.set_state(DriverStates.from_points)

@router.message(DriverStates.from_points)
async def from_points(message: types.Message, state: FSMContext):
    data = await state.get_data()
    save_route_description(message.from_user.id, data["from_city"], True, message.text)
    await state.update_data(from_points=message.text)
    await message.answer("Місто прибуття:", reply_markup=cities_keyboard(message.from_user.id))
    await state.set_state(DriverStates.to_city)

@router.message(DriverStates.to_city)
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
    modified_city = get_city_modified_name(city)
    suggestions = get_route_descriptions(city, False, message.from_user.id)
    keyboard = []
    if suggestions:
        for s in suggestions:
            keyboard.append([KeyboardButton(text=s)])
    if keyboard:
        kb = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)
    else:
        kb = ReplyKeyboardRemove()
    await message.answer(
        f"Опишіть маршрут по {modified_city} в довільній формі, " \
        f"або виберіть готовий опис внизу:" if keyboard else f"Опишіть маршрут по {modified_city} в довільній формі:",
        reply_markup=kb
    )
    await state.set_state(DriverStates.to_points)

@router.message(DriverStates.to_points)
async def to_points(message: types.Message, state: FSMContext):
    data = await state.get_data()
    save_route_description(message.from_user.id, data["to_city"], False, message.text)
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

    now = datetime.datetime.now(tz=response.tzinfo)
    if response <= now:
        await message.answer("❌ Час відправлення має бути у майбутньому. Введіть знову:")
        return

    await message.answer(f"Вкажіть приблизний час прибуття в {data.get('to_city')} у форматі ГГ:ХХ:")
    await state.set_state(DriverStates.arrival_time)

@router.message(DriverStates.arrival_time)
async def arrival_time(message: types.Message, state: FSMContext):
    is_valid, error_msg = validate_time(message.text)
    if not is_valid:
        await message.answer(error_msg)
        return

    data = await state.get_data()
    is_valid, response = generate_datetime(data.get("day"), message.text)
    if not is_valid:
        await message.answer(response)
        return

    if response <= data.get("datetime"):
        await message.answer("❌ Час прибуття має бути пізніше часу відправлення. Введіть знову:")
        return

    await state.update_data(arrival_time=response)
    await message.answer("Місця:")
    await state.set_state(DriverStates.seats)

@router.message(DriverStates.seats)
async def seats(message: types.Message, state: FSMContext):
    await state.update_data(seats=message.text)
    await message.answer("Ціна за місце:")
    await state.set_state(DriverStates.price)

@router.message(DriverStates.price)
async def price(message: types.Message, state: FSMContext):
    await state.update_data(price=message.text)
    recent_cars = get_driver_recent_car_descriptions(message.from_user.id, limit=4)
    if recent_cars:
        keyboard = [[KeyboardButton(text=car)] for car in recent_cars]
        kb = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=True)
        await message.answer("Опишіть ваше авто, або виберіть готовий опис:", reply_markup=kb)
    else:
        await message.answer("Опишіть ваше авто, наприклад: Чорна Мазда 3, 9746")
    await state.set_state(DriverStates.car_description)


@router.message(DriverStates.car_description)
async def car_description(message: types.Message, state: FSMContext):
    await state.update_data(car_description=message.text)
    save_or_update_driver_car_description(message.from_user.id, message.text)
    
    recent_phones = get_recent_phone_numbers(message.from_user.id, limit=4)
    phone_kb_buttons = []
    if recent_phones:
        phone_kb_buttons.extend([[KeyboardButton(text=phone)] for phone in recent_phones])
    phone_kb_buttons.extend([
        [KeyboardButton(text="📱 Поділитися моїм номером з телеграму", request_contact=True)],
        [KeyboardButton(text="Не ділитися")],
    ])
    
    phone_kb = ReplyKeyboardMarkup(
        keyboard=phone_kb_buttons,
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(
        "Якщо хочете, поділіться номером телефону або напишіть вручну. Його бачитимуть лише пасажири, яких ви підтвердите.",
        reply_markup=phone_kb,
    )
    await state.set_state(DriverStates.phone)


@router.message(DriverStates.phone)
async def driver_phone(message: types.Message, state: FSMContext):
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

    await state.update_data(driver_phone=phone)
    data = await state.get_data()

    saved = save_trip_to_db(message.from_user.id, data)
    if not saved:
        await message.answer(
            "❌ У вас вже є активна поїздка в цей час.",
            reply_markup=driver_menu_kb
        )
        await state.clear()
        return

    await message.answer("Поїздка збережена ✅", reply_markup=driver_menu_kb)
    await state.clear()


@router.message(lambda m: m.text == "📋 Мої поїздки водія")
async def my_driver_trips(message: types.Message):
    trips = get_driver_trips(message.from_user.id)
    if not trips:
        await message.answer("У вас ще немає запланованих поїздок.")
        return

    for i, trip in enumerate(trips):
        if i > 0:
            await message.answer("*\n*\n*")
        text, kb = await _build_driver_trip_details_msg(trip, message.bot)
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


async def _build_past_driver_trip_details_msg(trip_row, bot, driver_id):
    trip_id, from_city, to_city, dep_dt, price, seats, status, confirmed_count, pending_count, arrival_time, from_points, to_points, driver_phone, car_description = trip_row
    status_label = "🚫 Скасована" if status == "cancelled" else "✅ Завершена"
    pos = get_driver_past_trip_position(driver_id, trip_id)
    position_line = f"🗓 Поїздка #{pos[0]} з {pos[1]}\n" if pos else ""
    phone_line = f"\n📞 Ваш телефон: {driver_phone}" if driver_phone else ""
    car_line = f"\n🚘 {car_description}" if car_description else ""
    text = (
        f"{position_line}{format_basic_details(from_city, to_city, dep_dt, arrival_time, from_points, to_points)}\n"
        f"💰 {price} грн | 👥 {seats} місць{phone_line}{car_line}\n"
        f"✅ Підтверджено: {confirmed_count} | ⏳ Не підтверджено: {pending_count} | {status_label}"
    )
    rows = []

    pending_bookings = get_bookings_for_trip(trip_id, 'pending')
    if pending_bookings:
        text += "\n\n⏳ <b>Не підтверджені:</b>"
        for booking_id, passenger_id, notes, pickup_at, booking_seats, passenger_phone in pending_bookings:
            try:
                passenger_chat = await bot.get_chat(passenger_id)
                passenger_name = passenger_chat.full_name
            except:
                passenger_name = "Пасажир"
            notes_line = format_notes_details_for_driver(notes, None, passenger_phone)
            text += f"\n👤 {passenger_name} ({booking_seats} міс.) {notes_line}"
            msg_url = f"https://t.me/{passenger_chat.username}" if (passenger_chat and passenger_chat.username) else f"tg://user?id={passenger_id}"
            rows.append([InlineKeyboardButton(text=f"✉️ {passenger_name}", url=msg_url)])

    confirmed_bookings = get_bookings_for_trip(trip_id, 'confirmed')
    if confirmed_bookings:
        text += "\n\n✅ <b>Підтверджені:</b>"
        for booking_id, passenger_id, notes, pickup_at, booking_seats, passenger_phone in confirmed_bookings:
            try:
                passenger_chat = await bot.get_chat(passenger_id)
                passenger_name = passenger_chat.full_name
            except:
                passenger_name = "Пасажир"
            notes_line = format_notes_details_for_driver(notes, pickup_at, passenger_phone)
            text += f"\n👤 {passenger_name} ({booking_seats} міс.){notes_line}"
            msg_url = f"https://t.me/{passenger_chat.username}" if (passenger_chat and passenger_chat.username) else f"tg://user?id={passenger_id}"
            rows.append([InlineKeyboardButton(text=f"✉️ {passenger_name}", url=msg_url)])

    nav_row = []
    if get_prev_driver_past_trip(driver_id, trip_id):
        nav_row.append(InlineKeyboardButton(text="⬅️ Попередня", callback_data=f"dh_prev:{trip_id}"))
    if get_next_driver_past_trip(driver_id, trip_id):
        nav_row.append(InlineKeyboardButton(text="Наступна ➡️", callback_data=f"dh_next:{trip_id}"))
    if nav_row:
        rows.append(nav_row)

    kb = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
    return text, kb


@router.message(lambda m: m.text == "📜 Минулі поїздки")
async def my_past_driver_trips(message: types.Message):
    trip = get_latest_driver_past_trip(message.from_user.id)
    if not trip:
        await message.answer("У вас ще немає минулих поїздок.")
        return
    text, kb = await _build_past_driver_trip_details_msg(trip, message.bot, message.from_user.id)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(lambda c: c.data and (c.data.startswith("dh_prev:") or c.data.startswith("dh_next:")))
async def driver_history_nav(callback: types.CallbackQuery, bot: Bot):
    action, trip_id_str = callback.data.split(":")
    current_trip_id = int(trip_id_str)
    driver_id = callback.from_user.id

    if action == "dh_prev":
        trip = get_prev_driver_past_trip(driver_id, current_trip_id)
    else:
        trip = get_next_driver_past_trip(driver_id, current_trip_id)

    if not trip:
        await callback.answer()
        return

    text, kb = await _build_past_driver_trip_details_msg(trip, bot, driver_id)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("cancel_trip:"))
async def cancel_trip_callback(callback: types.CallbackQuery, bot: Bot):
    trip_id = int(callback.data.split(":")[1])

    trip_details = get_trip_details(trip_id)
    if trip_details:
        arrival_dt = trip_details[3]
        if arrival_dt <= datetime.datetime.now(tz=arrival_dt.tzinfo):
            await callback.answer("❌ Не можливо скасувати поїздку, вона вже відбулась.", show_alert=True)
            return

    success, booking_ids = cancel_trip(trip_id, callback.from_user.id)

    if success:
        await callback.message.edit_text(callback.message.html_text + "\n\n🚫 Ви скасували цю поїздку", reply_markup=None, parse_mode="HTML")
        await callback.answer("")
        for booking_id in booking_ids:
            prev_status, _ = update_booking_status(booking_id, "trip_cancelled", ["pending", "confirmed", "rejected", "cancelled_by_passenger", "trip_cancelled"])
            if prev_status in ("pending", "confirmed"):
                passenger_id = get_passenger_id(booking_id)
                trip = get_trip_details_by_booking(booking_id)
                booking_desc = f"\n{format_booking_description_for_passenger(*trip)}" if trip else ""
                driver_phone = get_driver_phone_by_booking(booking_id) if prev_status == "confirmed" else None
                phone_line = f"\n📞 Номер водія: {driver_phone}" if driver_phone else ""
                await bot.send_message(passenger_id, f"❌ На жаль, водій скасував цю поїздку.{booking_desc}{phone_line}")
    else:
        await callback.message.edit_text(callback.message.html_text + "\n\n🚫 Ви вже скасували цю поїздку раніше", reply_markup=None, parse_mode="HTML")
        await callback.answer("")

@router.callback_query(lambda c: c.data.startswith("confirm_booking:"))
async def confirm_booking(callback: types.CallbackQuery, state: FSMContext):
    booking_id = int(callback.data.split(":")[1])

    await callback.answer()
    trip_id = get_trip_id_for_booking(booking_id)
    # Use cancel_trip do distinguish if we are confirming from view trip or P msg.
    from_trips_view = any(
        btn.callback_data and btn.callback_data.startswith("cancel_trip:")
        for row in (callback.message.reply_markup.inline_keyboard if callback.message.reply_markup else [])
        for btn in row
    )
    await state.update_data(
        confirming_booking_id=booking_id,
        confirming_trip_id=trip_id,
        confirming_from_trips_view=from_trips_view,
        confirming_message_id=callback.message.message_id,
        confirming_chat_id=callback.message.chat.id,
        confirming_message_text=callback.message.html_text
    )
    await state.set_state(DriverStates.confirming_booking)

    trip = get_trip_details_by_booking(booking_id)
    if trip:
        # trip is (from_city, to_city, dep_dt, notes)
        dep_dt = trip[2]
        arrival_dt = trip[5]
        local_dt = dep_dt.astimezone(ZoneInfo("Europe/Kiev"))
        arrival_local = arrival_dt.astimezone(ZoneInfo("Europe/Kiev"))

        def round_to_5(dt):
            total_mins = dt.hour * 60 + dt.minute
            rounded = round(total_mins / 5) * 5
            return dt.replace(hour=rounded // 60, minute=rounded % 60, second=0, microsecond=0)

        base = round_to_5(local_dt)
        candidates = [
            local_dt,
            base + datetime.timedelta(minutes=5),
            base + datetime.timedelta(minutes=10),
            base + datetime.timedelta(minutes=15),
            base + datetime.timedelta(minutes=20),
        ]
        times = [t.strftime("%H:%M") for t in candidates if t <= arrival_local]
        rows = [[KeyboardButton(text=t) for t in times[i:i+3]] for i in range(0, len(times), 3)]
        arrival_kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)
    else:
        arrival_kb = ReplyKeyboardRemove()

    await callback.message.answer(
        "⏱ Оберіть час коли ви будете біля цього пасажира, "
        "або введіть в форматі ГГ:ХХ:",
        reply_markup=arrival_kb
    )

@router.message(DriverStates.confirming_booking)
async def confirm_booking_notes(message: types.Message, state: FSMContext, bot: Bot):
    is_valid, error_msg = validate_time(message.text)
    if not is_valid:
        await message.answer(error_msg)
        return

    data = await state.get_data()
    booking_id = data["confirming_booking_id"]

    pickup_dt = None
    trip = get_trip_details_by_booking(booking_id)
    if trip:
        dep_dt = trip[2]
        arrival_dt = trip[5]
        local_date = dep_dt.astimezone(ZoneInfo("Europe/Kiev")).strftime("%Y-%m-%d")
        ok, pickup_dt = generate_datetime(local_date, message.text)
        if ok and not (dep_dt <= pickup_dt <= arrival_dt):
            dep_local = dep_dt.astimezone(ZoneInfo("Europe/Kiev")).strftime("%H:%M")
            arr_local = arrival_dt.astimezone(ZoneInfo("Europe/Kiev")).strftime("%H:%M")
            await message.answer(f"❌ Час має бути між {dep_local} та {arr_local}. Введіть знову:")
            return

    msg_id = data["confirming_message_id"]
    chat_id = data["confirming_chat_id"]
    trip_id = data.get("confirming_trip_id")
    from_trips_view = data.get("confirming_from_trips_view", False)
    original_text = data["confirming_message_text"]
    await state.clear()

    prev_status, _ = update_booking_status(booking_id, "confirmed", ["pending"])
    if prev_status == "pending":
        set_booking_pickup_at(booking_id, pickup_dt)
        updated_trip = get_driver_trip_by_id(trip_id) if (trip_id and from_trips_view) else None
        if updated_trip:
            # if trip_id - we got here from my_driver_trips, so we need to rebuild the message with updated booking counts
            new_text, new_kb = await _build_driver_trip_details_msg(updated_trip, bot)
            await bot.edit_message_text(new_text, chat_id=chat_id, message_id=msg_id, reply_markup=new_kb, parse_mode="HTML")
        else:
            # if no trip_id - we got here from the direct booking confirmation msg, so we just append the confirmation note to the existing message
            await bot.edit_message_text(original_text + "\n\n✅ Ви підтвердили бронювання", chat_id=chat_id, message_id=msg_id, reply_markup=None, parse_mode="HTML")
        await message.answer("✅ Бронювання підтверджено.", reply_markup=driver_menu_kb)
        passenger_id = get_passenger_id(booking_id)
        driver_phone = get_driver_phone_by_booking(booking_id)
        if trip:
            phone_line = f"\n📞 Номер водія: {driver_phone}" if driver_phone else ""
            msg = f"✅ Водій підтвердив вашу бронь!\n{format_booking_description_for_passenger(trip[0], trip[1], trip[2], trip[3], pickup_dt, trip[5], trip[6], trip[7], trip[8], trip[9])}{phone_line}\nВдалої поїздки!"
        else:
            msg = "✅ Водій підтвердив вашу бронь! Вдалої поїздки!"
        await bot.send_message(passenger_id, msg)
    elif prev_status == "confirmed":
        await message.answer("Ви вже підтвердили це бронювання раніше")
    elif prev_status == "rejected":
        await message.answer("Ви вже відхилили це бронювання раніше")
    elif prev_status == "trip_cancelled":
        await message.answer("Ви вже скасували цю поїздку раніше")
    elif prev_status == "cancelled_by_passenger":
        await message.answer("Пасажир вже скасував це бронювання")
    else:
        await message.answer(f"Бронювання недоступне ({prev_status})")

@router.callback_query(lambda c: c.data.startswith("reject_booking:"))
async def reject_booking(callback: types.CallbackQuery, bot: Bot):
    booking_id = int(callback.data.split(":")[1])

    trip = get_trip_details_by_booking(booking_id)
    if trip:
        arrival_dt = trip[5]
        if arrival_dt <= datetime.datetime.now(tz=arrival_dt.tzinfo):
            await callback.answer("❌ Не можливо відхилити бронювання, поїздка вже відбулась.", show_alert=True)
            return

    trip_id = get_trip_id_for_booking(booking_id)
    from_trips_view = any(
        btn.callback_data and btn.callback_data.startswith("cancel_trip:")
        for row in (callback.message.reply_markup.inline_keyboard if callback.message.reply_markup else [])
        for btn in row
    )
    prev_status, new_status = update_booking_status(booking_id, "rejected", ["pending", "confirmed"])

    async def _rebuild_or_append(suffix: str):
        updated_trip = get_driver_trip_by_id(trip_id) if (trip_id and from_trips_view) else None
        if updated_trip:
            new_text, new_kb = await _build_driver_trip_details_msg(updated_trip, bot)
            await callback.message.edit_text(new_text, reply_markup=new_kb, parse_mode="HTML")
        else:
            await callback.message.edit_text(callback.message.html_text + suffix, reply_markup=None, parse_mode="HTML")

    if prev_status == "pending":
        await callback.answer()
        await _rebuild_or_append("\n\n❌ Ви відмовили цьому пасажиру")
        passenger_id = get_passenger_id(booking_id)
        booking_desc = f"\n{format_booking_description_for_passenger(*trip)}" if trip else ""
        await bot.send_message(passenger_id, f"❌ Вибачте, водій відмовив у бронюванні поїздки.{booking_desc}")
    elif prev_status == "confirmed":
        await callback.answer()
        await _rebuild_or_append("\n\n❌ Ви скасували це бронювання")
        passenger_id = get_passenger_id(booking_id)
        driver_phone = get_driver_phone_by_booking(booking_id)
        booking_desc = f"\n{format_booking_description_for_passenger(*trip)}" if trip else ""
        phone_line = f"\n📞 Номер водія: {driver_phone}" if driver_phone else ""
        await bot.send_message(passenger_id, f"❌ Вибачте, водій скасував ваше бронювання.{booking_desc}{phone_line}")
    elif prev_status == "rejected":
        await callback.answer("❌ Ви вже відхилили це бронювання раніше", show_alert=True)
    elif prev_status == "trip_cancelled":
        await callback.answer("❌ Ви вже скасували цю поїздку раніше", show_alert=True)
    elif prev_status == "cancelled_by_passenger":
        await callback.answer("❌ Пасажир вже скасував це бронювання раніше", show_alert=True)
    else:
        await callback.answer(f"❌ Бронювання недоступне ({prev_status})", show_alert=True)

