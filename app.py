import os
import json
import requests
import telebot
from telebot import types
import base64
import traceback
import time as time_module # Usado para time.sleep
from datetime import datetime, timedelta, time
from threading import Thread
import sqlite3 # Importado aqui para isinstance checks para SQLite

# Importações Flask e Werkzeug (para segurança e hashing de senha)
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from werkzeug.security import check_password_hash, generate_password_hash

# Importa as funções centralizadas de conexão e inicialização do banco de dados
# Certifique-se de que esses arquivos estão na pasta 'database/'
from database import get_db_connection
from database.db_init import init_db # Importa a função de inicialização do DB

# Importa o módulo de pagamentos do Mercado Pago
import pagamentos

# ATENÇÃO: As importações de funcionalidades da Sprint 1 (comunidades) foram removidas
# para garantir que apenas a base atual funcione conforme solicitado.
# Se for adicionar Sprint 1 novamente, as importe aqui:
# from bot.handlers.comunidades import register_comunidades_handlers
# from web.routes.comunidades import create_comunidades_blueprint


# ────────────────────────────────────────────────────────────────────
# 1. CONFIGURAÇÃO INICIAL
# ────────────────────────────────────────────────────────────────────
# Carrega variáveis de ambiente do arquivo .env (apenas para desenvolvimento local)
# Em produção (Render), as variáveis de ambiente são configuradas diretamente no serviço.
from dotenv import load_dotenv
load_dotenv() # Descomente para carregar .env localmente

API_TOKEN = os.getenv('API_TOKEN')
BASE_URL = os.getenv('BASE_URL') # Ex: https://seu-app.onrender.com
DATABASE_URL = os.getenv('DATABASE_URL') # String de conexão PostgreSQL (se aplicável)
FLASK_SECRET_KEY = os.getenv(
    'FLASK_SECRET_KEY', 
    'uma_chave_padrao_muito_segura_e_longa_para_dev_local_1234567890' # Altere em produção!
)
# Mercado Pago Access Token
MERCADOPAGO_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN')


print(f"DEBUG: API_TOKEN lido: {'***' if API_TOKEN else 'NULO'}")
print(f"DEBUG: BASE_URL lida: {BASE_URL}")
print(f"DEBUG: DATABASE_URL lida: {'***' if DATABASE_URL else 'NULO (usando SQLite)'}")
print(f"DEBUG: MERCADOPAGO_ACCESS_TOKEN lido: {'***' if MERCADOPAGO_ACCESS_TOKEN else 'NULO'}")


# Verifica se o API_TOKEN está configurado
if not API_TOKEN:
    raise RuntimeError("A variável de ambiente 'API_TOKEN' não está definida. O bot não pode funcionar.")


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
        print(f"ERRO DB: get_or_register_user falhou: {e}")
        if conn and not conn.closed:
            conn.rollback() # Reverte a transação em caso de erro
    finally:
        if conn:
            conn.close()


def enviar_produto_telegram(user_id, nome_produto, link_produto):
    """
    Envia uma mensagem de entrega de produto via Telegram.
    Args:
        user_id (int): O ID do usuário do Telegram.
        nome_produto (str): O nome do produto a ser entregue.
        link_produto (str): O link de acesso ao produto.
    """
    url = f"https://api.telegram.org/bot{API_TOKEN}/sendMessage"
    texto = (f"🎉 Pagamento Aprovado!\n\nObrigado por comprar *{nome_produto}*.\n\nAqui está o seu link de acesso:\n{link_produto}")
    payload = { 'chat_id': user_id, 'text': texto, 'parse_mode': 'Markdown' }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status() # Lança um HTTPError para respostas de erro (4xx ou 5xx)
        print(f"DEBUG: Mensagem de entrega para {user_id} enviada com sucesso.")
    except requests.exceptions.RequestException as e:
        print(f"ERRO: Falha ao enviar mensagem de entrega para {user_id}: {e}")
        traceback.print_exc()


# ────────────────────────────────────────────────────────────────────
# 4. INIT_DB (com comunidades)
# ────────────────────────────────────────────────────────────────────

def init_db():
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'error')
            return redirect(url_for('login'))

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
        print(f"ERRO REMOVE USUARIO: Falha ao remover usuário: {e}")
        traceback.print_exc()
        flash('Erro ao remover usuário.', 'error')
        if conn and not conn.closed:
            conn.rollback()
        return redirect(url_for('usuarios'))
    finally:
        if conn:
            conn.close()

