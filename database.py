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
    arrival_time TIMESTAMPTZ,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP()
)
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS cities (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    approved BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP()
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
    booked_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP(),
    notes TEXT,
    pickup_at TIMESTAMPTZ,
    seats INT DEFAULT 1
);
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS trip_search_lists (
    user_id BIGINT PRIMARY KEY,
    trip_ids INT[],          -- список знайдених поїздок
    current_index INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP()
);
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS city_popularity_per_user (
    user_id BIGINT NOT NULL,
    city_name TEXT NOT NULL,
    counter INT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP(),
    last_updated TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP(),
    PRIMARY KEY (user_id, city_name)
);
""")
conn.commit()

def save_trip_to_db(driver_id, data):
    """Insert trip only if no active trip overlaps. Returns True on success, False on overlap."""
    cursor.execute("BEGIN")
    cursor.execute("""
        WITH overlap AS (
            SELECT EXISTS (
                SELECT 1 FROM trips
                WHERE driver_id = %s
                  AND status = 'active'
                  AND departure_datetime < %s
                  AND arrival_time > %s
            ) AS has_overlap
        ),
        inserted AS (
            INSERT INTO trips (driver_id, from_city, from_points, to_city, to_points, departure_datetime, price, seats, arrival_time)
            SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s
            FROM overlap WHERE NOT has_overlap
            RETURNING id
        )
        SELECT (SELECT has_overlap FROM overlap), (SELECT id FROM inserted)
    """, (
        driver_id, data["arrival_time"], data["datetime"],
        driver_id,
        data["from_city"], data["from_points"],
        data["to_city"],  data["to_points"],
        data["datetime"], data["price"], data["seats"], data["arrival_time"]
    ))
    conn.commit()
    has_overlap, inserted_id = cursor.fetchone()
    return not has_overlap

def get_cities():
    cursor.execute("SELECT name FROM cities WHERE approved = TRUE ORDER BY name")
    rows = cursor.fetchall()
    return [r[0] for r in rows]

def add_city_if_missing(city_name: str):
    cursor.execute("""
        INSERT INTO cities (name, approved)
        VALUES (%s, FALSE)
        ON CONFLICT (name) DO NOTHING
    """, (city_name,))
    conn.commit()

def book_trip(trip_id: int, passenger_id: int, notes: str = None, seats_requested: int = 1):
    cursor.execute("BEGIN")
    # Lock the trip row so concurrent bookings can't race past the seat check
    cursor.execute("SELECT id FROM trips WHERE id = %s FOR UPDATE", (trip_id,))
    cursor.execute("""
        WITH trip AS (
            SELECT
                status,
                departure_datetime > CLOCK_TIMESTAMP() AS not_departed,
                seats::int - (
                    SELECT COALESCE(SUM(b.seats), 0) FROM bookings b
                    WHERE b.trip_id = %s AND b.status IN ('pending', 'confirmed')
                ) >= %s AS has_seats,
                (
                    SELECT COUNT(*) FROM bookings b2
                    JOIN trips t2 ON b2.trip_id = t2.id
                    WHERE b2.passenger_id = %s
                      AND b2.status IN ('pending', 'confirmed')
                      AND t2.departure_datetime < (SELECT arrival_time  FROM trips WHERE id = %s)
                      AND t2.arrival_time        > (SELECT departure_datetime FROM trips WHERE id = %s)
                ) AS overlap_count
            FROM trips WHERE id = %s
        ),
        inserted AS (
            INSERT INTO bookings (trip_id, passenger_id, status, notes, seats)
            SELECT %s, %s, 'pending', %s, %s
            FROM trip
            WHERE status = 'active'
              AND not_departed
              AND has_seats
              AND overlap_count = 0
            RETURNING id
        )
        SELECT
            (SELECT status        FROM trip),
            (SELECT not_departed  FROM trip),
            (SELECT has_seats     FROM trip),
            (SELECT overlap_count FROM trip),
            (SELECT id            FROM inserted)
    """, (trip_id, seats_requested, passenger_id, trip_id, trip_id, trip_id, trip_id, passenger_id, notes, seats_requested))
    conn.commit()
    row = cursor.fetchone()

    if not row or row[0] is None:
        return False, "not_found"
    status, not_departed, has_seats, overlap_count, inserted_id = row
    if status != 'active':
        return False, "cancelled"
    if not not_departed:
        return False, "departed"
    if not has_seats:
        return False, "no_seats"
    if overlap_count:
        return False, "overlap"
    return True, inserted_id

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
        INSERT INTO city_popularity_per_user (user_id, city_name, counter, last_updated)
        VALUES (%s, %s, 1, CLOCK_TIMESTAMP())
        ON CONFLICT (user_id, city_name)
        DO UPDATE SET counter = city_popularity_per_user.counter + 1,
                      last_updated = CLOCK_TIMESTAMP()
    """, (user_id, city_name))
    conn.commit()

