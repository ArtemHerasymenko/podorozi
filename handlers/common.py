import logging
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from states.feedback_states import FeedbackStates
from database import save_feedback, save_trip_to_db, save_trip_template, upsert_template_time, get_recent_template_times, get_recent_times_by_cities, get_pending_subscriptions
from config import ADMIN_CHAT_ID
from data.route_intermediates import get_intermediates, get_covered_pairs, get_travel_time_between
from database import get_city_modified_name_2
import asyncio
import datetime
import zoneinfo
from zoneinfo import ZoneInfo

router = Router()

async def safe_answer(callback, *args, **kwargs):
    try:
        await callback.answer(*args, **kwargs)
    except TelegramBadRequest as e:
        logging.warning("callback.answer failed: %s", e)

async def safe_send(send_fn, text: str, kb: InlineKeyboardMarkup, parse_mode="HTML"):
    try:
        return await send_fn(text, reply_markup=kb, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "BUTTON_USER_PRIVACY_RESTRICTED" in str(e) and kb:
            logging.warning("BUTTON_USER_PRIVACY_RESTRICTED — retrying without tg://user button: %s", e)
            filtered_rows = [
                [btn for btn in row if not (btn.url and btn.url.startswith("tg://user"))]
                for row in kb.inline_keyboard
            ]
            filtered_rows = [row for row in filtered_rows if row]
            return await send_fn(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=filtered_rows), parse_mode=parse_mode)
        raise

# Hardcoded Ukrainian translations
eng_to_ukr_days = {
    'Monday': 'понеділок',
    'Tuesday': 'вівторок',
    'Wednesday': 'середа',
    'Thursday': 'четвер',
    'Friday': 'пʼятниця',
    'Saturday': 'субота',
    'Sunday': 'неділя'
}

uk_months = {
    'January': 'січня',
    'February': 'лютого',
    'March': 'березня',
    'April': 'квітня',
    'May': 'травня',
    'June': 'червня',
    'July': 'липня',
    'August': 'серпня',
    'September': 'вересня',
    'October': 'жовтня',
    'November': 'листопада',
    'December': 'грудня'
}

def generate_quick_days():
    now = datetime.datetime.now(tz=zoneinfo.ZoneInfo("Europe/Kyiv"))
    quick_days = []
    prefixes = ["Сьогодні", "Завтра"]
    for d in range(2):
        day = now + datetime.timedelta(days=d)
        english_day = day.strftime("%A")
        english_month = day.strftime("%B")
        dep_day = eng_to_ukr_days.get(english_day, english_day)
        uk_month = uk_months.get(english_month, english_month)
        label = f"{prefixes[d]} ({dep_day})"
        quick_days.append((label, day.strftime("%Y-%m-%d")))
    return quick_days

back_only_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="⬅️ Назад")]],
    resize_keyboard=True
)

searching_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="...")]],
    resize_keyboard=True
)

