import psycopg2
from config import DATABASE_URL
from data.cities import CITIES
from handlers.common import generate_datetime

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS trips (
    id SERIAL PRIMARY KEY,
    driver_id BIGINT,
    from_city TEXT,
    from_points TEXT,
    to_city TEXT,
    to_points TEXT,
    departure_datetime TIMESTAMPTZ,
    price TEXT,
    seats TEXT,
    status TEXT DEFAULT 'active'
)
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS cities (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
)
""")
conn.commit()

for city in CITIES:
    cursor.execute("""
        INSERT INTO cities (name)
        VALUES (%s)
        ON CONFLICT (name) DO NOTHING
    """, (city,))
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS bookings (
    id SERIAL PRIMARY KEY,
    trip_id INT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'pending',
    passenger_id BIGINT NOT NULL,  -- Telegram user id
    booked_at TIMESTAMP DEFAULT CLOCK_TIMESTAMP(),
    notes TEXT,
    driver_notes TEXT
);
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS trip_search_lists (
    user_id BIGINT PRIMARY KEY,
    trip_ids INT[],          -- список знайдених поїздок
    current_index INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CLOCK_TIMESTAMP()
);
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS city_popularity_per_user (
    user_id BIGINT NOT NULL,
    city_name TEXT NOT NULL,
    counter INT DEFAULT 1,
    PRIMARY KEY (user_id, city_name)
);
""")
conn.commit()

