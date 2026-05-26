import psycopg2
from config import DATABASE_URL
from data.cities import CITIES
from data.route_descriptions import ROUTE_DESCRIPTIONS
from data.route_tags import ROUTE_TAGS
from data.city_landmarks import CITY_LANDMARKS
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()
cursor.execute("SET TIME ZONE 'UTC'")

cursor.execute("""
CREATE TABLE IF NOT EXISTS trips (
    id SERIAL PRIMARY KEY,
    driver_id BIGINT,
    driver_phone TEXT,
    car_description TEXT,
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
    modified_name TEXT,
    modified_name_2 TEXT,
    modified_name_3 TEXT,
    approved BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP()
)
""")
conn.commit()

for city, modified_name, modified_name_2, modified_name_3 in CITIES:
    cursor.execute("""
        INSERT INTO cities (name, modified_name, modified_name_2, modified_name_3)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (name) DO NOTHING
    """, (city, modified_name, modified_name_2, modified_name_3))
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS bookings (
    id SERIAL PRIMARY KEY,
    trip_id INT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'pending',
    passenger_id BIGINT NOT NULL,
    booked_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP(),
    notes TEXT,
    passenger_phone TEXT,
    pickup_at TIMESTAMPTZ,
    seats INT DEFAULT 1,
    from_city TEXT,
    to_city TEXT
);
""")
conn.commit()

cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS from_city TEXT")
cursor.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS to_city TEXT")
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS route_descriptions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 0, -- 0 для глобальних описів, інші для користувацьких
    city_name TEXT NOT NULL,
    is_departure BOOLEAN NOT NULL,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP(),
    UNIQUE (user_id, city_name, is_departure, description)
);
""")
conn.commit()

for city_name, is_departure, description in ROUTE_DESCRIPTIONS:
    cursor.execute("""
        INSERT INTO route_descriptions (user_id, city_name, is_departure, description)
        VALUES (0, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """, (city_name, is_departure, description))
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS route_tags (
    id SERIAL PRIMARY KEY,
    tag TEXT NOT NULL,
    city_name TEXT NOT NULL,
    driver_id BIGINT NOT NULL,
    count INT NOT NULL DEFAULT 1,
    last_updated_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP(),
    UNIQUE (tag, city_name, driver_id)
);
""")
conn.commit()

for tag, city_name in ROUTE_TAGS:
    cursor.execute("""
        INSERT INTO route_tags (tag, city_name, driver_id)
        VALUES (%s, %s, 0)
        ON CONFLICT DO NOTHING
    """, (tag, city_name))
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS driver_info (
    id SERIAL PRIMARY KEY,
    driver_id BIGINT NOT NULL,
    car_description TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP(),
    UNIQUE (driver_id, car_description)
);
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS phones (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    phone_number TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP(),
    UNIQUE (user_id, phone_number)
);
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS feedbacks (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    mode TEXT NOT NULL,
    feedback_text TEXT,
    file_id TEXT,
    created_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP()
);
""")
cursor.execute("ALTER TABLE feedbacks ADD COLUMN IF NOT EXISTS file_id TEXT")
cursor.execute("ALTER TABLE feedbacks ALTER COLUMN feedback_text DROP NOT NULL")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS recent_searches (
    id SERIAL PRIMARY KEY,
    passenger_id BIGINT NOT NULL,
    from_city TEXT NOT NULL,
    to_city TEXT NOT NULL,
    time_str TEXT NOT NULL,
    search_for_day TEXT NOT NULL,
    searched_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP()
);
""")
cursor.execute("ALTER TABLE recent_searches ADD COLUMN IF NOT EXISTS search_for_day TEXT NOT NULL DEFAULT ''")
cursor.execute("ALTER TABLE recent_searches ADD COLUMN IF NOT EXISTS trip_ids INTEGER[] DEFAULT NULL")
cursor.execute("ALTER TABLE recent_searches DROP COLUMN IF EXISTS counter")
cursor.execute("ALTER TABLE recent_searches ADD COLUMN IF NOT EXISTS seats_requested INTEGER NOT NULL DEFAULT 1")
cursor.execute("""
    DO $$
    DECLARE
        con_name TEXT;
    BEGIN
        SELECT conname INTO con_name
        FROM pg_constraint
        WHERE conrelid = 'recent_searches'::regclass
          AND contype = 'u'
          AND conname LIKE 'recent_searches_passenger_id_from_city_to_city_time_str%';
        IF con_name IS NOT NULL THEN
            EXECUTE 'ALTER TABLE recent_searches DROP CONSTRAINT ' || quote_ident(con_name);
        END IF;
    END $$
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS city_landmarks (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 0,
    city_name TEXT NOT NULL,
    landmark TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP(),
    UNIQUE (user_id, city_name, landmark)
)
""")
cursor.execute("ALTER TABLE city_landmarks ADD COLUMN IF NOT EXISTS user_id BIGINT NOT NULL DEFAULT 0")
cursor.execute("ALTER TABLE city_landmarks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP()")
cursor.execute("""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'city_landmarks_city_name_landmark_key'
        ) THEN
            ALTER TABLE city_landmarks DROP CONSTRAINT city_landmarks_city_name_landmark_key;
        END IF;
    END $$
