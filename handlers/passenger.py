from email import message
import logging

from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from states.passenger_states import PassengerStates
from database import search_trips_ids, book_trip, check_trip_bookable, get_driver_id, get_driver_id_by_booking, get_trip_details, get_trip_details_by_booking, get_passenger_phone_by_booking, get_passenger_bookings, get_passenger_booking_ids, get_passenger_booking_by_id, get_latest_passenger_past_booking, get_prev_passenger_past_booking, get_next_passenger_past_booking, get_passenger_past_booking_position, update_booking_status, get_recent_phone_numbers, save_or_update_phone_number, save_recent_search, get_recent_search_times, get_city_modified_name, upsert_user_details, get_recent_booking_notes, get_recent_searches, save_search_subscription, get_active_subscriptions, deactivate_subscription, get_subscription_cities
from database import create_trip_search_list, get_current_trip_from_search_list, increase_trip_search_list_index, decrease_trip_search_list_index, set_trip_search_list_index, get_search_list_times, get_trip_search_list_ids, get_trip_for_display
from database import increment_city_popularity, add_city_if_missing
from handlers.passenger_search import search_and_display
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.exceptions import TelegramBadRequest
from keyboards.city_kb import cities_keyboard
from keyboards.booking_kb import booking_actions_kb
from aiogram.types import ReplyKeyboardRemove
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Bot
import asyncio
import datetime
from zoneinfo import ZoneInfo
from handlers.common import generate_quick_days, quick_day_kb, validate_time, validate_city_name, generate_datetime, format_basic_details, format_booking_description_for_driver, format_booking_description_for_passenger, back_only_kb, searching_kb, safe_answer, safe_send, seats_word, mask_phone, format_trip, trip_keyboard, send_trip_message, driver_menu_kb, to_local_day_and_time
from data.route_intermediates import get_search_city_pairs, get_travel_time_between
from config import ADMIN_CHAT_ID

router = Router()

STATUS_LABELS = {
    "pending": "⏳ Очікує підтвердження водієм",
    "confirmed": "✅ Підтверджено водієм",
    "rejected": "❌ Відхилено водієм",
    "cancelled_by_passenger": "🚫 Ви скасували ваше бронювання",
    "trip_cancelled": "🚫 Водій скасував цю поїздку"
}

BOOK_ERRORS = {
    "not_found":     "❌ Поїздку не знайдено. Спробуйте знайти іншу.",
    "cancelled":     "❌ Водій скасував цю поїздку. Спробуйте знайти іншу.",
    "departed":      "❌ Ця поїздка вже відправилась. Спробуйте знайти іншу.",
    "no_seats":      "❌ На жаль, хтось щойно зайняв вільні місця. Спробуйте знайти іншу поїздку.",
    "overlap":       "❌ У вас вже є активне бронювання на цей час. Можете його скасувати і спробувати ще раз.",
    "already_booked_pending":   "❌ Ви вже забронювали цю поїздку, але водій ще не підтвердив.",
    "already_booked_confirmed": "❌ Ви вже забронювали цю поїздку, водій підтвердив.",
}

def _is_admin(user_id: int) -> bool:
    return user_id == int(ADMIN_CHAT_ID)