def save_trip_to_db(driver_id, data):
    
    cursor.execute("""
        INSERT INTO trips (driver_id, from_city, from_points, to_city, to_points, departure_datetime, price, seats)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        driver_id,
        data["from_city"],
        data["from_points"],
        data["to_city"],
        data["to_points"],
        data["datetime"],
        data["price"],
        data["seats"]
    ))
    conn.commit()

def get_cities():
    cursor.execute("SELECT name FROM cities ORDER BY name")
    rows = cursor.fetchall()
    return [r[0] for r in rows]

def book_trip(trip_id: int, passenger_id: int, notes: str = None) -> bool:

    cursor.execute("""
        INSERT INTO bookings (trip_id, passenger_id, status, notes)
        SELECT %s, %s, 'pending', %s
        WHERE EXISTS (SELECT 1 FROM trips WHERE id = %s AND status = 'active')
        RETURNING id
    """, (trip_id, passenger_id, notes, trip_id))
    conn.commit()
    row = cursor.fetchone()
    if not row:
        return False, None

    return True, row[0]

def update_booking_status(booking_id: int, new_status: str, allowed_prev_statuses: list[str]):
    cursor.execute("""
        WITH prev AS (
            SELECT status FROM bookings WHERE id = %s
        ),
        updated AS (
            UPDATE bookings SET status = %s
            WHERE id = %s AND status = ANY(%s)
            RETURNING status
        )
        SELECT
            (SELECT status FROM prev),
            COALESCE(
                (SELECT status FROM updated),
                (SELECT status FROM prev)
            )
    """, (booking_id, new_status, booking_id, allowed_prev_statuses))
    conn.commit()
    row = cursor.fetchone()
    return (row[0], row[1]) if row else (None, None)

def increment_city_popularity(user_id: int, city_name: str):
    cursor.execute("""
        INSERT INTO city_popularity_per_user (user_id, city_name, counter)
        VALUES (%s, %s, 1)
        ON CONFLICT (user_id, city_name)
        DO UPDATE SET counter = city_popularity_per_user.counter + 1
    """, (user_id, city_name))
    conn.commit()

def get_cities_for_user_sorted(user_id: int):
    # Get popular cities for the user, sorted by counter DESC
    cursor.execute("""
        SELECT city_name FROM city_popularity_per_user
        WHERE user_id = %s
        ORDER BY counter DESC, city_name ASC
    """, (user_id,))
    popular = [r[0] for r in cursor.fetchall()]

    # Get all cities
    all_cities = get_cities()

    # Others: cities not in popular, sorted alphabetically
    others = sorted([c for c in all_cities if c not in popular])

    return popular, others

def get_driver_trips(driver_id: int):
    cursor.execute("""
        SELECT t.id, t.from_city, t.to_city, t.departure_datetime, t.price, t.seats, t.status,
               COUNT(b.id) FILTER (WHERE b.status = 'confirmed') AS confirmed_count,
               COUNT(b.id) FILTER (WHERE b.status = 'pending') AS pending_count
        FROM trips t
        LEFT JOIN bookings b ON b.trip_id = t.id
        WHERE t.driver_id = %s
          AND t.departure_datetime >= CLOCK_TIMESTAMP() - INTERVAL '2 hours'
          AND t.status != 'cancelled'
        GROUP BY t.id
        ORDER BY t.departure_datetime
    """, (driver_id,))
    return cursor.fetchall()

def get_bookings_for_trip(trip_id: int, status: str):
    cursor.execute("""
        SELECT id, passenger_id, notes, driver_notes
        FROM bookings
        WHERE trip_id = %s AND status = %s
    """, (trip_id, status))
    return cursor.fetchall()

def cancel_trip(trip_id: int, driver_id: int):
    cursor.execute("""
        WITH cancelled_trip AS (
            UPDATE trips SET status = 'cancelled'
            WHERE id = %s AND driver_id = %s AND status = 'active'
            RETURNING id
        )
        SELECT
            (SELECT COUNT(*) FROM cancelled_trip) > 0,
            ARRAY(SELECT id FROM bookings WHERE trip_id IN (SELECT id FROM cancelled_trip))
    """, (trip_id, driver_id))
    conn.commit()
    row = cursor.fetchone()
    if not row or not row[0]:
        return False, []
    return True, row[1] or []

def get_driver_id(trip_id: int) -> int:
    cursor.execute("SELECT driver_id FROM trips WHERE id = %s", (trip_id,))
    return cursor.fetchone()[0]

def get_driver_id_by_booking(booking_id: int) -> int:
    cursor.execute("""
        SELECT t.driver_id FROM bookings b
        JOIN trips t ON b.trip_id = t.id
        WHERE b.id = %s
    """, (booking_id,))
    return cursor.fetchone()[0]

def get_passenger_id(booking_id: int) -> int:
    cursor.execute("SELECT passenger_id FROM bookings WHERE id = %s", (booking_id,))
    return cursor.fetchone()[0]

def get_passenger_bookings(passenger_id: int):
    cursor.execute("""
        SELECT b.id, t.id, t.from_city, t.to_city, t.departure_datetime, t.price, t.seats, b.status, t.driver_id, b.notes, b.driver_notes
        FROM bookings b
        JOIN trips t ON b.trip_id = t.id
        WHERE b.passenger_id = %s
          AND b.status IN ('pending', 'confirmed')
          AND t.departure_datetime >= CLOCK_TIMESTAMP() - INTERVAL '2 hours'
        ORDER BY t.departure_datetime
    """, (passenger_id,))
    return cursor.fetchall()

def get_trip_details(trip_id: int):
    cursor.execute("""
        SELECT from_city, to_city, departure_datetime
        FROM trips
        WHERE id = %s
    """, (trip_id,))
    return cursor.fetchone()

def get_trip_details_by_booking(booking_id: int):
    cursor.execute("""
        SELECT t.from_city, t.to_city, t.departure_datetime, b.notes, b.driver_notes
        FROM bookings b
        JOIN trips t ON b.trip_id = t.id
        WHERE b.id = %s
    """, (booking_id,))
    return cursor.fetchone()

def set_booking_driver_notes(booking_id: int, driver_notes: str):
    cursor.execute("""
        UPDATE bookings SET driver_notes = %s WHERE id = %s
    """, (driver_notes, booking_id))
    conn.commit()

def search_trips_ids(from_city, to_city):
    cursor.execute("""
        SELECT id
        FROM trips
        WHERE from_city = %s AND to_city = %s
        ORDER BY departure_datetime
    """, (from_city, to_city))

    return [row[0] for row in cursor.fetchall()]

def create_trip_search_list(user_id: int, trips: list[int]):
    cursor.execute("""
        INSERT INTO trip_search_lists (user_id, trip_ids, current_index, created_at)
        VALUES (%s, %s, 0, CLOCK_TIMESTAMP())
        ON CONFLICT (user_id) DO UPDATE
        SET trip_ids = EXCLUDED.trip_ids,
            current_index = 0,
            created_at = CLOCK_TIMESTAMP()
    """, (user_id, trips))
    conn.commit()

def get_current_trip_from_search_list(user_id: int):
    cursor.execute("""
        SELECT trip_ids, current_index
        FROM trip_search_lists
        WHERE user_id = %s
    """, (user_id,))
    
    result = cursor.fetchone()
    if not result:
        return None

    trip_ids, index = result

    if index >= len(trip_ids):
        return None

    trip_id = trip_ids[index]

    cursor.execute("""
        SELECT id, driver_id, from_city, from_points, to_city, to_points, departure_datetime, price, seats
        FROM trips
        WHERE id = %s
    """, (trip_id,))
    
    return cursor.fetchone(), index, len(trip_ids)

def increase_trip_search_list_index(user_id: int):
    cursor.execute("""
        UPDATE trip_search_lists
        SET current_index = (
            CASE 
                WHEN current_index = cardinality(trip_ids) - 1 THEN 0
                ELSE current_index + 1
            END
        )
        WHERE user_id = %s
    """, (user_id,))
    conn.commit()


def decrease_trip_search_list_index(user_id: int):
    cursor.execute("""
        UPDATE trip_search_lists
        SET current_index = (
            CASE 
                WHEN current_index = 0 THEN cardinality(trip_ids) - 1
                ELSE current_index - 1
            END
        )
        WHERE user_id = %s
    """, (user_id,))
    conn.commit()