""")
cursor.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'city_landmarks_user_id_city_name_landmark_key'
        ) THEN
            ALTER TABLE city_landmarks ADD CONSTRAINT city_landmarks_user_id_city_name_landmark_key UNIQUE (user_id, city_name, landmark);
        END IF;
    END $$
""")
conn.commit()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_details (
        user_id BIGINT,
        user_name TEXT,
        updated_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP(),
        UNIQUE (user_id, user_name)
    )
""")
conn.commit()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS trip_templates (
        id SERIAL PRIMARY KEY,
        driver_id BIGINT NOT NULL,
        from_city TEXT NOT NULL,
        to_city TEXT NOT NULL,
        from_points TEXT,
        to_points TEXT,
        car_description TEXT,
        driver_phone TEXT,
        price TEXT,
        created_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP(),
        updated_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP(),
        active BOOLEAN NOT NULL DEFAULT TRUE,
        UNIQUE (driver_id, from_city, to_city, from_points, to_points)
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS template_times (
        id SERIAL PRIMARY KEY,
        template_id INTEGER NOT NULL REFERENCES trip_templates(id) ON DELETE CASCADE,
        time TEXT NOT NULL,
        count INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP(),
        updated_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP(),
        UNIQUE (template_id, time)
    )
""")
conn.commit()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id BIGSERIAL PRIMARY KEY,
        from_user_id BIGINT,
        to_user_id BIGINT,
        text TEXT,
        created_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP()
    )
""")
conn.commit()

for city_name, landmark in CITY_LANDMARKS:
    cursor.execute("""
        INSERT INTO city_landmarks (user_id, city_name, landmark)
        VALUES (0, %s, %s)
        ON CONFLICT DO NOTHING
    """, (city_name, landmark))

cursor.execute("DELETE FROM city_landmarks WHERE city_name = 'Полтава' AND landmark = 'Полтіхніка'")
conn.commit()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS search_subscriptions (
        id SERIAL PRIMARY KEY,
        passenger_id BIGINT NOT NULL,
        from_city TEXT NOT NULL,
        to_city TEXT NOT NULL,
        search_for_day TEXT NOT NULL,
        seats_requested INTEGER NOT NULL DEFAULT 1,
        from_time TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
        to_time TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP(),
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ DEFAULT CLOCK_TIMESTAMP(),
        notified_at TIMESTAMPTZ,
        UNIQUE (passenger_id, from_city, to_city, search_for_day)
    )
""")
cursor.execute("ALTER TABLE search_subscriptions ADD COLUMN IF NOT EXISTS from_time TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP()")
cursor.execute("ALTER TABLE search_subscriptions ADD COLUMN IF NOT EXISTS to_time TIMESTAMPTZ NOT NULL DEFAULT CLOCK_TIMESTAMP()")
cursor.execute("ALTER TABLE search_subscriptions ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE")
conn.commit()

