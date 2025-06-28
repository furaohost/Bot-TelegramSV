import sqlite3
import os
import psycopg2
from psycopg2 import Error

def init_db():
    # Determina se está usando SQLite ou PostgreSQL com base em DATABASE_URL
    database_url = os.getenv('DATABASE_URL')

    if database_url:
        # Inicialização para PostgreSQL
        print("Inicializando banco de dados (PostgreSQL)...")
        conn = None
        try:
            conn = psycopg2.connect(database_url)
            cur = conn.cursor()

            # Criação das tabelas para PostgreSQL
            # Use IF NOT EXISTS para evitar erros se as tabelas já existirem
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    is_active BOOLEAN DEFAULT TRUE,
                    data_registro TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS produtos (
                    id SERIAL PRIMARY KEY,
                    nome VARCHAR(255) NOT NULL,
                    preco NUMERIC(10, 2) NOT NULL,
                    link TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS vendas (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(id),
                    produto_id INTEGER NOT NULL REFERENCES produtos(id),
                    preco NUMERIC(10, 2) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    data_venda TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    payment_id VARCHAR(255),
                    payer_name VARCHAR(255),
                    payer_email VARCHAR(255)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_messages (
                    id SERIAL PRIMARY KEY,
                    message_text TEXT NOT NULL,
                    target_chat_id BIGINT, -- NULL para todos os usuários
                    image_url TEXT,
                    schedule_time TIMESTAMP WITH TIME ZONE NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    sent_at TIMESTAMP WITH TIME ZONE
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key VARCHAR(255) PRIMARY KEY,
                    value TEXT
                );
            """)

            conn.commit()
            print("Banco de dados PostgreSQL inicializado com sucesso.")

        except Error as e:
            print(f"ERRO DB INIT: Falha na inicialização do banco de dados PostgreSQL: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    else:
        # Inicialização para SQLite (para desenvolvimento local sem DATABASE_URL)
        print("Inicializando banco de dados (SQLite)...")
        conn = None
        try:
            # Conecta a um arquivo de banco de dados SQLite local
            conn = sqlite3.connect('database.db')
            cur = conn.cursor()

            # Criação das tabelas para SQLite
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY, -- Use INTEGER para auto-incremento em SQLite para PK
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    data_registro DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admin (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS produtos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    preco REAL NOT NULL,
                    link TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS vendas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    produto_id INTEGER NOT NULL,
                    preco REAL NOT NULL,
                    status TEXT NOT NULL,
                    data_venda DATETIME DEFAULT CURRENT_TIMESTAMP,
                    payment_id TEXT,
                    payer_name TEXT,
                    payer_email TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (produto_id) REFERENCES produtos(id)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_text TEXT NOT NULL,
                    target_chat_id INTEGER, -- NULL para todos os usuários
                    image_url TEXT,
                    schedule_time DATETIME NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    sent_at DATETIME
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            """)

            conn.commit()
            print("Banco de dados SQLite inicializado com sucesso.")

        except sqlite3.Error as e:
            print(f"ERRO DB INIT: Falha na inicialização do banco de dados SQLite: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()