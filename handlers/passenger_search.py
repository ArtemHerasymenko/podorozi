import asyncio
import datetime

from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from zoneinfo import ZoneInfo

from database import search_trips_with_details, save_recent_search, get_city_modified_name_2, get_trip_for_display
from data.route_intermediates import get_search_city_pairs
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from handlers.common import trip_word, searching_kb, seats_word, format_trip, send_trip_message
from states.passenger_states import PassengerStates

router = Router()

_KYIV = ZoneInfo("Europe/Kyiv")

in_search_result_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔔 Сповістити про нові поїздки")],
        [KeyboardButton(text="⬅️ Назад")],
    ],
    resize_keyboard=True,
)


async def search_and_display(
    message: types.Message,
    from_city: str,
    to_city: str,
    day: str,
    seats: int = 1,
    state: FSMContext = None,
) -> types.Message:
    now_kyiv = datetime.datetime.now(_KYIV)
    is_today = day == now_kyiv.strftime("%Y-%m-%d")

    start_of_day = datetime.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=_KYIV)
    end_of_day = start_of_day.replace(hour=23, minute=59, second=59)

    time_from = now_kyiv + datetime.timedelta(minutes=5) if is_today else start_of_day
    time_to = end_of_day

    time_from_utc = time_from.astimezone(datetime.timezone.utc)
    time_to_utc = time_to.astimezone(datetime.timezone.utc)

    day_label = "Сьогодні" if is_today else "Завтра"
    await message.answer(
        f"🔎 Шукаємо поїздки...\n{day_label}\n"
        f"{from_city} → {to_city}\n"
        f"з {time_from.strftime('%H:%M')} до {time_to.strftime('%H:%M')}\n"
        f"{seats} {seats_word(seats)}",
        reply_markup=searching_kb,
    )
    await asyncio.sleep(3)

    extra_from, extra_to = get_search_city_pairs(from_city, to_city)
    all_trips = search_trips_with_details(from_city, to_city, time_from_utc, time_to_utc, extra_from_cities=extra_from, extra_to_cities=extra_to)

    trips = [t for t in all_trips if t[6] >= seats]
    save_recent_search(message.from_user.id, from_city, to_city, "show_all", day, [t[0] for t in all_trips], seats_requested=seats)

    if not trips:
        if not all_trips:
            return await message.answer("Поїздок на цей час не знайдено, спробуйте пізніше.", reply_markup=in_search_result_kb)
        total = len(all_trips)
        return await message.answer(f"Знайдено {total} {trip_word(total)}, але вільних місць вже немає.", reply_markup=in_search_result_kb)

    total = len(all_trips)
    found = len(trips)
    if total == found:
        await message.answer(f"Знайдено {total} {trip_word(total)}.", reply_markup=in_search_result_kb)
    else:
        await message.answer(f"Знайдено {total} {trip_word(total)}, вільні місця є в {found}.", reply_markup=in_search_result_kb)

    trip_buttons = []
    trip_text_map = {}
    for i, trip in enumerate(trips):
        trip_id, _, _, to_points, dep_dt, price, _ = trip
        dep_time = dep_dt.astimezone(_KYIV).strftime("%H:%M")
        destination = to_points or ""
        price_padded = str(price).ljust(4)
        num = str(i + 1).rjust(len(str(len(trips))))
        left = f"{num}. 🕐 {dep_time}  💰{price_padded}"
        right = f"{num}. 📍 {destination}"
        trip_text_map[left] = trip_id
        trip_text_map[right] = trip_id
        trip_buttons.append([KeyboardButton(text=left), KeyboardButton(text=right)])

    if state:
        await state.update_data(trip_text_map=trip_text_map)

    kb = ReplyKeyboardMarkup(
        keyboard=trip_buttons + [
            [KeyboardButton(text="🔔 Сповістити про нові поїздки")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )
    return await message.answer("Оберіть поїздку (ліва кнопка):", reply_markup=kb)


@router.message(PassengerStates.browsing_trip_list)
async def view_trip_from_search(message: types.Message, state: FSMContext):
    data = await state.get_data()
    trip_text_map = data.get("trip_text_map", {})
    trip_id = trip_text_map.get(message.text)
    if not trip_id:
        return
    trip = get_trip_for_display(trip_id)
    if not trip:
        await message.answer("Поїздку не знайдено.")
        return
    driver_chat = None
    try:
        driver_chat = await message.bot.get_chat(trip[1])
        driver_name = driver_chat.full_name
    except:
        driver_name = None
    trip_text = format_trip(trip, 0, 1, driver_name, is_own=(trip[1] == message.from_user.id))
    prev_msg_id = data.get("trip_detail_message_id")
    if prev_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=prev_msg_id)
        except Exception:
            pass
    sent = await send_trip_message(message.answer, trip_text, trip[0], 1, trip[1], driver_chat.username if driver_chat else None, 0, show_keyboard=False)
    await state.update_data(trip_detail_message_id=sent.message_id)