def get_cities_for_user_sorted(user_id: int):
    cursor.execute("""
        SELECT city_name FROM city_popularity_per_user
        WHERE user_id = %s
        ORDER BY last_updated DESC
        LIMIT 4
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
               COALESCE(SUM(b.seats) FILTER (WHERE b.status = 'confirmed'), 0) AS confirmed_count,
               COALESCE(SUM(b.seats) FILTER (WHERE b.status = 'pending'), 0) AS pending_count,
               t.arrival_time, t.from_points, t.to_points
        FROM trips t
        LEFT JOIN bookings b ON b.trip_id = t.id
        WHERE t.driver_id = %s
          AND t.arrival_time >= CLOCK_TIMESTAMP()
          AND t.status != 'cancelled'
        GROUP BY t.id
        ORDER BY t.departure_datetime
    """, (driver_id,))
    return cursor.fetchall()

def get_driver_trip_by_id(trip_id: int):
    cursor.execute("""
        SELECT t.id, t.from_city, t.to_city, t.departure_datetime, t.price, t.seats, t.status,
               COALESCE(SUM(b.seats) FILTER (WHERE b.status = 'confirmed'), 0) AS confirmed_count,
               COALESCE(SUM(b.seats) FILTER (WHERE b.status = 'pending'), 0) AS pending_count,
               t.arrival_time, t.from_points, t.to_points
        FROM trips t
        LEFT JOIN bookings b ON b.trip_id = t.id
        WHERE t.id = %s
        GROUP BY t.id
    """, (trip_id,))
    return cursor.fetchone()

def get_trip_id_for_booking(booking_id: int):
    cursor.execute("SELECT trip_id FROM bookings WHERE id = %s", (booking_id,))
    row = cursor.fetchone()
    return row[0] if row else None

def get_bookings_for_trip(trip_id: int, status: str):
    cursor.execute("""
        SELECT id, passenger_id, notes, pickup_at, seats
        FROM bookings
        WHERE trip_id = %s AND status = %s
        ORDER BY CASE WHEN status = 'confirmed' THEN pickup_at ELSE booked_at END ASC NULLS LAST
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
        SELECT b.id, t.id, t.from_city, t.to_city, t.departure_datetime, t.price, t.seats, b.status, t.driver_id, b.notes, b.pickup_at, t.arrival_time, b.seats, t.from_points, t.to_points
        FROM bookings b
        JOIN trips t ON b.trip_id = t.id
        WHERE b.passenger_id = %s
          AND b.status IN ('pending', 'confirmed')
          AND t.arrival_time >= CLOCK_TIMESTAMP()
        ORDER BY t.departure_datetime
    """, (passenger_id,))
    return cursor.fetchall()

def get_trip_details(trip_id: int):
    cursor.execute("""
        SELECT from_city, to_city, departure_datetime, arrival_time, from_points, to_points
        FROM trips
        WHERE id = %s
    """, (trip_id,))
    return cursor.fetchone()

def get_trip_details_by_booking(booking_id: int):
    cursor.execute("""
        SELECT t.from_city, t.to_city, t.departure_datetime, b.notes, b.pickup_at, t.arrival_time, b.seats, t.from_points, t.to_points
        FROM bookings b
        JOIN trips t ON b.trip_id = t.id
        WHERE b.id = %s
    """, (booking_id,))
    return cursor.fetchone()

def set_booking_pickup_at(booking_id: int, pickup_at):
    cursor.execute("""
        UPDATE bookings SET pickup_at = %s WHERE id = %s
    """, (pickup_at, booking_id))
    conn.commit()

def search_trips_ids(from_city, to_city, from_datetime, seats_needed=1):
    cursor.execute("""
        SELECT t.id
        FROM trips t
        WHERE t.from_city = %s AND t.to_city = %s
          AND t.status = 'active'
          AND t.departure_datetime > CLOCK_TIMESTAMP()
          AND t.departure_datetime >= %s
          AND (
            t.seats::int - COALESCE((
              SELECT SUM(b.seats) FROM bookings b
              WHERE b.trip_id = t.id AND b.status IN ('pending', 'confirmed')
            ), 0)
          ) >= %s
        ORDER BY t.departure_datetime
    """, (from_city, to_city, from_datetime, seats_needed))

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
        SELECT trip_ids, current_index, CLOCK_TIMESTAMP() - created_at > INTERVAL '5 minutes'
        FROM trip_search_lists
        WHERE user_id = %s
    """, (user_id,))
    
    result = cursor.fetchone()
    if not result:
        return None

    trip_ids, index, is_expired = result

    if is_expired:
        return "expired"

    if index >= len(trip_ids):
        return None

    trip_id = trip_ids[index]

    cursor.execute("""
        SELECT t.id, t.driver_id, t.from_city, t.from_points, t.to_city, t.to_points, t.departure_datetime, t.price, t.seats,
               t.seats::int - (
                   SELECT COALESCE(SUM(b.seats), 0) FROM bookings b
                   WHERE b.trip_id = t.id AND b.status IN ('pending', 'confirmed')
               ) AS free_seats,
               t.arrival_time
        FROM trips t
        WHERE t.id = %s
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

