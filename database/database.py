# database/database.py

import sqlite3

def get_db_connection():
    conn = sqlite3.connect("database/bot.db")
    conn.row_factory = sqlite3.Row
    return conn
