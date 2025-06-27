import os
import json
import requests
import telebot
from telebot import types
import base64
import pagamentos
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta, time
from threading import Thread
import time as time_module
import traceback

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import errors

# ────────────────────────────────────────────────────────────────────
# 1. CONFIGURAÇÃO INICIAL
# ────────────────────────────────────────────────────────────────────
API_TOKEN       = os.getenv('API_TOKEN')
BASE_URL        = os.getenv('BASE_URL')
DATABASE_URL    = os.getenv('DATABASE_URL')
FLASK_SECRET_KEY = os.getenv(
    'FLASK_SECRET_KEY',
    'uma_chave_padrao_muito_segura_e_longa_para_dev_local_1234567890'
)

print(f"DEBUG: API_TOKEN = {API_TOKEN}")
print(f"DEBUG: BASE_URL  = {BASE_URL}")
print(f"DEBUG: DATABASE_URL = {DATABASE_URL}")

if not API_TOKEN:
    raise RuntimeError('A variável de ambiente API_TOKEN não está definida.')

# ────────────────────────────────────────────────────────────────────
# 2. FLASK & TELEBOT
# ────────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder='web/templates', static_folder='web/static')
app.secret_key = FLASK_SECRET_KEY
bot = telebot.TeleBot(API_TOKEN, threaded=False, parse_mode='Markdown')

# ────────────────────────────────────────────────────────────────────
# 3. FUNÇÕES DE BANCO (SQLite fallback)
# ────────────────────────────────────────────────────────────────────

def get_db_connection():
    if not DATABASE_URL:
        print('AVISO: DATABASE_URL não definida, usando SQLite local.')
        import sqlite3
        db_path = os.path.join(os.getcwd(), 'dashboard_local.db')
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    try:
        conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=RealDictCursor,
            sslmode='require'
        )
        conn.autocommit = False
        print('DEBUG DB: Conectado ao PostgreSQL.')
        return conn
    except Exception as e:
        print('ERRO DB: Falha ao conectar ao PostgreSQL:', e)
        raise

# ────────────────────────────────────────────────────────────────────
# Função completa init_db (mesma que já existia)
# ────────────────────────────────────────────────────────────────────

def init_db():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            print("DEBUG DB INIT: Iniciando criação/verificação de tabelas…")
            # (INSIRA aqui a implementação completa da sua função init_db)
            pass  # ← substitua este pass pelo corpo original completo
    except Exception as e:
        print(f"ERRO DB: Falha ao inicializar o banco de dados: {e}")
        traceback.print_exc()
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

# ────────────────────────────────────────────────────────────────────
# 4. IMPORTS DE HANDLERS / BLUEPRINTS
# ────────────────────────────────────────────────────────────────────
from bot.utils.keyboards import confirm_18_keyboard, menu_principal
from bot.handlers.chamadas import register_chamadas_handlers
from bot.handlers.comunidades import register_comunidades_handlers
from bot.handlers.ofertas import register_ofertas_handlers
from bot.handlers.conteudos import register_conteudos_handlers
from web.routes.comunidades import create_comunidades_blueprint

# Registro
register_chamadas_handlers(bot, get_db_connection)
register_comunidades_handlers(bot, get_db_connection)  # Sprint‑1
register_ofertas_handlers(bot, get_db_connection)
register_conteudos_handlers(bot, get_db_connection)

app.register_blueprint(create_comunidades_blueprint(get_db_connection))

# ────────────────────────────────────────────────────────────────────
# ────────────────────────────────────────────────────────────────────
# 5. Worker de mensagens (adicione o corpo real depois)
# ────────────────────────────────────────────────────────────────────

def scheduled_message_worker():
    """Stub para evitar erro do Pylance.
    Substitua esta função pelo corpo ORIGINAL completo que havia no seu
    app.py – o laço while que lê a tabela scheduled_messages e envia.
    """
    pass

# -----------------------------------------------------------------------------------------------------------------------------------

# ────────────────────────────────────────────────────────────────────
# 6. BLOCO de inicialização quando executado no Render (gunicorn)
# ────────────────────────────────────────────────────────────────────
if __name__ != '__main__':
    try:
        init_db()
        pagamentos.init_mercadopago_sdk()

        # ─── WEBHOOK ───────────────────────────────────────────────
        if not BASE_URL:
            raise RuntimeError('BASE_URL não definida em Environment → Render')

        bot.remove_webhook()                       # limpa antigo
        bot.set_webhook(f"{BASE_URL}/{API_TOKEN}")
        print('Webhook do Telegram configurado com sucesso!')
        # ───────────────────────────────────────────────────────────

        # Inicia worker background
        worker_thread = Thread(target=scheduled_message_worker, daemon=True)
        worker_thread.start()
        print('DEBUG: Worker de mensagens agendadas iniciado.')

    except Exception as e:
        print('Erro ao configurar webhook ou iniciar worker:', e)
        traceback.print_exc()
        raise