def save_trip_to_db(driver_id, data):
    """Insert trip only if no active trip overlaps. Returns trip_id on success, None on overlap."""
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
            INSERT INTO trips (driver_id, driver_phone, car_description, from_city, from_points, to_city, to_points, departure_datetime, price, seats, arrival_time)
            SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            FROM overlap WHERE NOT has_overlap
            RETURNING id
        )
        SELECT (SELECT has_overlap FROM overlap), (SELECT id FROM inserted)
    """, (
        driver_id, data["arrival_time"], data["datetime"],
        driver_id,
        data.get("driver_phone"),
        data.get("car_description"),
        data["from_city"], data["from_points"],
        data["to_city"],  data["to_points"],
        data["datetime"], data["price"], data["seats"], data["arrival_time"]
    ))
    conn.commit()
    has_overlap, inserted_id = cursor.fetchone()
    return inserted_id if not has_overlap else None

def get_cities():
    cursor.execute("SELECT name FROM cities WHERE approved = TRUE ORDER BY name")
    rows = cursor.fetchall()
    return [r[0] for r in rows]

def get_city_modified_name(city_name: str):
    cursor.execute("SELECT COALESCE(modified_name, name) FROM cities WHERE name = %s", (city_name,))
    row = cursor.fetchone()
    return row[0] if row else city_name

def get_city_modified_name_2(city_name: str):
    cursor.execute("SELECT modified_name_2 FROM cities WHERE name = %s", (city_name,))
    row = cursor.fetchone()
    return row[0] if row else city_name

def get_city_modified_name_3(city_name: str):
    cursor.execute("SELECT modified_name_3 FROM cities WHERE name = %s", (city_name,))
    row = cursor.fetchone()
    return row[0] if row else city_name

def get_city_landmarks(city_name: str, user_id: int = 0) -> list[str]:
    cursor.execute("""
        SELECT landmark FROM city_landmarks
        WHERE city_name = %s AND user_id = %s
        ORDER BY updated_at DESC
    """, (city_name, user_id))
    user_rows = [row[0] for row in cursor.fetchall()]
    cursor.execute("""
        SELECT landmark FROM city_landmarks
        WHERE city_name = %s AND user_id = 0
        ORDER BY updated_at DESC
    """, (city_name,))
    general_rows = [row[0] for row in cursor.fetchall() if row[0] not in user_rows]
    return (user_rows + general_rows)[:16]

def save_user_landmark(user_id: int, city_name: str, landmark: str):
    cursor.execute("""
        INSERT INTO city_landmarks (user_id, city_name, landmark)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, city_name, landmark) DO UPDATE SET updated_at = CLOCK_TIMESTAMP()
    """, (user_id, city_name, landmark))
    conn.commit()

def add_city_if_missing(city_name: str):
    cursor.execute("""
        INSERT INTO cities (name, modified_name, modified_name_2, modified_name_3, approved)
        VALUES (%s, %s, %s, %s, FALSE)
        ON CONFLICT (name) DO NOTHING
    """, (city_name, city_name, city_name, city_name))
    conn.commit()

def book_trip(trip_id: int, passenger_id: int, notes: str = None, seats_requested: int = 1, passenger_phone: str = None, from_city: str = None, to_city: str = None):
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
            INSERT INTO bookings (trip_id, passenger_id, status, notes, seats, passenger_phone, from_city, to_city)
            SELECT %s, %s, 'pending', %s, %s, %s, %s, %s
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
    """, (trip_id, seats_requested, passenger_id, trip_id, trip_id, trip_id, trip_id, passenger_id, notes, seats_requested, passenger_phone, from_city, to_city))
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
    popular = sorted(r[0] for r in cursor.fetchall())

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
                             t.arrival_time, t.from_points, t.to_points, t.driver_phone, t.car_description
        FROM trips t
        LEFT JOIN bookings b ON b.trip_id = t.id
        WHERE t.driver_id = %s
          AND t.arrival_time >= CLOCK_TIMESTAMP()
          AND t.status != 'cancelled'
        GROUP BY t.id
        ORDER BY t.departure_datetime
    """, (driver_id,))
    return cursor.fetchall()

def get_latest_driver_past_trip(driver_id: int):
    cursor.execute("""
        SELECT t.id, t.from_city, t.to_city, t.departure_datetime, t.price, t.seats, t.status,
               COALESCE(SUM(b.seats) FILTER (WHERE b.status = 'confirmed'), 0) AS confirmed_count,
               COALESCE(SUM(b.seats) FILTER (WHERE b.status = 'pending'), 0) AS pending_count,
                             t.arrival_time, t.from_points, t.to_points, t.driver_phone, t.car_description
        FROM trips t
        LEFT JOIN bookings b ON b.trip_id = t.id
        WHERE t.driver_id = %s
          AND t.arrival_time < CLOCK_TIMESTAMP()
        GROUP BY t.id
        ORDER BY t.departure_datetime DESC, t.id DESC
        LIMIT 1
    """, (driver_id,))
    return cursor.fetchone()

def get_prev_driver_past_trip(driver_id: int, current_trip_id: int):
    """Trip that departed before the current one (older)."""
    cursor.execute("""
        WITH current AS (SELECT departure_datetime, id FROM trips WHERE id = %s)
        SELECT t.id, t.from_city, t.to_city, t.departure_datetime, t.price, t.seats, t.status,
               COALESCE(SUM(b.seats) FILTER (WHERE b.status = 'confirmed'), 0) AS confirmed_count,
               COALESCE(SUM(b.seats) FILTER (WHERE b.status = 'pending'), 0) AS pending_count,
               t.arrival_time, t.from_points, t.to_points, t.driver_phone, t.car_description
        FROM trips t
        LEFT JOIN bookings b ON b.trip_id = t.id, current
        WHERE t.driver_id = %s
          AND t.arrival_time < CLOCK_TIMESTAMP()
          AND (
              t.departure_datetime < current.departure_datetime
              OR (t.departure_datetime = current.departure_datetime AND t.id < current.id)
          )
        GROUP BY t.id
        ORDER BY t.departure_datetime DESC, t.id DESC
        LIMIT 1
    """, (current_trip_id, driver_id))
    return cursor.fetchone()

def get_next_driver_past_trip(driver_id: int, current_trip_id: int):
    """Trip that departed after the current one (newer, but still in the past)."""
    cursor.execute("""
        WITH current AS (SELECT departure_datetime, id FROM trips WHERE id = %s)
        SELECT t.id, t.from_city, t.to_city, t.departure_datetime, t.price, t.seats, t.status,
               COALESCE(SUM(b.seats) FILTER (WHERE b.status = 'confirmed'), 0) AS confirmed_count,
               COALESCE(SUM(b.seats) FILTER (WHERE b.status = 'pending'), 0) AS pending_count,
               t.arrival_time, t.from_points, t.to_points, t.driver_phone, t.car_description
        FROM trips t
        LEFT JOIN bookings b ON b.trip_id = t.id, current
        WHERE t.driver_id = %s
          AND t.arrival_time < CLOCK_TIMESTAMP()
          AND (
              t.departure_datetime > current.departure_datetime
              OR (t.departure_datetime = current.departure_datetime AND t.id > current.id)
          )
        GROUP BY t.id
        ORDER BY t.departure_datetime ASC, t.id ASC
        LIMIT 1
    """, (current_trip_id, driver_id))
    return cursor.fetchone()

def get_driver_past_trip_position(driver_id: int, trip_id: int):
    """Returns (rank, total) where rank=1 is most recent."""
    cursor.execute("""
        WITH current AS (SELECT departure_datetime, id FROM trips WHERE id = %s)
        SELECT
            (SELECT COUNT(*) FROM trips, current
             WHERE driver_id = %s
               AND arrival_time < CLOCK_TIMESTAMP()
               AND (
                   trips.departure_datetime > current.departure_datetime
                   OR (trips.departure_datetime = current.departure_datetime AND trips.id >= current.id)
               )) AS rank,
            (SELECT COUNT(*) FROM trips
             WHERE driver_id = %s
               AND arrival_time < CLOCK_TIMESTAMP()) AS total
    """, (trip_id, driver_id, driver_id))
    return cursor.fetchone()

def get_driver_trip_by_id(trip_id: int):
    cursor.execute("""
        SELECT t.id, t.from_city, t.to_city, t.departure_datetime, t.price, t.seats, t.status,
               COALESCE(SUM(b.seats) FILTER (WHERE b.status = 'confirmed'), 0) AS confirmed_count,
               COALESCE(SUM(b.seats) FILTER (WHERE b.status = 'pending'), 0) AS pending_count,
               t.arrival_time, t.from_points, t.to_points, t.driver_phone, t.car_description
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
        SELECT id, passenger_id, notes, pickup_at, seats, passenger_phone, from_city, to_city
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
        SELECT b.id, t.id, t.from_city, t.to_city, t.departure_datetime, t.price, t.seats, b.status, t.driver_id, b.notes, b.pickup_at, t.arrival_time, b.seats, t.from_points, t.to_points, t.driver_phone, b.passenger_phone, t.car_description, b.from_city, b.to_city
        FROM bookings b
        JOIN trips t ON b.trip_id = t.id
        WHERE b.passenger_id = %s
          AND b.status IN ('pending', 'confirmed')
          AND t.arrival_time >= CLOCK_TIMESTAMP()
        ORDER BY t.departure_datetime
    """, (passenger_id,))
    return cursor.fetchall()

def get_latest_passenger_past_booking(passenger_id: int):
    cursor.execute("""
        SELECT b.id, t.from_city, t.to_city, t.departure_datetime, t.price, b.status, t.driver_id, b.notes, b.pickup_at, t.arrival_time, b.seats, t.from_points, t.to_points, t.driver_phone, b.passenger_phone, t.car_description, b.from_city, b.to_city
        FROM bookings b
        JOIN trips t ON b.trip_id = t.id
        WHERE b.passenger_id = %s
          AND t.arrival_time < CLOCK_TIMESTAMP()
        ORDER BY t.departure_datetime DESC, b.id DESC
        LIMIT 1
    """, (passenger_id,))
    return cursor.fetchone()

def get_prev_passenger_past_booking(passenger_id: int, current_booking_id: int):
    cursor.execute("""
        WITH current AS (
            SELECT t2.departure_datetime, b2.id
            FROM bookings b2 JOIN trips t2 ON b2.trip_id = t2.id
            WHERE b2.id = %s
        )
        SELECT b.id, t.from_city, t.to_city, t.departure_datetime, t.price, b.status, t.driver_id, b.notes, b.pickup_at, t.arrival_time, b.seats, t.from_points, t.to_points, t.driver_phone, b.passenger_phone, t.car_description, b.from_city, b.to_city
        FROM bookings b
        JOIN trips t ON b.trip_id = t.id, current
        WHERE b.passenger_id = %s
          AND t.arrival_time < CLOCK_TIMESTAMP()
          AND (
              t.departure_datetime < current.departure_datetime
              OR (t.departure_datetime = current.departure_datetime AND b.id < current.id)
          )
        ORDER BY t.departure_datetime DESC, b.id DESC
        LIMIT 1
    """, (current_booking_id, passenger_id))
    return cursor.fetchone()

def get_next_passenger_past_booking(passenger_id: int, current_booking_id: int):
    cursor.execute("""
        WITH current AS (
            SELECT t2.departure_datetime, b2.id
            FROM bookings b2 JOIN trips t2 ON b2.trip_id = t2.id
            WHERE b2.id = %s
        )
        SELECT b.id, t.from_city, t.to_city, t.departure_datetime, t.price, b.status, t.driver_id, b.notes, b.pickup_at, t.arrival_time, b.seats, t.from_points, t.to_points, t.driver_phone, b.passenger_phone, t.car_description, b.from_city, b.to_city
        FROM bookings b
        JOIN trips t ON b.trip_id = t.id, current
        WHERE b.passenger_id = %s
          AND t.arrival_time < CLOCK_TIMESTAMP()
          AND (
              t.departure_datetime > current.departure_datetime
              OR (t.departure_datetime = current.departure_datetime AND b.id > current.id)
          )
        ORDER BY t.departure_datetime ASC, b.id ASC
        LIMIT 1
    """, (current_booking_id, passenger_id))
    return cursor.fetchone()

def get_passenger_past_booking_position(passenger_id: int, booking_id: int):
    """Returns (rank, total) where rank=1 is most recent."""
    cursor.execute("""
        WITH current AS (
            SELECT t2.departure_datetime, b2.id
            FROM bookings b2 JOIN trips t2 ON b2.trip_id = t2.id
            WHERE b2.id = %s
        )
        SELECT
            (SELECT COUNT(*) FROM bookings b JOIN trips t ON b.trip_id = t.id, current
             WHERE b.passenger_id = %s
               AND t.arrival_time < CLOCK_TIMESTAMP()
               AND (
                   t.departure_datetime > current.departure_datetime
                   OR (t.departure_datetime = current.departure_datetime AND b.id >= current.id)
               )) AS rank,
            (SELECT COUNT(*) FROM bookings b JOIN trips t ON b.trip_id = t.id
             WHERE b.passenger_id = %s
               AND t.arrival_time < CLOCK_TIMESTAMP()) AS total
    """, (booking_id, passenger_id, passenger_id))
    return cursor.fetchone()

def get_route_tags(city_name: str, driver_id: int):
    """Returns up to 8 tags: driver's own first (by count DESC), padded with global (driver_id=0) ones."""
    cursor.execute("""
        SELECT tag FROM route_tags
        WHERE city_name = %s AND driver_id = %s
        ORDER BY count DESC
        LIMIT 6
    """, (city_name, driver_id))
    driver_tags = [row[0] for row in cursor.fetchall()]

    needed = 8 - len(driver_tags)
    cursor.execute("""
        SELECT tag FROM route_tags
        WHERE city_name = %s AND driver_id = 0
          AND tag != ALL(%s)
        ORDER BY count DESC
        LIMIT %s
    """, (city_name, driver_tags, needed))
    global_tags = [row[0] for row in cursor.fetchall()]

    return driver_tags + global_tags