def quick_day_kb():
    quick_days = generate_quick_days()
    keyboard = [[KeyboardButton(text=label)] for label, _ in quick_days]
    keyboard.append([KeyboardButton(text="⬅️ Назад")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def seats_word(n) -> str:
    n = abs(int(n))
    if 11 <= n % 100 <= 14:
        return "місць"
    last = n % 10
    if last == 1:
        return "місце"
    if 2 <= last <= 4:
        return "місця"
    return "місць"

def trip_word(n) -> str:
    n = abs(int(n))
    last2, last1 = n % 100, n % 10
    if 11 <= last2 <= 14:
        return "поїздок"
    if last1 == 1:
        return "поїздку"
    if 2 <= last1 <= 4:
        return "поїздки"
    return "поїздок"

def validate_city_name(city: str):
    import re
    if not city or not re.match(r"^[a-zA-Zа-яА-ЯіІїЇєЄ'\s-]+$", city):
        return False, "Назва міста може містити лише літери, пробіли та дефіси."
    return True, None

def validate_time(time_str):
    import re

    time_str = re.sub(r'[.\- ]', ':', time_str.strip())

    if not re.match(r'^\d{1,2}:\d{2}$', time_str):
        return False, "Неправильний формат часу. Введіть в форматі ГГ:ХХ. Наприклад, 14:30"

    hour, minute = map(int, time_str.split(':'))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return False, "Неправильний час. Години 00-23, хвилини 00-59"

    return True, time_str

def generate_datetime(date_str, time_str):
    # Parse into datetime with timezone conversion
    try:
        kyiv_tz = zoneinfo.ZoneInfo("Europe/Kyiv")
        naive_dt = datetime.datetime.fromisoformat(f"{date_str}T{time_str.zfill(5)}")
        local_dt = naive_dt.replace(tzinfo=kyiv_tz)
        return True, local_dt.astimezone(datetime.timezone.utc)
    except ValueError as e:
        return False, f"Неправильна дата чи час: {str(e)}"

async def finish_trip_creation(user_id: int, data: dict, answer, state: FSMContext, bot=None):
    template_id = save_trip_template(user_id, data)
    if template_id and data.get("datetime"):
        kyiv_time = data["datetime"].astimezone(ZoneInfo("Europe/Kyiv")).strftime("%H:%M")
        upsert_template_time(template_id, kyiv_time)
    trip_id, has_overlap = save_trip_to_db(user_id, data)
    await answer("✅ Поїздка збережена!\nМожете переглянути її в меню\n\"📋 Заплановані поїздки\"", reply_markup=driver_menu_kb)
    intermediates = get_intermediates(data.get("from_city", ""), data.get("to_city", ""))
    if intermediates:
        names = [get_city_modified_name_2(c) or c for c in intermediates]
        cities_str = " та ".join(names) if len(names) <= 2 else ", ".join(names[:-1]) + " та " + names[-1]
        await answer(f"ℹ️ Вашу поїздку також бачитимуть пасажири з {cities_str}.")
    if has_overlap:
        await answer("⚠️ Зверніть увагу: у вас є інша поїздка впритул до цієї.")
    await state.clear()
    if bot and data.get("datetime"):
        dep_datetime = data["datetime"]
        from_city = data.get("from_city", "")
        to_city = data.get("to_city", "")
        covered = get_covered_pairs(from_city, to_city)
        boarding_times = [dep_datetime + datetime.timedelta(minutes=get_travel_time_between(from_city, pair_from)) for pair_from, _ in covered]
        waiting = get_pending_subscriptions(covered, boarding_times)
        seats = int(data.get("seats") or 0)
        waiting = [(sub_id, pid, sreq, sub_from_city, bt) for sub_id, pid, sreq, sub_from_city, bt in waiting if sreq <= seats]
        if waiting:
            try:
                driver_chat = await bot.get_chat(user_id)
                driver_name = driver_chat.full_name
                driver_username = driver_chat.username
            except Exception:
                logging.exception("Failed to get driver chat for user_id=%s", user_id)
                driver_name = "Водій"
                driver_username = None
            trip_tuple = (
                trip_id, user_id, data.get("driver_phone"),
                from_city, data.get("from_points"),
                to_city, data.get("to_points"),
                dep_datetime, data.get("price"),
                seats, seats,
                data.get("arrival_time"), data.get("car_description")
            )
            for sub_id, passenger_id, _, sub_from_city, boarding_time in waiting:
                if passenger_id == user_id:
                    continue
                await asyncio.sleep(0.5)
                trip_text = format_trip(trip_tuple, 0, 1, driver_name=driver_name, passenger_from_city=sub_from_city, board_time=boarding_time)
                try:
                    await send_trip_message(
                        lambda text, **kw: bot.send_message(passenger_id, "🔔 Зʼявилась нова поїздка!\n\n" + text, **kw),
                        trip_text, trip_id, 1, user_id, driver_username, 0, subscription_id=sub_id
                    )
                except Exception:
                    logging.exception("Failed to send trip notification to passenger_id=%s", passenger_id)
    return trip_id

async def handle_day_input(message: types.Message, state: FSMContext, next_state):
    quick_days = generate_quick_days()
    day_dict = {label: date_str for label, date_str in quick_days}
    if message.text not in day_dict:
        await message.answer("Оберіть день зі списку.")
        return
    await state.update_data(day=day_dict[message.text])
    data = await state.get_data()
    from_city_label = get_city_modified_name_2(data["from_city"]) or data["from_city"]
    exact = get_recent_template_times(data["template_id"], limit=10) if data.get("template_id") else []
    by_city = get_recent_times_by_cities(message.from_user.id, data.get("from_city", ""), data.get("to_city", ""), limit=10)
    recent_times = list(dict.fromkeys(exact + by_city))
    chosen_day = data.get("day", "")
    now_kyiv = datetime.datetime.now(tz=zoneinfo.ZoneInfo("Europe/Kyiv"))
    if chosen_day == now_kyiv.strftime("%Y-%m-%d"):
        current_hhmm = (now_kyiv + datetime.timedelta(minutes=3)).strftime("%H:%M")
        recent_times = [t for t in recent_times if t > current_hhmm]
    recent_times = sorted(recent_times[:3])
    if recent_times:
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=t)] for t in recent_times] + [[KeyboardButton(text="⬅️ Назад")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    else:
        kb = back_only_kb
    await message.answer(f"Введіть час виїзду з {from_city_label} у форматі ГГ:ХХ:", reply_markup=kb)
    await state.set_state(next_state)

async def handle_time_input(message: types.Message, state: FSMContext, next_state):
    if not message.text:
        await message.answer("Будь ласка, введіть час текстом, наприклад 14:30:")
        return
    time_str = message.text.zfill(5)
    is_valid, result = validate_time(time_str)
    if not is_valid:
        await message.answer(result)
        return
    data = await state.get_data()
    is_valid, response = generate_datetime(data.get("day"), time_str)
    if not is_valid:
        await message.answer(response)
        return
    if response <= datetime.datetime.now(datetime.timezone.utc):
        await message.answer("❌ Час відправлення має бути у майбутньому. Введіть знову:")
        return
    travel_minutes = get_travel_time_between(data.get("from_city", ""), data.get("to_city", ""))
    arrival = response + datetime.timedelta(minutes=travel_minutes or 30)
    await state.update_data(datetime=response, arrival_time=arrival)
    await message.answer("Кількість місць:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=str(i))] for i in range(1, 5)] + [[KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True,
        one_time_keyboard=True
    ))
    await state.set_state(next_state)

def format_basic_details(from_city: str, to_city: str, dep_dt, arrival_dt, from_points: str = None, to_points: str = None, passenger_from_city: str = None, board_time=None) -> str:
    local_tz = zoneinfo.ZoneInfo("Europe/Kyiv")
    local_dt = dep_dt.astimezone(local_tz)
    dep_day = eng_to_ukr_days.get(local_dt.strftime("%A"), local_dt.strftime("%A"))
    dep_time = local_dt.strftime("%H:%M")
    to_str = f"<b>{to_city}</b> ({to_points})" if to_points else f"<b>{to_city}</b>"
    if passenger_from_city and passenger_from_city != from_city and board_time is not None:
        board_local = board_time.astimezone(local_tz)
        board_day = eng_to_ukr_days.get(board_local.strftime("%A"), board_local.strftime("%A"))
        dep_day_str = f", {dep_day}" if dep_day != board_day else ""
        board_day_str = f", {board_day}" if board_day != dep_day else ""
        return (
            f"📍 <b>{from_city}</b> — {dep_time}{dep_day_str}\n"
            f"📍 <b>{passenger_from_city}</b> — {board_local.strftime('%H:%M')}{board_day_str}\n"
            f"📍 {to_str}"
        )
    else:
        time_str = f"🕐 {dep_time}"
        from_str = f"<b>{from_city}</b> ({from_points})" if from_points else f"<b>{from_city}</b>"
        return f"{time_str}\n📍 {from_str}\n📍 {to_str}"
    
def mask_phone(phone):
    if not phone or len(phone) < 4:
        return phone
    return phone[:3] + '*' * (len(phone) - 4) + phone[-1]

def format_trip(trip, index, total_cnt, driver_name=None, is_own=False, passenger_from_city=None, board_time=None):
    position_text = f"Поїздка № {index + 1}/{total_cnt}" if total_cnt > 1 else ""
    position_line = f"{position_text}\n\n" if position_text else ""
    name_str = driver_name or "Водій"
    if is_own:
        name_str += " (Ви)"
    driver_line = f"👤 {name_str}"
    car_line = f"🚘 {trip[12]}" if trip[12] else ""
    route_str = format_basic_details(trip[3], trip[5], trip[7], trip[11], trip[4], trip[6], passenger_from_city=passenger_from_city, board_time=board_time)
    return (
        f"{position_line}"
        f"{route_str}\n\n"
        f"💰 {trip[8]} грн за місце | {trip[10]}/{trip[9]} вільні\n"
        f"{driver_line}\n"
        f"{car_line}\n"
        )

def trip_keyboard(trip_id, total_cnt=1, driver_id=None, driver_username=None, index=0, all_times=None, subscription_id=None):
    import math
    book_cb = f"book_trip:{trip_id}:{subscription_id}" if subscription_id else f"book_trip:{trip_id}"
    rows = []
    if total_cnt > 1:
        nav = [
            InlineKeyboardButton(text="⬅️ Попередня", callback_data="prev"),
            InlineKeyboardButton(text="Наступна ➡️", callback_data="next"),
        ]
        if all_times:
            _kyiv = zoneinfo.ZoneInfo("Europe/Kyiv")
            all_times = [t.astimezone(_kyiv).strftime("%H:%M") for t in all_times]
            page_size = 8
            n = len(all_times)
            page = index // page_size
            last_page = (n - 1) // page_size
            if n % page_size == 1 and last_page > 0 and page >= last_page - 1:
                start = (last_page - 1) * page_size
                end = n
            else:
                start = page * page_size
                end = min(start + page_size, n)
            prev_btn = InlineKeyboardButton(text=f"{all_times[0]}...{all_times[start - 1]}", callback_data=f"trip_idx:{start - 1}") if start > 0 else None
            next_btn = InlineKeyboardButton(text=f"{all_times[end]}...{all_times[-1]}", callback_data=f"trip_idx:{end}") if end < n else None
            time_btns = [
                InlineKeyboardButton(
                    text=f"👉 {t}" if i == index else t,
                    callback_data=f"trip_idx:{i}"
                )
                for i, t in list(enumerate(all_times))[start:end]
            ]
            middle = time_btns
            if prev_btn:
                rows.append([prev_btn] + middle[:2])
                middle = middle[2:]
            remaining = middle + ([next_btn] if next_btn else [])
            rows.extend(remaining[i:i + 4] for i in range(0, len(remaining), 4))
            if len(rows) >= 2 and len(rows[-1]) <= 2:
                rows[-1].insert(0, rows[-2].pop())
            if next_btn and rows and len(rows[-1]) == 4:
                rows.append(rows[-1][2:])
                rows[-2] = rows[-2][:2]
                if len(rows) >= 3:
                    rows[-2].insert(0, rows[-3].pop())
        rows.insert(0, nav)
    if driver_id:
        driver_url = f"https://t.me/{driver_username}" if driver_username else f"tg://user?id={driver_id}"
        rows.append([
            InlineKeyboardButton(text="✉️ Написати водію", url=driver_url),
            InlineKeyboardButton(text="Забронювати ✅", callback_data=book_cb),
        ])
    else:
        rows.append([InlineKeyboardButton(text="Забронювати ✅", callback_data=book_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def send_trip_message(send_fn, text: str, trip_id, total_cnt, driver_id, driver_username, index, show_keyboard=True, all_times=None, subscription_id=None):
    kb = trip_keyboard(trip_id, total_cnt, driver_id, driver_username, index=index, all_times=all_times, subscription_id=subscription_id) if show_keyboard else None
    return await safe_send(send_fn, text, kb)

def format_notes_details_for_driver(notes: str = None, pickup_at=None, passenger_phone: str = None, booking_from_city: str = None, booking_to_city: str = None) -> str:
    notes_line = f"📍 Місце посадки: <b>{booking_from_city}</b>"
    if notes:
        notes_line += f"<b>, {notes}</b>"
    if booking_to_city:
        notes_line += f"\n📍 Місце висадки: <b>{booking_to_city}</b>"
    phone_line = f"\n📞 {passenger_phone}" if passenger_phone else "\n📞 Пасажир не вказав свій номер"
    if pickup_at:
        time_str = pickup_at.astimezone(zoneinfo.ZoneInfo("Europe/Kyiv")).strftime("%H:%M")
        driver_notes_line = f"\n⏱ Ви підберете о: {time_str}"
    else:
        driver_notes_line = ""
    return f"{notes_line}{phone_line}{driver_notes_line}"

def format_booking_description_for_driver(from_city: str, to_city: str, dep_dt, notes: str = None, pickup_at=None, arrival_dt=None, seats: int = None, from_points: str = None, to_points: str = None, passenger_phone: str = None, booking_from_city: str = None, booking_to_city: str = None) -> str:
    trip_desc = format_basic_details(from_city, to_city, dep_dt, arrival_dt, from_points, to_points)
    seats_line = f"\n👥 Місць заброньовано: {seats}" if seats is not None else ""
    notes_desc = format_notes_details_for_driver(notes, pickup_at, passenger_phone, booking_from_city=booking_from_city, booking_to_city=booking_to_city)
    return f"{notes_desc}{seats_line} \n\nВаш маршрут:\n{trip_desc}"

def format_notes_details_for_passenger(notes: str = None, pickup_at=None, booking_from_city: str = None, booking_to_city: str = None) -> str:
    notes_line = f"\n📍 Місце посадки: <b>{booking_from_city}</b>"
    if notes:
        notes_line += f"<b>, {notes}</b>"
    notes_line += f"\n📍 Місце висадки: <b>{booking_to_city}</b>"
    if pickup_at:
        time_str = pickup_at.astimezone(zoneinfo.ZoneInfo("Europe/Kyiv")).strftime("%H:%M")
        driver_notes_line = f"\n⏱ Підбере вас о: <b>{time_str}</b>"
    else:
        driver_notes_line = ""
    return f"{driver_notes_line}{notes_line}"

def format_booking_description_for_passenger(from_city: str, to_city: str, dep_dt, notes: str = None, pickup_at=None, arrival_dt=None, seats: int = None, from_points: str = None, to_points: str = None, car_description: str = None, booking_from_city: str = None, booking_to_city: str = None, driver_phone: str = None, price=None, driver_name: str = None) -> str:
    trip_desc = format_basic_details(from_city, to_city, dep_dt, arrival_dt, from_points, to_points, passenger_from_city=booking_from_city, board_time=pickup_at)
    seats_line = f"\n👥 Місць заброньовано: {seats}" if seats is not None else ""
    car_line = f"\n🚘 {car_description}" if car_description else ""
    phone_line = f"\n📞 {driver_phone}" if driver_phone else "\n📞 Водій не вказав свій номер"
    price_line = f"\n💰 {price} грн за місце" if price is not None else ""
    driver_line = f"👤 {driver_name}" if driver_name else "👤 Водій"
    notes_desc = format_notes_details_for_passenger(notes, pickup_at, booking_from_city, booking_to_city)
    return f"{driver_line}{notes_desc}{seats_line}{price_line}{car_line}{phone_line}\n\nМаршрут водія:\n{trip_desc}"

create_trip_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Використати шаблон")],
        [KeyboardButton(text="✏️ Створити з нуля")],
        [KeyboardButton(text="⬅️ Назад")],
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

driver_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚗 Створити поїздку")],
        [KeyboardButton(text="📋 Заплановані поїздки")],
        [KeyboardButton(text="📜 Минулі поїздки")],
        [KeyboardButton(text="⬅️ Назад")]
    ],
    resize_keyboard=True
)

role_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚗 Я водій")],
        [KeyboardButton(text="👤 Я пасажир")],
        [KeyboardButton(text="📝 Питання та відгуки")]
    ],
    resize_keyboard=True
)

