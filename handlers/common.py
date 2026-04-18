from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import datetime
import zoneinfo

router = Router()

# Hardcoded Ukrainian translations
uk_days = {
    'Monday': 'Понеділок',
    'Tuesday': 'Вівторок',
    'Wednesday': 'Середа',
    'Thursday': 'Четвер',
    'Friday': 'Пʼятниця',
    'Saturday': 'Субота',
    'Sunday': 'Неділя'
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
    now = datetime.datetime.now(tz=zoneinfo.ZoneInfo("Europe/Kiev"))
    quick_days = []
    for d in range(2):
        day = now + datetime.timedelta(days=d)
        english_day = day.strftime("%A")
        english_month = day.strftime("%B")
        uk_day = uk_days.get(english_day, english_day)
        uk_month = uk_months.get(english_month, english_month)
        label = f"{uk_day}, {day.day} {uk_month}"
        quick_days.append((label, day.strftime("%Y-%m-%d")))
    return quick_days

def quick_day_kb():
    quick_days = generate_quick_days()
    keyboard = [[KeyboardButton(text=label)] for label, _ in quick_days]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def validate_city_name(city: str):
    import re
    if not city or not re.match(r"^[a-zA-Zа-яА-ЯіІїЇєЄ'\s-]+$", city):
        return False, "Назва міста може містити лише літери, пробіли та дефіси."
    return True, None

def validate_time(time_str):
    import re
    
    # Validate time format (allow H:MM or HH:MM)
    if not re.match(r'^\d{1,2}:\d{2}$', time_str):
        return False, "Неправильний формат часу. Введи в форматі ГГ:ХХ. Наприклад, 14:30:"
    
    # Validate time values
    hour, minute = map(int, time_str.split(':'))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return False, "Неправильний час. Години 00-23, хвилини 00-59:"
    
    return True, None

def generate_datetime(date_str, time_str):
    # Parse into datetime with timezone conversion
    try:
        local_tz = zoneinfo.ZoneInfo("Europe/Kiev")
        naive_dt = datetime.datetime.fromisoformat(f"{date_str}T{time_str}")
        local_dt = naive_dt.replace(tzinfo=local_tz)
        utc_dt = local_dt.astimezone(datetime.timezone.utc)
        return True, utc_dt
    except ValueError as e:
        return False, f"Неправильна дата чи час: {str(e)}"

def format_basic_details(from_city: str, to_city: str, dep_dt, arrival_dt, from_points: str = None, to_points: str = None) -> str:
    local_tz = zoneinfo.ZoneInfo("Europe/Kiev")
    local_dt = dep_dt.astimezone(local_tz)
    arrival_local = arrival_dt.astimezone(local_tz)
    uk_day = uk_days.get(local_dt.strftime("%A"), local_dt.strftime("%A"))
    dep_time = local_dt.strftime("%H:%M")
    arr_time = arrival_local.strftime("%H:%M")
    date_str = local_dt.strftime("%d.%m.%Y")
    from_str = f"{from_city} ({from_points})" if from_points else from_city
    to_str = f"{to_city} ({to_points})" if to_points else to_city
    return f"🚗 {from_str}\n➡️ {to_str}\n🕐 {dep_time} → {arr_time} ({uk_day}, {date_str})"
    
def format_notes_details_for_driver(notes: str = None, pickup_at=None, passenger_phone: str = None) -> str:
    notes_line = f"\n📍 Місце посадки: {notes}" if notes else ""
    phone_line = f"\n📞 Телефон пасажира: {passenger_phone}" if passenger_phone else ""
    if pickup_at:
        time_str = pickup_at.astimezone(zoneinfo.ZoneInfo("Europe/Kiev")).strftime("%H:%M")
        driver_notes_line = f"\n⏱ Ви прибуде о: {time_str}"
    else:
        driver_notes_line = ""
    return f"{notes_line}{phone_line}{driver_notes_line}"

def format_booking_description_for_driver(from_city: str, to_city: str, dep_dt, notes: str = None, pickup_at=None, arrival_dt=None, seats: int = None, from_points: str = None, to_points: str = None, passenger_phone: str = None) -> str:
    trip_desc = format_basic_details(from_city, to_city, dep_dt, arrival_dt, from_points, to_points)
    seats_line = f"\n👥 Місць заброньовано: {seats}" if seats is not None else ""
    notes_desc = format_notes_details_for_driver(notes, pickup_at, passenger_phone)
    return f"{trip_desc}{seats_line}{notes_desc}"

def format_notes_details_for_passenger(notes: str = None, pickup_at=None) -> str:
    notes_line = f"\n📍 Місце посадки: {notes}" if notes else ""
    if pickup_at:
        time_str = pickup_at.astimezone(zoneinfo.ZoneInfo("Europe/Kiev")).strftime("%H:%M")
        driver_notes_line = f"\n⏱ Водій прибуде о: {time_str}"
    else:
        driver_notes_line = ""
    return f"{notes_line}{driver_notes_line}"

def format_booking_description_for_passenger(from_city: str, to_city: str, dep_dt, notes: str = None, pickup_at=None, arrival_dt=None, seats: int = None, from_points: str = None, to_points: str = None) -> str:
    trip_desc = format_basic_details(from_city, to_city, dep_dt, arrival_dt, from_points, to_points)
    seats_line = f"\n👥 Місць заброньовано: {seats}" if seats is not None else ""
    notes_desc = format_notes_details_for_passenger(notes, pickup_at)
    return f"{trip_desc}{seats_line}{notes_desc}"

role_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚗 Я водій")],
        [KeyboardButton(text="👤 Я пасажир")]
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
        except:
            pass
    await state.clear()
    await message.answer("Оберіть роль:", reply_markup=role_menu)

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
        except:
            pass
    await state.clear()
    await message.answer("Оберіть роль:", reply_markup=role_menu)