def get_driver_recent_car_descriptions(driver_id: int, limit: int = 4):
    """Get up to `limit` recent car descriptions for a driver, sorted by updated_at DESC."""
    cursor.execute("""
        SELECT car_description FROM driver_info
        WHERE driver_id = %s
        ORDER BY updated_at DESC
        LIMIT %s
    """, (driver_id, limit))
    return [row[0] for row in cursor.fetchall()]

def save_or_update_driver_car_description(driver_id: int, car_description: str):
    """Insert car description if new, or update updated_at if exists."""
    cursor.execute("""
        INSERT INTO driver_info (driver_id, car_description, updated_at)
        VALUES (%s, %s, CLOCK_TIMESTAMP())
        ON CONFLICT (driver_id, car_description) DO UPDATE
        SET updated_at = CLOCK_TIMESTAMP()
    """, (driver_id, car_description))
    conn.commit()

def get_recent_phone_numbers(user_id: int, limit: int = 4):
    """Get up to `limit` recent phone numbers for a user, sorted by updated_at DESC."""
    cursor.execute("""
        SELECT phone_number FROM phones
        WHERE user_id = %s
        ORDER BY updated_at DESC
        LIMIT %s
    """, (user_id, limit))
    return [row[0] for row in cursor.fetchall()]

def save_or_update_phone_number(user_id: int, phone_number: str):
    """Insert phone number if new, or update updated_at if exists."""
    cursor.execute("""
        INSERT INTO phones (user_id, phone_number, updated_at)
        VALUES (%s, %s, CLOCK_TIMESTAMP())
        ON CONFLICT (user_id, phone_number) DO UPDATE
        SET updated_at = CLOCK_TIMESTAMP()
    """, (user_id, phone_number))
    conn.commit()

