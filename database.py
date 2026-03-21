import psycopg2
from config import DATABASE_URL
from data.cities import CITIES

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
    day TEXT,
    time TEXT,
    price TEXT,
    seats TEXT
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
    booked_at TIMESTAMP DEFAULT NOW()
);
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS trip_search_lists (
    user_id BIGINT PRIMARY KEY,
    trip_ids INT[],          -- список знайдених поїздок
    current_index INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
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

def save_trip(driver_id, data):
    cursor.execute("""
        INSERT INTO trips (driver_id, from_city, from_points, to_city, to_points, day, time, price, seats)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        driver_id,
        data["from_city"],
        data["from_points"],
        data["to_city"],
        data["to_points"],
        data["day"],
        data["time"],
        data["price"],
        data["seats"]
    ))
    conn.commit()

def get_cities():
    cursor.execute("SELECT name FROM cities ORDER BY name")
    rows = cursor.fetchall()
    return [r[0] for r in rows]

def book_trip(trip_id: int, passenger_id: int) -> bool:

    cursor.execute("""
        INSERT INTO bookings (trip_id, passenger_id, status)
        VALUES (%s, %s, 'pending')
        RETURNING id
    """, (trip_id, passenger_id))
    conn.commit()
    booking_id = cursor.fetchone()[0]

    return True, booking_id

def update_booking_status(booking_id: int, status: str):
    cursor.execute("""
        UPDATE bookings
        SET status = %s
        WHERE id = %s
    """, (status, booking_id))
    conn.commit()

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
        ORDER BY counter DESC, name ASC
    """, (user_id,))
    popular = [r[0] for r in cursor.fetchall()]

    # Get all cities
    all_cities = get_cities()

    # Others: cities not in popular, sorted alphabetically
    others = sorted([c for c in all_cities if c not in popular])

    return popular, others

def get_driver_id(trip_id: int) -> int:
    cursor.execute("SELECT driver_id FROM trips WHERE id = %s", (trip_id,))
    return cursor.fetchone()[0]

def get_passenger_id(booking_id: int) -> int:
    cursor.execute("SELECT passenger_id FROM bookings WHERE id = %s", (booking_id,))
    return cursor.fetchone()[0]

def search_trips_ids(from_city, to_city):
    cursor.execute("""
        SELECT id
        FROM trips
        WHERE from_city = %s AND to_city = %s
        ORDER BY day, time
    """, (from_city, to_city))

    return [row[0] for row in cursor.fetchall()]

def create_trip_search_list(user_id: int, trips: list[int]):
    cursor.execute("""
        INSERT INTO trip_search_lists (user_id, trip_ids, current_index, created_at)
        VALUES (%s, %s, 0, NOW())
        ON CONFLICT (user_id) DO UPDATE
        SET trip_ids = EXCLUDED.trip_ids,
            current_index = 0,
            created_at = NOW()
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
        SELECT id, from_city, to_city, day, time, price, seats
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