def passenger_menu_kb(user_id: int) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🔎 Знайти поїздку")],
        [KeyboardButton(text="🔔 Сповіщення про нові поїздки")],
    ]
    rows += [
        [KeyboardButton(text="📋 Поточні бронювання")],
        [KeyboardButton(text="📜 Минулі бронювання")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def after_search_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🔔 Сповістити про нові поїздки")],
        [KeyboardButton(text="⬅️ Назад")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

@router.message(lambda m: m.text == "👤 Я пасажир")
async def passenger_menu(message: types.Message):
    await message.answer(
        "Меню пасажира:",
        reply_markup=passenger_menu_kb(message.from_user.id)
    )

async def _build_passenger_booking_msg(booking_row, bot, booking_ids=None):
    booking_id, trip_id, from_city, to_city, dep_dt, price, seats, status, driver_id, notes, pickup_at, arrival_time, booked_seats, from_points, to_points, driver_phone, passenger_phone, car_description, booking_from_city, booking_to_city = booking_row
    ids = [bid for bid, _ in booking_ids] if booking_ids else []
    position_line = ""
    if len(ids) > 1:
        idx = ids.index(booking_id) if booking_id in ids else 0
        position_line = f"#{idx + 1} з {len(ids)}\n"
    status_label = STATUS_LABELS.get(status, status)
    try:
        driver_chat = await bot.get_chat(driver_id)
        driver_name = driver_chat.full_name
    except:
        driver_chat = None
        driver_name = "Водій"
    if driver_phone and status == "confirmed":
        display_phone = driver_phone
    elif driver_phone:
        display_phone = mask_phone(driver_phone)
    else:
        display_phone = None
    booking_desc = format_booking_description_for_passenger(from_city, to_city, dep_dt, notes, pickup_at if status != "pending" else None, arrival_time, booked_seats, from_points, to_points, car_description, booking_from_city=booking_from_city, booking_to_city=booking_to_city, driver_phone=display_phone, price=price, driver_name=driver_name)
    text = f"{position_line}{status_label}\n\n{booking_desc}"
    rows = []
    driver_url = f"https://t.me/{driver_chat.username}" if (driver_chat and driver_chat.username) else f"tg://user?id={driver_id}"
    rows.append([InlineKeyboardButton(text="✉️ Написати водію", url=driver_url)])
    if len(ids) > 1:
        rows.append([
            InlineKeyboardButton(text="⬅️ Попереднє", callback_data=f"pb_prev:{booking_id}"),
            InlineKeyboardButton(text="Наступне ➡️", callback_data=f"pb_next:{booking_id}"),
        ])
    rows.append([InlineKeyboardButton(text="Скасувати бронювання ❌", callback_data=f"cancel_booking:{booking_id}")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(lambda m: m.text == "📋 Поточні бронювання")
async def my_trips(message: types.Message, state: FSMContext):
    await message.answer("Шукаємо...", reply_markup=back_only_kb)
    await state.set_state(PassengerStates.viewing_bookings)
    booking_ids = get_passenger_booking_ids(message.from_user.id)
    active_booking_ids = [(bid, st) for bid, st in booking_ids if st in ("pending", "confirmed")]
    first_id = active_booking_ids[0][0] if active_booking_ids else None
    if first_id is None:
        await message.answer("У вас ще немає заброньованих поїздок.", reply_markup=back_only_kb)
        return
    booking = get_passenger_booking_by_id(first_id)
    text, kb = await _build_passenger_booking_msg(booking, message.bot, booking_ids=active_booking_ids)
    await safe_send(message.answer, text, kb)


@router.callback_query(lambda c: c.data and c.data.startswith("show_passenger_booking:"))
async def show_passenger_booking(callback: types.CallbackQuery, bot: Bot):
    booking_id = int(callback.data.split(":")[1])
    passenger_id = callback.from_user.id
    booking_ids = get_passenger_booking_ids(passenger_id)
    active_booking_ids = [(bid, st) for bid, st in booking_ids if st in ("pending", "confirmed")]
    booking = get_passenger_booking_by_id(booking_id)
    if not booking:
        await safe_answer(callback)
        return
    if booking[7] != "confirmed":
        await callback.message.answer("🚫 Це бронювання вже скасовано водійєм.", reply_markup=back_only_kb)
        await safe_answer(callback)
        return
    await callback.message.answer("Відкриваємо бронювання...", reply_markup=back_only_kb)
    await asyncio.sleep(2)
    text, kb = await _build_passenger_booking_msg(booking, bot, booking_ids=active_booking_ids)
    await safe_send(callback.message.answer, text, kb)
    await safe_answer(callback)


@router.callback_query(lambda c: c.data and (c.data.startswith("pb_prev:") or c.data.startswith("pb_next:")))
async def passenger_bookings_nav(callback: types.CallbackQuery, bot: Bot):
    action, current_id_str = callback.data.split(":")
    current_id = int(current_id_str)
    passenger_id = callback.from_user.id
    booking_ids = get_passenger_booking_ids(passenger_id)
    active_booking_ids = [(bid, st) for bid, st in booking_ids if st in ("pending", "confirmed")]
    active_ids = [bid for bid, _ in active_booking_ids]
    if not active_ids:
        await callback.message.edit_text("У вас ще немає заброньованих поїздок.", reply_markup=None)
        await safe_answer(callback)
        return
    all_ids = [bid for bid, _ in booking_ids]
    if current_id not in all_ids:
        booking_id = active_ids[0]
    elif action == "pb_prev":
        cur_pos = all_ids.index(current_id)
        booking_id = next(
            (bid for bid, st in reversed(booking_ids[:cur_pos]) if st in ("pending", "confirmed")),
            active_ids[0]
        )
    else:
        cur_pos = all_ids.index(current_id)
        booking_id = next(
            (bid for bid, st in booking_ids[cur_pos + 1:] if st in ("pending", "confirmed")),
            active_ids[-1]
        )
    booking = get_passenger_booking_by_id(booking_id)
    text, kb = await _build_passenger_booking_msg(booking, bot, booking_ids=active_booking_ids)
    await safe_send(callback.message.edit_text, text, kb)
    await safe_answer(callback)

@router.message(lambda m: m.text == "📜 Минулі бронювання")
async def my_past_trips(message: types.Message, state: FSMContext):
    await message.answer("Шукаємо...", reply_markup=back_only_kb)
    await state.set_state(PassengerStates.viewing_bookings)
    # await asyncio.sleep(3)
    booking = get_latest_passenger_past_booking(message.from_user.id)
    if not booking:
        await message.answer("У вас ще немає завершених поїздок.")
        return
    text, kb = await _build_past_passenger_booking_msg(booking, message.bot, message.from_user.id)
    await safe_send(message.answer, text, kb)


@router.message(lambda m: m.text == "🔔 Сповіщення про нові поїздки")
async def my_subscriptions(message: types.Message):
    subs = get_active_subscriptions(message.from_user.id)
    if not subs:
        await message.answer("У вас немає активних сповіщень. Почніть пошук і зможете створити сповіщення.", reply_markup=passenger_menu_kb(message.from_user.id))
        return
    await message.answer("Ми сповістимо вас коли з'являться нові поїздки з такими параметрами:", reply_markup=passenger_menu_kb(message.from_user.id))
    kyiv = ZoneInfo("Europe/Kyiv")
    for sub_id, from_city, to_city, search_for_day, seats, from_time, to_time in subs:
        from_hhmm = from_time.astimezone(kyiv).strftime("%H:%M")
        to_hhmm = to_time.astimezone(kyiv).strftime("%H:%M")
        text = f"🔔 {from_city} → {to_city}\n{_day_label(search_for_day)}, {from_hhmm}–{to_hhmm}, {seats} {seats_word(seats)}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Скасувати ❌", callback_data=f"unsub:{sub_id}")]
        ])
        await message.answer(text, reply_markup=kb)

@router.callback_query(lambda c: c.data and c.data.startswith("unsub:"))
async def unsubscribe_handler(callback: types.CallbackQuery):
    sub_id = int(callback.data.split(":")[1])
    deactivate_subscription(sub_id, callback.from_user.id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.edit_text(callback.message.text + "\n\n🚫 Сповіщення скасовано")
    await callback.answer()


async def _build_past_passenger_booking_msg(booking_row, bot, passenger_id):
    booking_id, from_city, to_city, dep_dt, price, status, driver_id, notes, pickup_at, arrival_time, booked_seats, from_points, to_points, driver_phone, passenger_phone, car_description, booking_from_city, booking_to_city = booking_row
    status_label = STATUS_LABELS.get(status, status)
    pos = get_passenger_past_booking_position(passenger_id, booking_id)
    position_line = f"🗓 Бронювання #{pos[0]} з {pos[1]}\n" if pos else ""
    try:
        driver_chat = await bot.get_chat(driver_id)
        driver_name = driver_chat.full_name
    except:
        driver_chat = None
        driver_name = "Водій"
    if driver_phone and status == "confirmed":
        display_phone = driver_phone
    elif driver_phone:
        display_phone = mask_phone(driver_phone)
    else:
        display_phone = None
    board_time = pickup_at or (dep_dt + datetime.timedelta(minutes=get_travel_time_between(from_city, booking_from_city)) if booking_from_city else None)
    booking_desc = format_booking_description_for_passenger(from_city, to_city, dep_dt, notes, board_time, arrival_time, booked_seats, from_points, to_points, car_description, booking_from_city=booking_from_city, booking_to_city=booking_to_city, driver_phone=display_phone, price=price, driver_name=driver_name)
    # passenger_phone_line = f"\n📱 Ваш телефон: {passenger_phone}" if passenger_phone else ""
    text = f"{position_line}{status_label}\n\n{booking_desc}"

    rows = []
    if driver_chat:
        driver_url = f"https://t.me/{driver_chat.username}" if driver_chat.username else f"tg://user?id={driver_id}"
        rows.append([InlineKeyboardButton(text="✉️ Написати водію", url=driver_url)])

    nav_row = []
    if get_prev_passenger_past_booking(passenger_id, booking_id):
        nav_row.append(InlineKeyboardButton(text="⬅️ Попереднє", callback_data=f"ph_prev:{booking_id}"))
    if get_next_passenger_past_booking(passenger_id, booking_id):
        nav_row.append(InlineKeyboardButton(text="Наступне ➡️", callback_data=f"ph_next:{booking_id}"))
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
        await safe_answer(callback)
        return

    text, kb = await _build_past_passenger_booking_msg(booking, bot, passenger_id)
    await safe_send(callback.message.edit_text, text, kb)
    await safe_answer(callback)


@router.message(StateFilter(PassengerStates), lambda m: m.text == "⬅️ Назад")
async def passenger_flow_back(message: types.Message, state: FSMContext):
    data = await state.get_data()
    trip_message_id = data.get("trip_message_id")
    if trip_message_id:
        try:
            await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=trip_message_id, reply_markup=None)
        except Exception as e:
            logging.warning("Failed to clear trip message reply markup: %s", e)
    sub_kb_message_id = data.get("subscription_kb_message_id")
    if sub_kb_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=sub_kb_message_id)
        except Exception as e:
            logging.warning("Failed to delete subscription kb message: %s", e)
    await state.clear()
    await message.answer("Меню пасажира:", reply_markup=passenger_menu_kb(message.from_user.id))

