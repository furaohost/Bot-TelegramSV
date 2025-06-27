import os
import json
import requests
import telebot
from telebot import types
import base64
import traceback
import time as time_module
from datetime import datetime, timedelta, time
from threading import Thread

import pagamentos
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from werkzeug.security import check_password_hash, generate_password_hash

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import errors

# ────────────────────────────────────────────────────────────────────
# 1. CONFIGURAÇÃO INICIAL
# ────────────────────────────────────────────────────────────────────
API_TOKEN        = os.getenv("API_TOKEN")
BASE_URL         = os.getenv("BASE_URL")
DATABASE_URL     = os.getenv("DATABASE_URL")
FLASK_SECRET_KEY = os.getenv(
    "FLASK_SECRET_KEY",
    "uma_chave_padrao_muito_segura_e_longa_para_dev_local_1234567890",
)

print("DEBUG: API_TOKEN =", API_TOKEN)
print("DEBUG: BASE_URL  =", BASE_URL)
print("DEBUG: DATABASE_URL =", DATABASE_URL)

if not API_TOKEN:
    raise RuntimeError("A variável de ambiente API_TOKEN não está definida.")

# ────────────────────────────────────────────────────────────────────
# 2. FLASK & TELEBOT
# ────────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
app.secret_key = FLASK_SECRET_KEY
bot = telebot.TeleBot(API_TOKEN, threaded=False, parse_mode="Markdown")

# ────────────────────────────────────────────────────────────────────
# 3. FUNÇÕES DE BANCO
# ────────────────────────────────────────────────────────────────────

def get_db_connection():
    if not DATABASE_URL:
        print("AVISO: DATABASE_URL não definida, usando SQLite local.")
        import sqlite3
        db_path = os.path.join(os.getcwd(), "dashboard_local.db")
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    try:
        conn = psycopg2.connect(
            DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require"
        )
        conn.autocommit = False
        print("DEBUG DB: Conectado ao PostgreSQL.")
        return conn
    except Exception as e:
        print("ERRO DB: Falha ao conectar ao PostgreSQL:", e)
        raise

# ────────────────────────────────────────────────────────────────────
# 4. INIT_DB (com comunidades)
# ────────────────────────────────────────────────────────────────────

def init_db():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # USERS
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                );
                """
            )
            # PRODUTOS
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS produtos (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL,
                    preco NUMERIC(10,2) NOT NULL,
                    link TEXT NOT NULL
                );
                """
            )
            # VENDAS
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS vendas (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    produto_id INTEGER,
                    preco NUMERIC(10,2),
                    status TEXT,
                    data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    payment_id TEXT,
                    payer_name TEXT,
                    payer_email TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (produto_id) REFERENCES produtos(id)
                );
                """
            )
            # ADMIN
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS admin (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE,
                    password_hash TEXT
                );
                """
            )
            # CONFIG
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )
            # COMUNIDADES (Sprint‑1)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS comunidades (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL,
                    descricao TEXT,
                    chat_id BIGINT,
                    status TEXT DEFAULT 'ativa',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            # SCHEDULED_MESSAGES
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_messages (
                    id SERIAL PRIMARY KEY,
                    message_text TEXT NOT NULL,
                    target_chat_id BIGINT,
                    image_url TEXT,
                    schedule_time TIMESTAMP WITH TIME ZONE NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sent_at TIMESTAMP
                );
                """
            )
            # ADMIN padrão
            cur.execute("SELECT id FROM admin WHERE username = 'admin'")
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO admin (username,password_hash) VALUES (%s,%s)",
                    ("admin", generate_password_hash("admin123")),
                )
            # Mensagens padrão
            cur.execute(
                "INSERT INTO config (key,value) VALUES ('welcome_message_bot',%s) ON CONFLICT (key) DO NOTHING;",
                ("Olá, {first_name}! Bem‑vindo(a) ao bot!",),
            )
            cur.execute(
                "INSERT INTO config (key,value) VALUES ('welcome_message_community',%s) ON CONFLICT (key) DO NOTHING;",
                ("Bem‑vindo(a) à nossa comunidade, {first_name}!",),
            )
            conn.commit()
            print("DEBUG DB INIT: tabelas OK")
    except Exception as e:
        print("ERRO DB INIT:", e)
        traceback.print_exc()
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

# ────────────────────────────────────────────────────────────────────
# 5. HANDLERS / BLUEPRINTS
# ────────────────────────────────────────────────────────────────────
from bot.utils.keyboards import confirm_18_keyboard, menu_principal
from bot.handlers.chamadas import register_chamadas_handlers
from bot.handlers.comunidades import register_comunidades_handlers
from bot.handlers.ofertas import register_ofertas_handlers
from bot.handlers.conteudos import register_conteudos_handlers
from web.routes.comunidades import create_comunidades_blueprint

register_chamadas_handlers(bot, get_db_connection)
register_comunidades_handlers(bot, get_db_connection)  # Sprint‑1
register_ofertas_handlers(bot, get_db_connection)
register_conteudos_handlers(bot, get_db_connection)

app.register_blueprint(create_comunidades_blueprint(get_db_connection))

# ────────────────────────────────────────────────────────────────────
# 6. WORKER de mensagens agendadas (Completo)
# ────────────────────────────────────────────────────────────────────

def scheduled_message_worker():
    print("DEBUG WORKER: iniciado …")
    while True:
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM scheduled_messages WHERE status='pending' AND schedule_time<=NOW() ORDER BY schedule_time"
                )
                rows = cur.fetchall()
                for row in rows:
                    targets = []
                    if row["target_chat_id"]:
                        targets.append(row["target_chat_id"])
                    else:
                        cur.execute("SELECT id FROM users WHERE is_active=TRUE")
                        targets = [u["id"] for u in cur.fetchall()]
                    delivered = False
                    for chat_id in targets:
                        try:
                            if row["image_url"]:
                                bot.send_photo(chat_id, row["image_url"], caption=row["message_text"], parse_mode="Markdown")
                            else:
                                bot.send_message(chat_id, row["message_text"], parse_mode="Markdown")
                            delivered = True
                        except telebot.apihelper.ApiTelegramException as e:
                            if "blocked" in str(e).lower() or "not found" in str(e).lower():
                                cur.execute("UPDATE users SET is_active=FALSE WHERE id=%s", (chat_id,))
                        except Exception as e:
                            print("ERRO envio:", e)
                            traceback.print_exc()
                    status = "sent" if delivered else "failed"
                    cur.execute(
                        "UPDATE scheduled_messages SET status=%s, sent_at=NOW() WHERE id=%s",
                        (status, row["id"]),
                    )
                conn.commit()
        except Exception as e:
            print("ERRO WORKER:", e)
            traceback.print_exc()
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()
        time_module
