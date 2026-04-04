from aiogram.fsm.state import StatesGroup, State

class PassengerStates(StatesGroup):
    from_city = State()
    to_city = State()
    day = State()
    datetime = State()
    seats_requested = State()
    browsing_trips = State()
    booking_notes = State()