def _format_day(date_str: str) -> str:
    day_map = {d: label.split()[0] for label, d in generate_quick_days()}
    return day_map.get(date_str, date_str)

def _recent_search_label(from_city, to_city, search_for_day, time_str, seats_requested) -> str:
    display_time = "показати всі" if time_str == "show_all" else time_str
    seats_label = f", {seats_requested} {seats_word(seats_requested)}" if seats_requested >= 1 else ""
    return f"🔁 {from_city} → {to_city}\n{_format_day(search_for_day)}{seats_label}"

@router.message(lambda m: m.text == "🔎 Знайти поїздку")
async def find_trip(message: types.Message, state: FSMContext):
    upsert_user_details(message.from_user.id, message.from_user.full_name)
    now_kyiv = datetime.datetime.now(tz=ZoneInfo("Europe/Kyiv"))
    today = now_kyiv.strftime("%Y-%m-%d")
    now_hhmm = now_kyiv.strftime("%H:%M")
    def _not_expired(r):
        _, _, search_for_day, time_str, _ = r
        if search_for_day < today:
            return False
        if search_for_day == today and ("23:59" if time_str == "show_all" else time_str) <= now_hhmm:
            return False
        return True
    all_recent = get_recent_searches(message.from_user.id)
    recent = sorted([r for r in all_recent if _not_expired(r)][:1], key=lambda r: (r[2], r[3]))
    # unique_routes = list(dict.fromkeys((r[0], r[1]) for r in all_recent))[:2]

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
    if recent:
        buttons = []
        for from_city, to_city, search_for_day, time_str, seats_requested in recent:
            label = _recent_search_label(from_city, to_city, search_for_day, time_str, seats_requested)
            buttons.append([KeyboardButton(text=label)])
        buttons.append([KeyboardButton(text="🔍 Новий пошук")])
        buttons.append([KeyboardButton(text="⬅️ Назад")])
        await state.update_data(recent_searches=recent)
        await state.set_state(PassengerStates.quick_search_or_new)
        await message.answer(
            "Хочете повторити пошук чи почати новий?",
            reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
        )
    # elif unique_routes:
    #     buttons = []
    #     for from_city, to_city in unique_routes:
    #         buttons.append([KeyboardButton(text=f"🔄 {from_city} → {to_city}")])
    #     buttons.append([KeyboardButton(text="🔍 Новий пошук")])
    #     buttons.append([KeyboardButton(text="⬅️ Назад")])
    #     await state.set_state(PassengerStates.quick_partial_search_or_new)
    #     await message.answer(
    #         "Хочете повторити пошук чи почати новий?",
    #         reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    #     )
    else:
        await state.set_state(PassengerStates.from_city)
        await message.answer(
            "Оберіть місто відправлення зі списку. Не знайшлось? Введіть вручну:",
            reply_markup=cities_keyboard(message.from_user.id)
        )

@router.message(PassengerStates.quick_partial_search_or_new, lambda m: m.text and m.text.startswith("🔄 "))
async def quick_route_select(message: types.Message, state: FSMContext):
    parts = message.text[2:].strip().split(" → ", 1)
    if len(parts) != 2:
        await message.answer("Не вдалося розпізнати пошук.")
        return
    from_city, to_city = parts[0].strip(), parts[1].strip()
    await state.update_data(booking_from_city=from_city, booking_to_city=to_city)
    await state.set_state(PassengerStates.day)
    await message.answer("Оберіть день:", reply_markup=quick_day_kb())

@router.message(StateFilter(PassengerStates.quick_search_or_new, PassengerStates.quick_partial_search_or_new), lambda m: m.text == "🔍 Новий пошук")
async def quick_search_new(message: types.Message, state: FSMContext):
    await state.set_state(PassengerStates.from_city)
    await message.answer(
        "Оберіть місто відправлення зі списку. Не знайшлось? Введіть вручну:",
        reply_markup=cities_keyboard(message.from_user.id)
    )