def save_route_description(user_id: int, city_name: str, is_departure: bool, description: str):
    cursor.execute("""
        INSERT INTO route_descriptions (user_id, city_name, is_departure, description)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, city_name, is_departure, description)
        DO UPDATE SET created_at = CLOCK_TIMESTAMP()
    """, (user_id, city_name, is_departure, description))
    conn.commit()

def get_route_descriptions(city_name: str, is_departure: bool, user_id: int):
    """Returns up to 4 descriptions: user-specific first, padded with global (user_id=0) if needed."""
    cursor.execute("""
        SELECT description FROM route_descriptions
        WHERE city_name = %s AND is_departure = %s AND user_id = %s
        ORDER BY created_at DESC
        LIMIT 4
    """, (city_name, is_departure, user_id))
    user_results = [row[0] for row in cursor.fetchall()]

    if len(user_results) >= 4:
        return user_results

    needed = 4 - len(user_results)
    cursor.execute("""
        SELECT description FROM route_descriptions
        WHERE city_name = %s AND is_departure = %s AND user_id = 0
          AND description != ALL(%s)
        ORDER BY created_at DESC
        LIMIT %s
    """, (city_name, is_departure, user_results, needed))
    global_results = [row[0] for row in cursor.fetchall()]

    return user_results + global_results

