# database.py - saves users, rooms, chat messages and finished sessions in SQLite
import sqlite3
import time

DB_FILE = "focusroom.db"


def connect():
    return sqlite3.connect(DB_FILE)


def create_tables():
    db = connect()
    db.execute("CREATE TABLE IF NOT EXISTS users (name TEXT PRIMARY KEY)")
    db.execute("CREATE TABLE IF NOT EXISTS rooms (room_id TEXT PRIMARY KEY)")
    db.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, room_id TEXT, name TEXT, text TEXT, time TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY, room_id TEXT, minutes INTEGER, people TEXT, ended TEXT)")
    db.commit()
    db.close()


def add_user_and_room(name, room_id):
    db = connect()
    db.execute("INSERT OR IGNORE INTO users VALUES (?)", (name,))
    db.execute("INSERT OR IGNORE INTO rooms VALUES (?)", (room_id,))
    db.commit()
    db.close()


def save_message(room_id, name, text, t):
    db = connect()
    db.execute("INSERT INTO messages (room_id, name, text, time) VALUES (?, ?, ?, ?)", (room_id, name, text, t))
    db.commit()
    db.close()


def get_old_messages(room_id):
    # last 20 messages so new users can see what was said
    db = connect()
    rows = db.execute("SELECT name, text, time FROM messages WHERE room_id=? ORDER BY id DESC LIMIT 20", (room_id,)).fetchall()
    db.close()
    rows.reverse()
    return rows


def save_session(room_id, minutes, people):
    db = connect()
    db.execute("INSERT INTO sessions (room_id, minutes, people, ended) VALUES (?, ?, ?, ?)",
               (room_id, minutes, ", ".join(people), time.strftime("%Y-%m-%d %H:%M")))
    db.commit()
    db.close()


def get_sessions():
    db = connect()
    rows = db.execute("SELECT room_id, minutes, people, ended FROM sessions ORDER BY id DESC LIMIT 10").fetchall()
    db.close()
    return rows
