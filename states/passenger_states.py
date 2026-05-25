from aiogram.fsm.state import StatesGroup, State

class PassengerStates(StatesGroup):
    from_city = State()
    to_city = State()
    day = State()
    search_from_datetime = State()
    seats_requested = State()
    browsing_trips = State()
    booking_notes = State()
    booking_phone = State()
    viewing_bookings = State()
    quick_search_or_new = State()
    quick_partial_search_or_new = State()