def get_trip_details(trip_id: int):
    cursor.execute("""
        SELECT from_city, to_city, departure_datetime, arrival_time, from_points, to_points, car_description
        FROM trips
        WHERE id = %s
    """, (trip_id,))
    return cursor.fetchone()

def get_trip_details_by_booking(booking_id: int):
    cursor.execute("""
        SELECT t.from_city, t.to_city, t.departure_datetime, b.notes, b.pickup_at, t.arrival_time, b.seats, t.from_points, t.to_points, t.car_description, b.from_city, b.to_city, t.price
        FROM bookings b
        JOIN trips t ON b.trip_id = t.id
        WHERE b.id = %s
    """, (booking_id,))
    return cursor.fetchone()

def get_passenger_phone_by_booking(booking_id: int):
    cursor.execute("SELECT passenger_phone FROM bookings WHERE id = %s", (booking_id,))
    row = cursor.fetchone()
    return row[0] if row else None

def get_driver_phone_by_booking(booking_id: int):
    cursor.execute("""
        SELECT t.driver_phone
        FROM bookings b
        JOIN trips t ON b.trip_id = t.id
        WHERE b.id = %s
    """, (booking_id,))
    row = cursor.fetchone()
    return row[0] if row else None

def set_booking_pickup_at(booking_id: int, pickup_at):
    cursor.execute("""
        UPDATE bookings SET pickup_at = %s WHERE id = %s
    """, (pickup_at, booking_id))
    conn.commit()

def search_trips_ids(from_city, to_city, time_from, time_to, extra_from_cities: list = None, extra_to_cities: list = None):
    all_from_cities = [from_city] + (extra_from_cities or [])
    all_to_cities = [to_city] + (extra_to_cities or [])
    cursor.execute("""
        SELECT t.id,
               t.seats::int - COALESCE((
                   SELECT SUM(b.seats) FROM bookings b
                   WHERE b.trip_id = t.id AND b.status IN ('pending', 'confirmed')
               ), 0) AS free_seats
        FROM trips t
        WHERE t.from_city = ANY(%s) AND t.to_city = ANY(%s)
          AND t.status = 'active'
          AND t.departure_datetime > CLOCK_TIMESTAMP()
          AND t.departure_datetime >= %s
          AND t.departure_datetime <= %s
        ORDER BY t.departure_datetime
    """, (all_from_cities, all_to_cities, time_from, time_to))
    return cursor.fetchall()

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
        SELECT t.id, t.driver_id, t.driver_phone, t.from_city, t.from_points, t.to_city, t.to_points, t.departure_datetime, t.price, t.seats,
               t.seats::int - (
                   SELECT COALESCE(SUM(b.seats), 0) FROM bookings b
                   WHERE b.trip_id = t.id AND b.status IN ('pending', 'confirmed')
               ) AS free_seats,
               t.arrival_time, t.car_description
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