@router.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
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
    await message.answer("Оберіть роль:", reply_markup=role_menu)

@router.message(lambda m: m.text == "📝 Питання та відгуки")
async def feedback_start(message: types.Message, state: FSMContext):
    await state.set_state(FeedbackStates.writing)
    await message.answer("Опишіть де виникли проблеми чи питання (можна скріншотом). Або розкажіть що найбільше сподобалось:", reply_markup=back_only_kb)

@router.message(FeedbackStates.writing, lambda m: m.text != "⬅️ Назад")
async def feedback_write(message: types.Message, state: FSMContext):
    if message.photo:
        file_id = message.photo[-1].file_id
        caption = message.caption or ""
        feedback_id = save_feedback(message.from_user.id, "general", feedback_text=caption, file_id=file_id)
        await message.bot.send_photo(ADMIN_CHAT_ID, file_id, caption=f"📬 Відгук #{feedback_id} від {message.from_user.full_name} ({message.from_user.id})\n{caption}")
    elif message.text:
        save_feedback(message.from_user.id, "general", feedback_text=message.text)
    else:
        await message.answer("Будь ласка, надішліть відгук у вигляді тексту або скріншоту:")
        return
    await state.clear()
    await message.answer("Дякуємо за ваш відгук! 🙏", reply_markup=role_menu)

@router.message(lambda m: m.text == "⬅️ Назад")
async def back(message: types.Message, state: FSMContext):
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
    await message.answer("Оберіть роль:", reply_markup=role_menu)