@router.message(PassengerStates.quick_search_or_new, lambda m: m.text and m.text.startswith("🔁 "))
async def quick_search_select(message: types.Message, state: FSMContext):
    data = await state.get_data()
    recent_searches = data.get("recent_searches", [])
    matched = None
    for row in recent_searches:
        from_city, to_city, search_for_day, time_str, seats_requested = row
        label = _recent_search_label(from_city, to_city, search_for_day, time_str, seats_requested)
        if message.text == label:
            matched = row
            break
    if not matched:
        await state.clear()
        await message.answer("Не вдалося розпізнати пошук.", reply_markup=passenger_menu_kb(message.from_user.id))
        return
    from_city, to_city, search_for_day, time_str, seats_requested = matched
    await state.update_data(
        booking_from_city=from_city,
        booking_to_city=to_city,
        day=search_for_day,
        seats_requested=seats_requested,
    )
    await state.set_state(PassengerStates.search_from_datetime)
    await _run_search(message, state, "Показати всі поїздки" if time_str == "show_all" else time_str)

@router.message(PassengerStates.from_city)
async def from_city(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("Будь ласка, введіть назву міста текстом:")
        return
    if message.text.startswith("───"):
        await message.answer("Будь ласка, оберіть місто зі списку або введіть вручну.")
        return
    is_valid, error_msg = validate_city_name(message.text)
    if not is_valid:
        await message.answer(error_msg)
        return
    city = message.text.title()
    await state.update_data(booking_from_city=city)
    increment_city_popularity(message.from_user.id, city)
    add_city_if_missing(city)
    await message.answer("Місто прибуття:", reply_markup=cities_keyboard(message.from_user.id))
    await state.set_state(PassengerStates.to_city)

@router.message(PassengerStates.to_city)
async def to_city(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("Будь ласка, введіть назву міста текстом:")
        return
    if message.text.startswith("───"):
        await message.answer("Будь ласка, оберіть місто зі списку або введіть вручну.")
        return
    is_valid, error_msg = validate_city_name(message.text)
    if not is_valid:
        await message.answer(error_msg)
        return
    city = message.text.title()
    data = await state.get_data()
    if city == data.get("booking_from_city"):
        await message.answer("Місто прибуття не може збігатися з містом відправлення. Оберіть інше місто:")
        return
    await state.update_data(booking_to_city=city)
    increment_city_popularity(message.from_user.id, city)
    add_city_if_missing(city)
    await message.answer("Оберіть день:", reply_markup=quick_day_kb())
    await state.set_state(PassengerStates.day)

@router.message(PassengerStates.day)
async def day_handler(message: types.Message, state: FSMContext):
    quick_days = generate_quick_days()
    day_dict = {label: date_str for label, date_str in quick_days}
    if message.text not in day_dict:
        await message.answer("Оберіть день зі списку.")
        return
    day = day_dict[message.text]
    await state.update_data(day=day)
    await message.answer("👥 Скільки місць вам потрібно?", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=str(i))] for i in range(1, 5)] + [[KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True,
        one_time_keyboard=True
    ))
    await state.set_state(PassengerStates.seats_requested)

