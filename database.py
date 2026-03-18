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
    passenger_id BIGINT NOT NULL,  -- Telegram user id
    booked_at TIMESTAMP DEFAULT NOW()
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

def search_trips(from_city, to_city):
    cursor.execute("""
        SELECT * FROM trips
        WHERE from_city ILIKE %s AND to_city ILIKE %s
    """, (f"%{from_city}%", f"%{to_city}%"))
    return cursor.fetchall()

def get_cities():
    cursor.execute("SELECT name FROM cities ORDER BY name")
    rows = cursor.fetchall()
    return [r[0] for r in rows]

def book_trip(trip_id: int) -> bool:

    cursor.execute("""
        INSERT INTO bookings (trip_id, passenger_id)
        VALUES (%s, %s)
    """, (trip_id, passenger_id))
    conn.commit()

    return True