# database/database.py
import os
import sqlite3
import psycopg2
from psycopg2 import Error
from psycopg2.extras import RealDictCursor # Importado para PostgreSQL

def get_db_connection():
    database_url = os.getenv('DATABASE_URL')

    if database_url:
        try:
            # Conecta ao PostgreSQL
            # Usando RealDictCursor para que as linhas se comportem como dicionários
            conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
            return conn
        except Error as e:
            print(f"Erro ao conectar ao banco de dados PostgreSQL: {e}")
            return None
    else:
        try:
            # Conecta ao SQLite
            conn = sqlite3.connect('database.db')
            conn.row_factory = sqlite3.Row # Isso faz com que as linhas se comportem como dicionários
            return conn
        except sqlite3.Error as e:
            print(f"Erro ao conectar ao banco de dados SQLite: {e}")
            return None