@router.message(PassengerStates.seats_requested)
async def seats_requested_handler(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit() or int(message.text) < 1:
        await message.answer("Введіть ціле число, наприклад 1:")
        return
    seats = int(message.text)
    await state.update_data(seats_requested=seats)
    await _run_search(message, state, "Показати всі поїздки")

QUICK_TIME_OPTIONS = [30, 90]


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
            base = now_kyiv.replace(minute=(now_kyiv.minute // 30) * 30, second=0, microsecond=0)
            options = []
            for minutes in QUICK_TIME_OPTIONS:
                option_time = base + datetime.timedelta(minutes=minutes)
                if option_time.date() == base.date():
                    options.append([KeyboardButton(text=option_time.strftime("%H:%M"))])
    options.append([KeyboardButton(text="Показати всі поїздки")])
    options.append([KeyboardButton(text="⬅️ Назад")])
    return ReplyKeyboardMarkup(keyboard=options, resize_keyboard=True, one_time_keyboard=True)


async def _run_search(message: types.Message, state: FSMContext, time_str: str, jump_to_trip_id: int = None, user_id: int = None):
    if user_id is None:
        user_id = message.from_user.id
    now_kyiv = datetime.datetime.now(ZoneInfo('Europe/Kyiv'))
    data = await state.get_data()

    # if _is_admin(message.from_user.id):
    #     await search_and_display(message, data["booking_from_city"], data["booking_to_city"], data.get("day"), data.get("seats_requested", 1), state=state)
    #     await state.set_state(PassengerStates.browsing_trip_list)
    #     return

    selected_day = data.get("day")
    is_today = selected_day == now_kyiv.strftime("%Y-%m-%d")
    kyiv_end_of_day = now_kyiv.replace(hour=23, minute=59, second=59, microsecond=0)
    kyiv_next_day = now_kyiv + datetime.timedelta(days=1)

    if time_str == "Показати всі поїздки":
        if is_today:
            kyiv_from, kyiv_to = now_kyiv, kyiv_end_of_day
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
            now_utc = now_kyiv.astimezone(datetime.timezone.utc)
            utc_from = max(utc_from, now_utc)
            utc_to = max(min(utc_to, kyiv_end_of_day.astimezone(datetime.timezone.utc)), now_utc + datetime.timedelta(hours=1))
        else:
            utc_from = max(utc_from, kyiv_next_day.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(datetime.timezone.utc))
            utc_to = min(utc_to, kyiv_next_day.replace(hour=23, minute=59, second=59, microsecond=0).astimezone(datetime.timezone.utc))

    await state.update_data(search_from_datetime=utc_from, search_to_datetime=utc_to, last_time_str=time_str)

    data = await state.get_data()
    seats = data.get("seats_requested", 1)
    search_from_datetime = data["search_from_datetime"]
    search_to_datetime = data["search_to_datetime"]
    await message.answer(
        f"🔎 Шукаємо поїздки... \n{'Сьогодні' if is_today else 'Завтра'}\n"
        f"{data['booking_from_city']} → {data['booking_to_city']}\n"
        # f"з {search_from_datetime.astimezone(ZoneInfo('Europe/Kyiv')).strftime('%H:%M')} до {search_to_datetime.astimezone(ZoneInfo('Europe/Kyiv')).strftime('%H:%M')}\n"
        f"{seats} {seats_word(seats)}",
        reply_markup=searching_kb
    )
    await asyncio.sleep(3)

    extra_from, extra_to = get_search_city_pairs(data["booking_from_city"], data["booking_to_city"])
    all_trips = search_trips_ids(data["booking_from_city"], data["booking_to_city"], search_from_datetime, search_to_datetime, extra_from_cities=extra_from, extra_to_cities=extra_to)
    total = len(all_trips)
    passenger_from_city = data["booking_from_city"]
    available = [(t_id, boarding_dt) for t_id, free_seats, boarding_dt in all_trips if free_seats >= seats]
    save_recent_search(user_id, passenger_from_city, data["booking_to_city"], time_str if time_str != "Показати всі поїздки" else "show_all", data.get("day"), [t_id for t_id, *_ in all_trips], seats_requested=seats)

    def trip_word(n):
        last2, last1 = n % 100, n % 10
        if 11 <= last2 <= 14:
            return "поїздок"
        if last1 == 1:
            return "поїздку"
        if 2 <= last1 <= 4:
            return "поїздки"
        return "поїздок"

    if jump_to_trip_id and jump_to_trip_id not in [t_id for t_id, _ in available]:
        await message.answer("На жаль, ця поїздка вже недоступна.", reply_markup=after_search_kb())
        await state.set_state(PassengerStates.browsing_trips)
        return

    if not available:
        if total == 0:
            await message.answer(f"Поїздок не знайдено, спробуйте пізніше.", reply_markup=after_search_kb())
        else:
            await message.answer(f"Знайдено {total} {trip_word(total)}, але вільних місць вже немає.", reply_markup=after_search_kb())
        await state.set_state(PassengerStates.browsing_trips)
        return

    if total == len(available):
        await message.answer(f"Знайдено {total} {trip_word(total)}.", reply_markup=after_search_kb())
    else:
        await message.answer(f"Знайдено {total} {trip_word(total)}, вільні місця є в {len(available)}", reply_markup=after_search_kb())
    trips_ids = [t_id for t_id, _ in available]
    boarding_dts = [boarding_dt for _, boarding_dt in available]
    create_trip_search_list(user_id, trips_ids, boarding_dts, passenger_from_city)
    if jump_to_trip_id and jump_to_trip_id in trips_ids:
        set_trip_search_list_index(user_id, trips_ids.index(jump_to_trip_id))
    # This can come as expired, very unlikely.
    trip, index, total_cnt = get_current_trip_from_search_list(user_id)

    driver_chat = None
    try:
        driver_chat = await message.bot.get_chat(trip[1])
        driver_name = driver_chat.full_name
    except:
        driver_name = None

    trip_text = format_trip(trip, index, total_cnt, driver_name, is_own=(trip[1] == user_id), passenger_from_city=passenger_from_city, board_time=boarding_dts[index] if boarding_dts else None)
    trip_message = await send_trip_message(message.answer, trip_text, trip[0], total_cnt, trip[1], driver_chat.username if driver_chat else None, index, all_times=boarding_dts)

    await state.set_state(PassengerStates.browsing_trips)
    await state.update_data(trip_message_id=trip_message.message_id)

@router.message(lambda m: m.text == "...")
async def searching_noop(message: types.Message):
    pass

@router.message(PassengerStates.search_from_datetime)
async def search(message: types.Message, state: FSMContext):
    if not message.text:
        return
    time_str = message.text if message.text == "Показати всі поїздки" else message.text.zfill(5)
    if time_str != "Показати всі поїздки":
        is_valid, result = validate_time(time_str)
        if not is_valid:
            await message.answer(result)
            return
        time_str = result
    await _run_search(message, state, time_str)

@router.message(PassengerStates.browsing_trips, lambda m: m.text == "🔄 Зворотній маршрут")
async def switch_cities_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    from_city = data.get("booking_from_city")
    to_city = data.get("booking_to_city")
    time_str = data.get("last_time_str", "Показати всі поїздки")
    await state.update_data(booking_from_city=to_city, booking_to_city=from_city)
    await _run_search(message, state, time_str)

@router.message(PassengerStates.browsing_trips, lambda m: m.text == "🕐 Змінити час")
async def change_time_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    recent_times = get_recent_search_times(message.from_user.id, data["booking_from_city"], data["booking_to_city"], data["day"])
    await state.set_state(PassengerStates.search_from_datetime)
    await message.answer(
        "Введіть бажаний час виїзду у форматі ГГ:ХХ або оберіть один із варіантів:",
        reply_markup=quick_time_kb(data["day"], recent_times)
    )

SUBSCRIPTION_TIMES = ["00:00", "05:00", "06:00", "07:00", "08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00", "20:00", "21:00", "22:00", "23:59"]

def _day_label(day: str) -> str:
    kyiv = ZoneInfo("Europe/Kyiv")
    today = datetime.datetime.now(tz=kyiv).date()
    if day == today.strftime("%Y-%m-%d"):
        return "сьогодні"
    if day == (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d"):
        return "завтра"
    return day

def _subscription_inline_kb(selected=None, day: str = None):
    selected = selected or []
    if len(selected) == 2:
        lo = min(SUBSCRIPTION_TIMES.index(selected[0]), SUBSCRIPTION_TIMES.index(selected[1]))
        hi = max(SUBSCRIPTION_TIMES.index(selected[0]), SUBSCRIPTION_TIMES.index(selected[1]))
        highlighted = set(SUBSCRIPTION_TIMES[lo:hi + 1])
    else:
        highlighted = set(selected)
    kyiv = ZoneInfo("Europe/Kyiv")
    now_kyiv = datetime.datetime.now(tz=kyiv)
    today_str = now_kyiv.strftime("%Y-%m-%d")
    is_today = (day == today_str) if day else False
    current_hour = now_kyiv.strftime("%H:00")
    if is_today:
        first_future_idx = next((i for i, t in enumerate(SUBSCRIPTION_TIMES) if t >= current_hour), len(SUBSCRIPTION_TIMES))
        if SUBSCRIPTION_TIMES[first_future_idx] > current_hour:
            first_future_idx -= 1
        boundary_idx = first_future_idx
    else:
        boundary_idx = 0
    def make_btn(t, idx):
        if idx < boundary_idx:
            return InlineKeyboardButton(text="🔵 **:**" if t in highlighted else "**:**", callback_data="sub_noop")
        return InlineKeyboardButton(text=f"🔵 {t}" if t in highlighted else t, callback_data=f"sub_time:{t}")
    rows = [
        [make_btn(t, idx) for idx, t in enumerate(SUBSCRIPTION_TIMES[i:i + 4], start=i)]
        for i in range(0, len(SUBSCRIPTION_TIMES), 4)
    ]
    rows.append([InlineKeyboardButton(text="✅ Готово", callback_data="sub_done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.message(PassengerStates.browsing_trips, lambda m: m.text == "🔔 Сповістити про нові поїздки")
async def notify_new_driver_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    trip_message_id = data.get("trip_message_id")
    if trip_message_id:
        try:
            await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=trip_message_id, reply_markup=None)
        except Exception as e:
            logging.warning("Failed to clear trip message reply markup: %s", e)
    await state.update_data(subscription_selected_times=[])
    await state.set_state(PassengerStates.subscription_from_to_time)
    await message.answer("Оберіть з якого та по який час шукаєте поїздки.", reply_markup=back_only_kb)
    sub_kb_msg = await message.answer("Наприклад, 08:00 - 12:00", reply_markup=_subscription_inline_kb(day=data.get("day")))
    await state.update_data(subscription_kb_message_id=sub_kb_msg.message_id)

@router.message(PassengerStates.subscription_from_to_time, lambda m: m.text != "⬅️ Назад")
async def subscription_text_ignored(message: types.Message):
    await message.answer("Оберіть час, натиснувши кнопки вище.")

@router.callback_query(PassengerStates.subscription_from_to_time, lambda c: c.data == "sub_noop")
async def subscription_noop(callback: types.CallbackQuery):
    await callback.answer()

@router.callback_query(PassengerStates.subscription_from_to_time, lambda c: c.data and c.data.startswith("sub_time:"))
async def subscription_time_handler(callback: types.CallbackQuery, state: FSMContext):
    raw = callback.data.split(":", 1)[1]
    if raw not in SUBSCRIPTION_TIMES:
        await callback.answer()
        return
    data = await state.get_data()
    selected = list(data.get("subscription_selected_times", []))
    if len(selected) >= 2:
        selected = [raw]
    elif raw in selected:
        selected.remove(raw)
    else:
        selected.append(raw)
    await state.update_data(subscription_selected_times=selected)
    try:
        await callback.message.edit_reply_markup(reply_markup=_subscription_inline_kb(selected, day=data.get("day")))
    except TelegramBadRequest as e:
        logging.warning("Failed to update subscription inline kb: %s", e)
    await callback.answer()

@router.callback_query(PassengerStates.subscription_from_to_time, lambda c: c.data == "sub_done")
async def subscription_done_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("subscription_selected_times", [])
    if len(selected) != 2:
        await callback.answer("Оберіть два часи.", show_alert=True)
        return
    from_city = data.get("booking_from_city")
    to_city = data.get("booking_to_city")
    if not from_city or not to_city:
        await callback.message.edit_reply_markup(reply_markup=None)
        await state.clear()
        await callback.message.answer("Сталася помилка. Спробуйте почати пошук знову.", reply_markup=passenger_menu_kb(callback.from_user.id))
        await callback.answer()
        return
    from_str, to_str = min(selected), max(selected)
    day = data.get("day")
    seats = data.get("seats_requested", 1)
    _, from_utc = generate_datetime(day, from_str)
    _, to_utc = generate_datetime(day, to_str)
    subscription_id = save_search_subscription(
        callback.from_user.id,
        from_city,
        to_city,
        day,
        seats,
        from_time=from_utc,
        to_time=to_utc,
    )
    extra_from, extra_to = get_search_city_pairs(from_city, to_city)
    all_trips = search_trips_ids(from_city, to_city, from_utc, to_utc, extra_from_cities=extra_from, extra_to_cities=extra_to)
    matching_ids = {trip_id: boarding_dt for trip_id, free_seats, boarding_dt in all_trips if free_seats >= seats}
    known_ids = set(get_trip_search_list_ids(callback.from_user.id))
    new_trip_ids = [tid for tid in matching_ids if tid not in known_ids]
    try:
        await callback.message.delete()
    except TelegramBadRequest as e:
        logging.warning("Failed to delete subscription message: %s", e)
    await state.clear()
    await callback.message.answer(
        f"✅ Ми повідомимо вас, коли з'явиться нова поїздка:\n"
        f"{from_city} → {to_city}\n"
        f"з {from_str} до {to_str}\n"
        f"{_day_label(day)}, {seats} {seats_word(seats)}\n\n"
        f"Щоб переглянути або скасувати сповіщення перейдіть у меню\n«🔔 Сповіщення про нові поїздки»",
        reply_markup=passenger_menu_kb(callback.from_user.id)
    )
    await callback.answer()
    await asyncio.sleep(3)
    if len(new_trip_ids) > 3:
        await callback.message.answer(
            f"🔔 З‘явилось багато новий поїздок!"
            f"\nРозпочніть пошук, щоб переглянути їх."
        )
    else:
        for trip_id in new_trip_ids:
            await asyncio.sleep(0.5)
            trip = get_trip_for_display(trip_id)
            if not trip:
                continue
            driver_id = trip[1]
            try:
                driver_chat = await callback.bot.get_chat(driver_id)
                driver_name = driver_chat.full_name
                driver_username = driver_chat.username
            except Exception:
                logging.exception("Failed to get driver chat for driver_id=%s", driver_id)
                driver_name = "Водій"
                driver_username = None
            trip_dep_city = trip[3]
            trip_to_city = trip[5]
            dep_local, dep_day = to_local_day_and_time(trip[7])
            boarding_time = matching_ids[trip_id]
            route_lines = [f"📍 {trip_dep_city} - {dep_local.strftime('%H:%M')}, {dep_day}"]
            if from_city and from_city != trip_dep_city:
                board_local = boarding_time.astimezone(ZoneInfo("Europe/Kyiv"))
                route_lines.append(f"📍 {from_city} - {board_local.strftime('%H:%M')}")
            route_lines.append(f"📍 {trip_to_city}")
            notification_text = "🔔 Зʼявилась нова поїздка!\n\n" + "\n".join(route_lines)
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Переглянути деталі ➡️", callback_data=f"view_trip_notification:{trip_id}:{subscription_id}")
            ]])
            await callback.message.answer(notification_text, parse_mode="HTML", reply_markup=kb)


@router.message(PassengerStates.browsing_trips, lambda m: m.text == "⬅️ Назад")
async def back_from_search_handler(message: types.Message, state: FSMContext):
    data = await state.get_data()
    trip_message_id = data.get("trip_message_id")
    if trip_message_id:
        try:
            await message.bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=trip_message_id,
                reply_markup=None
            )
        except Exception as e:
            logging.warning("Failed to clear trip message reply markup: %s", e)
    await state.clear()
    await message.answer("Повернення в меню пасажира:", reply_markup=passenger_menu_kb(message.from_user.id))

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
        except Exception as e:
            logging.warning("Failed to clear trip message reply markup: %s", e)

    await state.clear()
    await message.answer(
        "Повернення в меню пасажира:",
        reply_markup=passenger_menu_kb(message.from_user.id)
    )

@router.callback_query(lambda c: c.data == "next")
async def next_handler(callback: types.CallbackQuery, bot: Bot, state: FSMContext):
    user_id = callback.from_user.id

    boarding_times, old_index, passenger_from_city = get_search_list_times(user_id)
    new_index = increase_trip_search_list_index(user_id)
    if new_index == old_index:
        await safe_answer(callback)
        return

    result = get_current_trip_from_search_list(user_id)

    if result == "expired":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("⏱ Цей пошук застарів. Будь ласка, почніть новий!", reply_markup=passenger_menu_kb(callback.from_user.id))
        await safe_answer(callback)
        return

    if not result:
        await safe_answer(callback, "❌ Виникла помилка, спробуйте знайти поїздку ще раз", show_alert=True)
        return

    trip, index, total_cnt = result
    driver_chat = None
    try:
        driver_chat = await callback.bot.get_chat(trip[1])
        driver_name = driver_chat.full_name
    except:
        driver_name = None
    trip_text = format_trip(trip, index, total_cnt, driver_name, is_own=(trip[1] == callback.from_user.id), passenger_from_city=passenger_from_city, board_time=boarding_times[index] if boarding_times else None)
    await send_trip_message(callback.message.edit_text, trip_text, trip[0], total_cnt, trip[1], driver_chat.username if driver_chat else None, index, all_times=boarding_times)

    await safe_answer(callback)

@router.callback_query(lambda c: c.data == "prev")
async def prev_handler(callback: types.CallbackQuery, bot: Bot, state: FSMContext):
    user_id = callback.from_user.id

    boarding_times, old_index, passenger_from_city = get_search_list_times(user_id)
    new_index = decrease_trip_search_list_index(user_id)
    if new_index == old_index:
        await safe_answer(callback)
        return

    result = get_current_trip_from_search_list(user_id)

    if result == "expired":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("⏱ Цей пошук застарів. Будь ласка, розпочніть новий!", reply_markup=passenger_menu_kb(callback.from_user.id))
        await safe_answer(callback)
        return

    if not result:
        await safe_answer(callback, "❌ Виникла помилка, спробуйте знайти поїздку ще раз", show_alert=True)
        return

    trip, index, total_cnt = result
    driver_chat = None
    try:
        driver_chat = await callback.bot.get_chat(trip[1])
        driver_name = driver_chat.full_name
    except:
        driver_name = None
    trip_text = format_trip(trip, index, total_cnt, driver_name, is_own=(trip[1] == callback.from_user.id), passenger_from_city=passenger_from_city, board_time=boarding_times[index] if boarding_times else None)
    await send_trip_message(callback.message.edit_text, trip_text, trip[0], total_cnt, trip[1], driver_chat.username if driver_chat else None, index, all_times=boarding_times)

    await safe_answer(callback)


@router.callback_query(lambda c: c.data and c.data.startswith("trip_idx:"))
async def trip_idx_handler(callback: types.CallbackQuery, bot: Bot, state: FSMContext):
    user_id = callback.from_user.id
    target_index = int(callback.data.split(":")[1])

    boarding_times, current_index, passenger_from_city = get_search_list_times(user_id)
    if target_index == current_index:
        await safe_answer(callback)
        return

    set_trip_search_list_index(user_id, target_index)
    result = get_current_trip_from_search_list(user_id)

    if result == "expired":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("⏱ Цей пошук застарів. Будь ласка, розпочніть новий!", reply_markup=passenger_menu_kb(callback.from_user.id))
        await safe_answer(callback)
        return

    if not result:
        await safe_answer(callback, "❌ Виникла помилка, спробуйте знайти поїздку ще раз", show_alert=True)
        return

    trip, index, total_cnt = result
    driver_chat = None
    try:
        driver_chat = await callback.bot.get_chat(trip[1])
        driver_name = driver_chat.full_name
    except:
        driver_name = None
    trip_text = format_trip(trip, index, total_cnt, driver_name, is_own=(trip[1] == callback.from_user.id), passenger_from_city=passenger_from_city, board_time=boarding_times[index] if boarding_times else None)
    await send_trip_message(callback.message.edit_text, trip_text, trip[0], total_cnt, trip[1], driver_chat.username if driver_chat else None, index, all_times=boarding_times)
    await safe_answer(callback)


@router.callback_query(lambda c: c.data and c.data.startswith("book_trip:"))
async def book_trip_callback(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    trip_id = int(parts[1])
    subscription_id = int(parts[2]) if len(parts) > 2 else None

    trip = get_trip_for_display(trip_id)
    if not trip or trip[1] == callback.from_user.id:
        await safe_answer(callback, "❌ Ви не можете забронювати власну поїздку.", show_alert=True)
        return

    data = await state.get_data()
    sub = get_subscription_cities(subscription_id) if subscription_id else None
    seats = (sub[2] if sub else None) or data.get("seats_requested", 1)
    can_book, reason = check_trip_bookable(trip_id, callback.from_user.id, seats)
    if not can_book:
        await safe_answer(callback, BOOK_ERRORS.get(reason, "❌ Не вдалося забронювати поїздку."), show_alert=True)
        return

    await safe_answer(callback)
    await callback.message.edit_reply_markup()
    await state.update_data(booking_trip_id=trip_id)
    await state.set_state(PassengerStates.booking_notes)

    if sub:
        from_city, to_city = sub[0], sub[1]
        await state.update_data(booking_from_city=from_city, booking_to_city=to_city, seats_requested=seats)
    else:
        from_city = data.get("booking_from_city")
        to_city = data.get("booking_to_city")
    city = get_city_modified_name(from_city)
    recent_notes = get_recent_booking_notes(callback.from_user.id, from_city)
    if recent_notes:
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=n)] for n in recent_notes] + [[KeyboardButton(text="⬅️ Назад")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    else:
        kb = back_only_kb
    await callback.message.answer(f"📍 Вкажіть місце де вас підібрати у {city}:", reply_markup=kb)

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

    success, booking_id, has_overlap = book_trip(trip_id, passenger_id, notes, seats_requested, phone, from_city=data.get("booking_from_city"), to_city=data.get("booking_to_city"))

    if not success:
        await message.answer(BOOK_ERRORS.get(booking_id, "❌ Не вдалося забронювати поїздку."), reply_markup=passenger_menu_kb(message.from_user.id))
        await state.clear()
        return
    await state.clear()
    await message.answer(
        "⏳ Ми відправили запит водієві, очікуйте підтвердження.",
        reply_markup=passenger_menu_kb(message.from_user.id)
    )
    if has_overlap:
        await message.answer("⚠️ Зверніть увагу: у вас вже є інше бронювання впритул до цього.")

    driver_id = get_driver_id(trip_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Переглянути деталі ➡️", callback_data=f"show_driver_trip:{trip_id}")
    ]])
    await message.bot.send_message(driver_id, f"🔔 Пасажир <b>{passenger_name}</b> хоче поїхати з вами.", parse_mode="HTML", reply_markup=kb)