def save_recent_search(passenger_id: int, from_city: str, to_city: str, time_str: str, search_for_day: str, trip_ids: list = None, seats_requested: int = 1):
    cursor.execute("""
        INSERT INTO recent_searches (passenger_id, from_city, to_city, time_str, search_for_day, searched_at, trip_ids, seats_requested)
        VALUES (%s, %s, %s, %s, %s, CLOCK_TIMESTAMP(), %s, %s)
    """, (passenger_id, from_city, to_city, time_str, search_for_day, trip_ids, seats_requested))
    conn.commit()

def get_recent_searches(passenger_id: int, limit: int = 20) -> list[tuple]:
    cursor.execute("""
        SELECT from_city, to_city, search_for_day, time_str, seats_requested
        FROM (
            SELECT DISTINCT ON (from_city, to_city, search_for_day, time_str)
                   from_city, to_city, search_for_day, time_str, seats_requested, searched_at
            FROM recent_searches
            WHERE passenger_id = %s
            ORDER BY from_city, to_city, search_for_day, time_str, searched_at DESC
        ) latest
        ORDER BY searched_at DESC
        LIMIT %s
    """, (passenger_id, limit))
    return cursor.fetchall()

def get_recent_booking_notes(passenger_id: int, from_city: str, limit: int = 3) -> list[str]:
    cursor.execute("""
        SELECT notes FROM bookings
        WHERE passenger_id = %s
          AND from_city = %s
          AND notes IS NOT NULL
          AND notes != ''
        GROUP BY notes
        ORDER BY MAX(booked_at) DESC
        LIMIT %s
    """, (passenger_id, from_city, limit))
    return [row[0] for row in cursor.fetchall()]

def get_recent_search_times(passenger_id: int, from_city: str, to_city: str, search_for_day: str, limit: int = 2):
    cursor.execute("""
        SELECT time_str FROM (
            SELECT time_str FROM (
                SELECT DISTINCT ON (time_str) time_str, searched_at FROM recent_searches
                WHERE passenger_id = %s AND from_city = %s AND to_city = %s AND search_for_day = %s AND time_str != 'show_all'
                ORDER BY time_str, searched_at DESC
            ) latest
            ORDER BY searched_at DESC
            LIMIT %s
        ) top
        ORDER BY time_str
    """, (passenger_id, from_city, to_city, search_for_day, limit))
    return [row[0] for row in cursor.fetchall()]

def save_trip_template(driver_id: int, data: dict) -> int | None:
    cursor.execute("""
        INSERT INTO trip_templates (driver_id, from_city, to_city, from_points, to_points, car_description, driver_phone, price, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CLOCK_TIMESTAMP())
        ON CONFLICT (driver_id, from_city, to_city, from_points, to_points)
        DO UPDATE SET price = EXCLUDED.price, car_description = EXCLUDED.car_description,
                      driver_phone = EXCLUDED.driver_phone, updated_at = CLOCK_TIMESTAMP(),
                      active = TRUE
        RETURNING id
    """, (driver_id, data.get("from_city"), data.get("to_city"), data.get("from_points"),
          data.get("to_points"), data.get("car_description"), data.get("driver_phone"), data.get("price")))
    row = cursor.fetchone()
    conn.commit()
    return row[0] if row else None

def upsert_template_time(template_id: int, time_str: str):
    cursor.execute("""
        INSERT INTO template_times (template_id, time, count, updated_at)
        VALUES (%s, %s, 1, CLOCK_TIMESTAMP())
        ON CONFLICT (template_id, time)
        DO UPDATE SET count = template_times.count + 1, updated_at = CLOCK_TIMESTAMP()
    """, (template_id, time_str))
    conn.commit()

def get_recent_template_times(template_id: int, limit: int = 3) -> list[str]:
    cursor.execute("""
        SELECT time FROM template_times
        WHERE template_id = %s
        ORDER BY updated_at DESC
        LIMIT %s
    """, (template_id, limit))
    return [row[0] for row in cursor.fetchall()]

