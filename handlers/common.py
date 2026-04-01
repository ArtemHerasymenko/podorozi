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

def validate_time(time_str):
    import re
    
    # Validate time format
    if not re.match(r'^\d{2}:\d{2}$', time_str):
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

def format_basic_details(from_city: str, to_city: str, dep_dt) -> str:
    local_tz = zoneinfo.ZoneInfo("Europe/Kiev")
    local_dt = dep_dt.astimezone(local_tz)
    uk_day = uk_days.get(local_dt.strftime("%A"), local_dt.strftime("%A"))
    dt_str = local_dt.strftime("%d.%m.%Y %H:%M")
    return f"🚗 {from_city} → {to_city}\n📅 {uk_day}, {dt_str}"
    
def format_notes_details_for_driver(notes: str = None, driver_notes: str = None) -> str:
    notes_line = f"\n📍 Місце посадки: {notes}" if notes else ""
    driver_notes_line = f"\n⏱ Ви прибуде о: {driver_notes}" if driver_notes else ""
    return f"{notes_line}{driver_notes_line}"

def format_booking_description_for_driver(from_city: str, to_city: str, dep_dt, notes: str = None, driver_notes: str = None) -> str:
    trip_desc = format_basic_details(from_city, to_city, dep_dt)
    notes_desc = format_notes_details_for_driver(notes, driver_notes)
    return f"{trip_desc}{notes_desc}"

def format_notes_details_for_passenger(notes: str = None, driver_notes: str = None) -> str:
    notes_line = f"\n📍 Місце посадки: {notes}" if notes else ""
    driver_notes_line = f"\n⏱ Водій прибуде о: {driver_notes}" if driver_notes else ""
    return f"{notes_line}{driver_notes_line}"

def format_booking_description_for_passenger(from_city: str, to_city: str, dep_dt, notes: str = None, driver_notes: str = None) -> str:
    trip_desc = format_basic_details(from_city, to_city, dep_dt)
    notes_desc = format_notes_details_for_passenger(notes, driver_notes)
    return f"{trip_desc}{notes_desc}"

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