@router.callback_query(lambda c: c.data == "cancel_search")
async def cancel_search(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.clear()
    await callback.message.answer("Пошук скасовано. Повернення в меню пасажира:", reply_markup=passenger_menu_kb(callback.from_user.id))
    await safe_answer(callback)


@router.callback_query(lambda c: c.data and c.data.startswith("view_trip_notification:"))
async def view_trip_notification_callback(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    trip_id = int(parts[1])
    subscription_id = int(parts[2]) if len(parts) > 2 else None

    trip = get_trip_for_display(trip_id)
    if not trip:
        await safe_answer(callback, "Поїздку не знайдено або вона вже відбулась.", show_alert=True)
        return

    dep_datetime = trip[7]
    if dep_datetime <= datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5):
        await safe_answer(callback, "❌ Ця поїздка вже відправилась.", show_alert=True)
        return

    sub = get_subscription_cities(subscription_id) if subscription_id else None
    search_from_city = sub[0] if sub else trip[3]
    search_to_city = sub[1] if sub else trip[5]
    seats = sub[2] if sub else 1
    day_str = sub[3] if sub else dep_datetime.astimezone(ZoneInfo("Europe/Kyiv")).strftime("%Y-%m-%d")

    await safe_answer(callback)
    await state.update_data(booking_from_city=search_from_city, booking_to_city=search_to_city, day=day_str, seats_requested=seats)
    await _run_search(callback.message, state, "Показати всі поїздки", jump_to_trip_id=trip_id, user_id=callback.from_user.id)


@router.callback_query(lambda c: c.data and c.data.startswith("cancel_booking:"))
async def cancel_booking_callback(callback: types.CallbackQuery, bot: Bot):
    import datetime
    booking_id = int(callback.data.split(":")[1])

    trip = get_trip_details_by_booking(booking_id)
    if trip:
        arrival_dt = trip[5]
        if arrival_dt <= datetime.datetime.now(datetime.timezone.utc):
            await safe_answer(callback, "❌ Поїздка вже відбулась, скасування неможливе.", show_alert=True)
            return

    prev_status, _ = update_booking_status(booking_id, "cancelled_by_passenger", ["pending", "confirmed"])
    if prev_status in ("pending", "confirmed"):
        new_text = callback.message.html_text + "\n\n" + STATUS_LABELS["cancelled_by_passenger"]
        await callback.message.edit_text(new_text, parse_mode="HTML")
        await safe_answer(callback, "🚫 Ви скасували ваше бронювання", show_alert=True)
        driver_id = get_driver_id_by_booking(booking_id)
        passenger_name = callback.from_user.full_name
        booking_from = trip[10] if trip else None
        booking_to = trip[11] if trip else None
        route_line = f"\n{booking_from} → {booking_to}" if booking_from and booking_to else ""
        await bot.send_message(driver_id, f"🚫 Пасажир {passenger_name} скасував своє бронювання.{route_line}", parse_mode="HTML")
    elif prev_status == "cancelled_by_passenger":
        await safe_answer(callback, "🚫 Ви вже скасували цю бронь раніше", show_alert=True)
    elif prev_status == "rejected":
        await safe_answer(callback, "🚫 Водій вже відхилив вашу бронь раніше", show_alert=True)
    elif prev_status == "trip_cancelled":
        await safe_answer(callback, STATUS_LABELS["trip_cancelled"], show_alert=True)
    else:
        await safe_answer(callback, "🚫 Не вдалося скасувати бронь. Виникла помилка, спробуйте ще.", show_alert=True)