def get_recent_times_by_cities(driver_id: int, from_city: str, to_city: str, limit: int = 10) -> list[str]:
    cursor.execute("""
        SELECT tt.time FROM template_times tt
        JOIN trip_templates t ON tt.template_id = t.id
        WHERE t.driver_id = %s AND t.from_city = %s AND t.to_city = %s
        ORDER BY tt.updated_at DESC
        LIMIT %s
    """, (driver_id, from_city, to_city, limit))
    return [row[0] for row in cursor.fetchall()]

def get_driver_templates(driver_id: int):
    cursor.execute("""
        SELECT id, from_city, to_city, from_points, to_points, car_description, driver_phone, price
        FROM trip_templates
        WHERE driver_id = %s AND active = TRUE
        ORDER BY updated_at DESC
    """, (driver_id,))
    return cursor.fetchall()

def get_template_by_id(template_id: int, driver_id: int):
    cursor.execute("""
        SELECT id, from_city, to_city, from_points, to_points, car_description, driver_phone, price
        FROM trip_templates
        WHERE id = %s AND driver_id = %s
    """, (template_id, driver_id))
    return cursor.fetchone()

def get_template_by_route(driver_id: int, from_city: str, to_city: str, from_points: str, to_points: str):
    cursor.execute("""
        SELECT id FROM trip_templates
        WHERE driver_id = %s AND from_city = %s AND to_city = %s
          AND COALESCE(from_points, '') = %s AND COALESCE(to_points, '') = %s
    """, (driver_id, from_city, to_city, from_points or "", to_points or ""))
    row = cursor.fetchone()
    return row[0] if row else None

def deactivate_template(template_id: int, driver_id: int):
    cursor.execute("""
        UPDATE trip_templates SET active = FALSE
        WHERE id = %s AND driver_id = %s
    """, (template_id, driver_id))
    conn.commit()

def save_event(from_user_id, to_user_id, text: str):
    cursor.execute("""
        INSERT INTO events (from_user_id, to_user_id, text)
        VALUES (%s, %s, %s)
    """, (from_user_id, to_user_id, text))
    conn.commit()

def upsert_user_details(user_id: int, user_name: str):
    cursor.execute("""
        INSERT INTO user_details (user_id, user_name)
        VALUES (%s, %s)
        ON CONFLICT (user_id, user_name) DO UPDATE SET updated_at = CLOCK_TIMESTAMP()
    """, (user_id, user_name))
    conn.commit()

def get_active_subscriptions(passenger_id: int) -> list[tuple]:
    cursor.execute("""
        SELECT id, from_city, to_city, search_for_day, seats_requested, from_time, to_time
        FROM search_subscriptions
        WHERE passenger_id = %s AND to_time > CLOCK_TIMESTAMP() AND is_active = TRUE
        ORDER BY from_time
    """, (passenger_id,))
    return cursor.fetchall()

def deactivate_subscription(subscription_id: int, passenger_id: int):
    cursor.execute("""
        UPDATE search_subscriptions SET is_active = FALSE WHERE id = %s AND passenger_id = %s
    """, (subscription_id, passenger_id))
    conn.commit()

def save_search_subscription(passenger_id: int, from_city: str, to_city: str, search_for_day: str, seats_requested: int = 1, from_time=None, to_time=None):
    cursor.execute("""
        INSERT INTO search_subscriptions (passenger_id, from_city, to_city, search_for_day, seats_requested, from_time, to_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (passenger_id, from_city, to_city, search_for_day)
        DO UPDATE SET seats_requested = EXCLUDED.seats_requested, from_time = EXCLUDED.from_time,
                      to_time = EXCLUDED.to_time, is_active = TRUE, created_at = CLOCK_TIMESTAMP(), notified_at = NULL
    """, (passenger_id, from_city, to_city, search_for_day, seats_requested, from_time, to_time))
    conn.commit()

def get_pending_subscriptions(from_city: str, to_city: str, dep_datetime) -> list[tuple]:
    cursor.execute("""
        SELECT passenger_id, seats_requested FROM search_subscriptions
        WHERE from_city = %s AND to_city = %s AND %s BETWEEN from_time AND to_time AND is_active = TRUE
    """, (from_city, to_city, dep_datetime))
    return cursor.fetchall()

def save_feedback(user_id: int, mode: str, feedback_text: str = None, file_id: str = None) -> int:
    cursor.execute("""
        INSERT INTO feedbacks (user_id, mode, feedback_text, file_id)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (user_id, mode, feedback_text, file_id))
    feedback_id = cursor.fetchone()[0]
    conn.commit()
    return feedback_id
