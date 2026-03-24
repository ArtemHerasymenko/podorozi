from aiogram.fsm.state import StatesGroup, State

class DriverStates(StatesGroup):
    from_city = State()
    from_points = State()
    to_city = State()
    to_points = State()
    day = State()
    datetime = State()
    price = State()
    seats = State()