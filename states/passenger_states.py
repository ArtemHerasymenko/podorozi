from aiogram.fsm.state import StatesGroup, State

class PassengerStates(StatesGroup):
    from_city = State()
    to_city = State()
    time = State()