@app.route('/pagamento/<status>')
def pagamento_retorno(status):
    """
    Rota para exibir o status de retorno de pagamento (pós-redirecionamento do Mercado Pago).
    """
    mensagem = "Status do Pagamento: "
    if status == 'sucesso':
        mensagem += "Aprovado com sucesso!"
    elif status == 'falha':
        mensagem += "Pagamento falhou."
    elif status == 'pendente':
        mensagem += "Pagamento pendente."
    # Retorna uma página HTML simples com a mensagem
    return f"""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Status do Pagamento</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>body {{ font-family: 'Inter', sans-serif; }}</style>
    </head>
    <body class="flex items-center justify-center min-h-screen bg-gray-100 p-4">
        <div class="bg-white p-8 rounded-lg shadow-md text-center">
            <h1 class="text-2xl font-bold text-gray-800 mb-4">{mensagem}</h1>
            <p class="text-gray-600">Você pode fechar esta janela e voltar para o Telegram.</p>
        </div>
    </body>
    </html>
    """, 200

@app.route('/config_messages', methods=['GET', 'POST'])
def config_messages():
    """
    Rota para configurar mensagens de boas-vindas do bot.
    Apenas acessível para usuários logados.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'error')
            return redirect(url_for('login'))

        with conn.cursor() as cur:
            is_sqlite = isinstance(conn, sqlite3.Connection)
            # Obtém a mensagem de boas-vindas atual do bot
            cur.execute("SELECT value FROM config WHERE key = %s" if not is_sqlite else "SELECT value FROM config WHERE key = ?", ('welcome_message_bot',))
            
            current_welcome_message_bot_row = cur.fetchone()
            current_welcome_message_bot = current_welcome_message_bot_row['value'] if current_welcome_message_bot_row else ''

            if request.method == 'POST':
                new_message = request.form['welcome_message_bot'].strip()
                if not new_message:
                    flash('A mensagem de boas-vindas não pode ser vazia.', 'error')
                    return render_template('config_messages.html', welcome_message_bot=current_welcome_message_bot)

                # Atualiza a mensagem no banco de dados
                cur.execute("UPDATE config SET value = %s WHERE key = %s" if not is_sqlite else "UPDATE config SET value = ? WHERE key = ?", (new_message, 'welcome_message_bot'))
                conn.commit()
                flash('Mensagem de boas-vindas do bot atualizada com sucesso!', 'success')
                return redirect(url_for('config_messages'))

            return render_template('config_messages.html', welcome_message_bot=current_welcome_message_bot)
    except Exception as e:
        print(f"ERRO CONFIG MENSAGENS: Falha ao configurar mensagens: {e}")
        traceback.print_exc()
        flash('Erro ao carregar ou atualizar mensagens.', 'error')
        if conn and not conn.closed:
            conn.rollback()
        return redirect(url_for('index'))
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
# Este worker será executado em uma thread separada ou como um processo à parte.
# Para Render, você pode precisar de um serviço worker separado no Procfile.
def scheduled_message_worker():
    print("DEBUG WORKER: iniciado …")
    while True:
        conn = None
        try:
            conn = get_db_connection()
            if conn is None:
                print("ERRO WORKER: Não foi possível obter conexão com o banco de dados. Tentando novamente em 30s...")
                time_module.sleep(30) # Espera antes de tentar novamente
                continue

            with conn.cursor() as cur:
                is_sqlite = isinstance(conn, sqlite3.Connection)
                # Adapta a query para SQLite/PostgreSQL
                # Busca mensagens pendentes cuja schedule_time já passou
                if is_sqlite:
                    cur.execute(
                        "SELECT * FROM scheduled_messages WHERE status='pending' AND schedule_time<=datetime('now') ORDER BY schedule_time"
                    )
                else: # PostgreSQL
                    cur.execute(
                        "SELECT * FROM scheduled_messages WHERE status='pending' AND schedule_time<=NOW() AT TIME ZONE 'UTC' ORDER BY schedule_time"
                    )
                rows = cur.fetchall()

                for row in rows:
                    targets = []
                    # Se um chat_id específico foi definido na mensagem agendada
                    if row["target_chat_id"]:
                        targets.append(row["target_chat_id"])
                    else:
                        # Caso contrário, envia para todos os usuários ativos
                        if is_sqlite:
                            cur.execute("SELECT id FROM users WHERE is_active=1")
                        else: # PostgreSQL
                            cur.execute("SELECT id FROM users WHERE is_active=TRUE")
                        targets = [u["id"] for u in cur.fetchall()]
                    delivered = False
                    for chat_id in targets:
                        try:
                            # Tenta enviar a mensagem/foto
                            if row["image_url"]:
                                # É crucial que o image_url seja um link acessível publicamente
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
                conn.rollback() # Reverte em caso de erro no worker
        finally:
            if conn:
                conn.close()
        time_module
