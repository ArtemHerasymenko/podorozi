import logging
from aiogram import Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from states.driver_states import DriverStates
from database import get_template_by_id, deactivate_template, get_driver_templates
from handlers.common import quick_day_kb, back_only_kb, safe_answer, handle_day_input, handle_time_input, finish_trip_creation, create_trip_kb
import asyncio

router = Router()


def _template_text(t, index, total):
    t_id, from_city, to_city, from_points, to_points, car, phone, price = t
    position = f"Шаблон # {index + 1}/{total}\n\n" if total > 1 else ""
    from_str = f"<b>{from_city}</b> ({from_points})" if from_points else f"<b>{from_city}</b>"
    to_str = f"<b>{to_city}</b> ({to_points})" if to_points else f"<b>{to_city}</b>"
    lines = [f"{position}➡️ {from_str}\n🏁 {to_str}", f"💰 {price} грн"]
    if car:
        lines.append(f"🚘 {car}")
    if phone:
        lines.append(f"📞 {phone}")
    return "\n".join(lines)

def _template_kb(index, total, t_id):
    nav = []
    if index > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Попередній", callback_data="tpl_prev"))
    if index < total - 1:
        nav.append(InlineKeyboardButton(text="➡️ Наступний", callback_data="tpl_next"))
    rows = [nav] if nav else []
    rows.append([InlineKeyboardButton(text="✅ Використати", callback_data=f"use_template:{t_id}")])
    rows.append([InlineKeyboardButton(text="🗑 Видалити", callback_data=f"tpl_remove:{t_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(DriverStates.choosing_creation_method, lambda m: m.text == "📋 Використати шаблон")
async def trip_use_template(message: types.Message, state: FSMContext):
    await message.answer("Шукаємо...", reply_markup=back_only_kb)
    templates = get_driver_templates(message.from_user.id)
    if not templates:
        await message.answer("Шаблонів ще немає. Створіть поїздку і шаблон збережеться тут автоматично.", reply_markup=create_trip_kb)
        return
    await state.update_data(tpl_index=0)
    await state.set_state(DriverStates.choosing_template)
    t = templates[0]
    tpl_msg = await message.answer(
        _template_text(t, 0, len(templates)),
        reply_markup=_template_kb(0, len(templates), t[0]),
        parse_mode="HTML"
    )
    await state.update_data(tpl_msg_id=tpl_msg.message_id)




@router.callback_query(DriverStates.choosing_template, lambda c: c.data in ("tpl_prev", "tpl_next"))
async def template_nav(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    templates = get_driver_templates(callback.from_user.id)
    index = data["tpl_index"] + (1 if callback.data == "tpl_next" else -1)
    index = max(0, min(index, len(templates) - 1))
    await state.update_data(tpl_index=index)
    t = templates[index]
    await callback.message.edit_text(
        _template_text(t, index, len(templates)),
        reply_markup=_template_kb(index, len(templates), t[0]),
        parse_mode="HTML"
    )
    await safe_answer(callback)


@router.callback_query(DriverStates.choosing_template, lambda c: c.data and c.data.startswith("tpl_remove:"))
async def remove_template(callback: types.CallbackQuery, state: FSMContext):
    template_id = int(callback.data.split(":")[1])
    deactivate_template(template_id, callback.from_user.id)
    templates = get_driver_templates(callback.from_user.id)
    if not templates:
        await state.set_state(DriverStates.choosing_creation_method)
        await callback.message.edit_text("Шаблонів більше немає.", reply_markup=None)
        await callback.message.answer("Використати шаблон, чи створити поїздку з нуля?", reply_markup=create_trip_kb)
    else:
        data = await state.get_data()
        index = min(data.get("tpl_index", 0), len(templates) - 1)
        await state.update_data(tpl_index=index)
        t = templates[index]
        await callback.message.edit_text(
            _template_text(t, index, len(templates)),
            reply_markup=_template_kb(index, len(templates), t[0]),
            parse_mode="HTML"
        )
    await safe_answer(callback)



@router.callback_query(DriverStates.choosing_template, lambda c: c.data and c.data.startswith("use_template:"))
async def apply_template(callback: types.CallbackQuery, state: FSMContext):
    template_id = int(callback.data.split(":")[1])
    template = get_template_by_id(template_id, callback.from_user.id)
    if not template:
        await callback.message.answer("Шаблон не знайдено.")
        await safe_answer(callback)
        return
    _, from_city, to_city, from_points, to_points, car, phone, price = template
    await state.update_data(
        template_id=template_id,
        from_city=from_city, to_city=to_city,
        from_points=from_points or "", to_points=to_points or "",
        car_description=car, driver_phone=phone, price=price
    )
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"Оберіть день:", reply_markup=quick_day_kb())
    await state.set_state(DriverStates.day_template)
    await safe_answer(callback)


@router.message(StateFilter(DriverStates.choosing_template, DriverStates.day_template, DriverStates.datetime_template, DriverStates.seats_template), lambda m: m.text == "⬅️ Назад")
async def template_flow_back(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tpl_msg_id = data.get("tpl_msg_id")
    if tpl_msg_id:
        try:
            await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=tpl_msg_id, reply_markup=None)
        except Exception as e:
            logging.warning("Failed to clear template message reply markup: %s", e)
    await state.set_state(DriverStates.choosing_creation_method)
    await message.answer("Використати шаблон, чи створити поїздку з нуля?", reply_markup=create_trip_kb)


@router.message(DriverStates.day_template, lambda m: m.text != "⬅️ Назад")
async def day(message: types.Message, state: FSMContext):
    await handle_day_input(message, state, DriverStates.datetime_template)


@router.message(DriverStates.datetime_template, lambda m: m.text != "⬅️ Назад")
async def time(message: types.Message, state: FSMContext):
    await handle_time_input(message, state, DriverStates.seats_template)


@router.message(DriverStates.seats_template, lambda m: m.text != "⬅️ Назад")
async def seats(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit() or int(message.text) < 1:
        await message.answer("Будь ласка, введіть кількість місць цифрою.")
        return
    await state.update_data(seats=message.text)
    data = await state.get_data()
    await finish_trip_creation(message.from_user.id, data, message.answer, state, bot=message.bot)
