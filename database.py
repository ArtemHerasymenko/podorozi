import psycopg2
from config import DATABASE_URL

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