import asyncio
import datetime

from aiogram import types, Bot
from zoneinfo import ZoneInfo

from database import search_trips_with_details, save_recent_search, get_city_modified_name_2
from data.route_intermediates import get_search_city_pairs
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from handlers.common import trip_word, searching_kb, seats_word

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
    bot: Bot,
    from_city: str,
    to_city: str,
    day: str,
    seats: int = 1,
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
    for trip in trips:
        trip_id, driver_id, trip_from_city, to_points, dep_dt, price, _ = trip

        try:
            chat = await bot.get_chat(driver_id)
            first_name = chat.first_name or chat.full_name.split()[0]
        except Exception:
            first_name = "Водій"

        dep_time = dep_dt.astimezone(_KYIV).strftime("%H:%M")
        destination = to_points or ""
        label = f"🕐{dep_time}  •  💰{price}грн  •  👤{first_name}\n📍 {destination}"
        trip_buttons.append([KeyboardButton(text=label)])

    kb = ReplyKeyboardMarkup(
        keyboard=trip_buttons + [
            [KeyboardButton(text="🔔 Сповістити про нові поїздки")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )
    return await message.answer("Оберіть поїздку:", reply_markup=kb)
