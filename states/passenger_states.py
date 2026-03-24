from aiogram.fsm.state import StatesGroup, State

class PassengerStates(StatesGroup):
    from_city = State()
    to_city = State()
    day = State()
    datetime = State()
    browsing_trips = State()