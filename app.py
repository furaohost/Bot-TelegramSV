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
# 1. CONFIGURAÇÃO INICIAL (Variáveis de Ambiente)
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
# 2. FLASK & TELEBOT (Inicialização dos objetos principais)
# ────────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
app.secret_key = FLASK_SECRET_KEY
bot = telebot.TeleBot(API_TOKEN, threaded=False, parse_mode="Markdown")


# ────────────────────────────────────────────────────────────────────
# 3. FUNÇÕES DE BANCO DE DADOS E UTILIDADE (DEFINIÇÕES - Todas devem vir antes do uso global)
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
        conn.autocommit = False # Permite controle manual de transações
        print("DEBUG DB: Conectado ao PostgreSQL.")
        return conn
    except Exception as e:
        print("ERRO DB: Falha ao conectar ao PostgreSQL:", e)
        raise

def init_db():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            print("DEBUG DB INIT: Iniciando criação/verificação de tabelas...")

            # USERS
            print("DEBUG DB INIT: Criando tabela 'users'...")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            # Adicionar is_active se a coluna não existir
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name='users' AND column_name='is_active';
            """)
            if not cur.fetchone():
                try:
                    cur.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE;")
                    print("DEBUG DB INIT: Coluna 'is_active' adicionada à tabela 'users'.")
                except errors.DuplicateColumn:
                    print("DEBUG DB INIT: Coluna 'is_active' já existe em 'users'.")
                except Exception as e:
                    print(f"ERRO DB INIT: Falha inesperada ao adicionar coluna 'is_active' em users: {e}")
                    traceback.print_exc()
                    raise
            else:
                print("DEBUG DB INIT: Coluna 'is_active' já existe em 'users'.")
            print("DEBUG DB INIT: Tabela 'users' criada ou já existe.")


            # PRODUTOS
            print("DEBUG DB INIT: Criando tabela 'produtos'...")
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
            print("DEBUG DB INIT: Tabela 'produtos' criada ou já existe.")


            # VENDAS
            print("DEBUG DB INIT: Criando tabela 'vendas'...")
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
            print("DEBUG DB INIT: Tabela 'vendas' criada ou já existe.")


            # ADMIN
            print("DEBUG DB INIT: Criando tabela 'admin'...")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS admin (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE,
                    password_hash TEXT
                );
                """
            )
            print("DEBUG DB INIT: Tabela 'admin' criada ou já existe.")


            # CONFIG
            print("DEBUG DB INIT: Criando tabela 'config'...")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )
            print("DEBUG DB INIT: Tabela 'config' criada ou já existe.")


            # COMUNIDADES (Corrigida para refletir bot/handlers/comunidades.py)
            print("DEBUG DB INIT: Criando tabela 'comunidades'...")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS comunidades (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL UNIQUE,
                    link TEXT,                      -- Usado em comunidades.py para INSERT
                    categoria TEXT,                 -- Usado em comunidades.py para INSERT
                    criada_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Usado em comunidades.py para INSERT
                    chat_id BIGINT UNIQUE,          -- Para links com Telegram/grupos
                    status TEXT DEFAULT 'ativa' -- Para controle de status
                );
                """
            )
            # Lógica para adicionar colunas a 'comunidades' se não existirem
            for col_name, col_type, default_val in [
                ("link", "TEXT", None),
                ("categoria", "TEXT", None),
                ("criada_em", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP", None),
                ("chat_id", "BIGINT UNIQUE", None),
                ("status", "TEXT DEFAULT 'ativa'", "'ativa'")
            ]:
                cur.execute(f"""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name='comunidades' AND column_name='{col_name}';
                """)
                if not cur.fetchone():
                    try:
                        alter_sql = f"ALTER TABLE comunidades ADD COLUMN {col_name} {col_type}"
                        if default_val is not None and "UNIQUE" not in col_type:
                            alter_sql += f" DEFAULT {default_val}"
                        cur.execute(alter_sql + ";")

                        if "UNIQUE" in col_type:
                            try:
                                cur.execute(f"ALTER TABLE comunidades ADD CONSTRAINT unique_{col_name} UNIQUE ({col_name});")
                                print(f"DEBUG DB INIT: Restrição UNIQUE adicionada para a coluna '{col_name}'.")
                            except errors.DuplicateObject:
                                print(f"DEBUG DB INIT: Restrição UNIQUE para '{col_name}' já existe.")
                            except Exception as unique_e:
                                print(f"ERRO DB INIT: Falha ao adicionar restrição UNIQUE para '{col_name}': {unique_e}")
                                traceback.print_exc()
                                raise

                        print(f"DEBUG DB INIT: Coluna '{col_name}' adicionada à tabela 'comunidades'.")
                    except errors.DuplicateColumn:
                        print(f"DEBUG DB INIT: Coluna '{col_name}' já existe em 'comunidades' (capturado no ALTER).")
                    except Exception as e:
                        print(f"ERRO DB INIT: Falha inesperada ao adicionar coluna '{col_name}' em comunidades: {e}")
                        traceback.print_exc()
                        raise
                else:
                    print(f"DEBUG DB INIT: Coluna '{col_name}' já existe em 'comunidades'.")
            print("DEBUG DB INIT: Tabela 'comunidades' criada ou já existe.")


            # SCHEDULED_MESSAGES
            print("DEBUG DB INIT: Criando tabela 'scheduled_messages'...")
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
            # Adicionar a coluna image_url se ela não existir
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name='scheduled_messages' AND column_name='image_url';
            """)
            if not cur.fetchone():
                try:
                    cur.execute("ALTER TABLE scheduled_messages ADD COLUMN image_url TEXT;")
                    print("DEBUG DB INIT: Coluna 'image_url' adicionada à tabela 'scheduled_messages'.")
                except errors.DuplicateColumn:
                    print("DEBUG DB INIT: Coluna 'image_url' já existe em 'scheduled_messages' (capturado no ALTER).")
                except Exception as e:
                    print(f"ERRO DB INIT: Falha inesperada ao adicionar coluna 'image_url': {e}")
                    traceback.print_exc()
                    raise
            else:
                print("DEBUG DB INIT: Coluna 'image_url' já existe em 'scheduled_messages'.")
            print("DEBUG DB INIT: Tabela 'scheduled_messages' criada.")

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
                ("Olá, {first_name}! Bem-vindo(a) ao bot!",),
            )
            cur.execute(
                "INSERT INTO config (key,value) VALUES ('welcome_message_community',%s) ON CONFLICT (key) DO NOTHING;",
                ("Bem-vindo(a) à nossa comunidade, {first_name}!",),
            )
            conn.commit()
            print("DEBUG DB INIT: Tabelas e dados iniciais OK.")
    except Exception as e:
        print("ERRO DB INIT:", e)
        traceback.print_exc()
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def get_or_register_user(user: types.User):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (user.id,))
            db_user = cur.fetchone()
            if db_user is None:
                data_registro = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cur.execute("INSERT INTO users (id, username, first_name, last_name, data_registro, is_active) VALUES (%s, %s, %s, %s, %s, %s)",
                             (user.id, user.username, user.first_name, user.last_name, data_registro, True))
                conn.commit()
            else:
                if not db_user['is_active']:
                    cur.execute("UPDATE users SET is_active = TRUE WHERE id = %s", (user.id,))
                    conn.commit()
                    print(f"DEBUG DB: Usuário {user.id} reativado.")
    except Exception as e:
        print(f"ERRO DB: get_or_register_user falhou: {e}")
        traceback.print_exc()
        if conn and not conn.closed: conn.rollback()
    finally:
        if conn: conn.close()

def enviar_produto_telegram(user_id, nome_produto, link_produto):
    url = f"https://api.telegram.org/bot{API_TOKEN}/sendMessage"
    texto = (f"🎉 Pagamento Aprovado!\n\nObrigado por comprar *{nome_produto}*.\n\nAqui está o seu link de acesso:\n{link_produto}")
    payload = { 'chat_id': user_id, 'text': texto, 'parse_mode': 'Markdown' }
    try:
        requests.post(url, json=payload)
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar mensagem de entrega: {e}")
        traceback.print_exc()

def mostrar_produtos(chat_id):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM produtos')
            produtos = cur.fetchall()
            if not produtos:
                bot.send_message(chat_id, "Nenhum produto disponível.")
                return
            for produto in produtos:
                markup = types.InlineKeyboardMarkup()
                btn_comprar = types.InlineKeyboardButton(f"Comprar por R${produto['preco']:.2f}", callback_data=f"comprar_{produto['id']}")
                markup.add(btn_comprar)
                bot.send_message(chat_id, f"🛍 *{produto['nome']}*\n\nPreço: R${produto['preco']:.2f}", parse_mode='Markdown', reply_markup=markup)
    except Exception as e:
        print(f"ERRO MOSTRAR PRODUTOS: Falha ao mostrar produtos: {e}")
        traceback.print_exc()
        bot.send_message(chat_id, "Ocorreu um erro ao carregar os produtos.")
    finally:
        if conn: conn.close()

def generar_cobranca(call: types.CallbackQuery, produto_id: int):
    user_id, chat_id = call.from_user.id, call.message.chat.id
    conn = None
    venda_id = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM produtos WHERE id = %s', (produto_id,))
            produto = cur.fetchone()

            if not produto:
                bot.send_message(chat_id, "Produto não encontrado.")
                return

            data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cur.execute("INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                         (user_id, produto['id'], produto['preco'], 'pendente', data_venda))
            venda_id = cur.fetchone()[0]
            conn.commit()

            pagamento = pagamentos.criar_pagamento_pix(produto=produto, user=call.from_user, venda_id=venda_id)

            if pagamento and 'point_of_interaction' in pagamento:
                qr_code_base64 = pagamento['point_of_interaction']['transaction_data']['qr_code_base64']
                qr_code_data = pagamento['point_of_interaction']['transaction_data']['qr_code']
                qr_code_image = base64.b64decode(qr_code_base64)

                caption_text = (
                    f"✅ PIX gerado para *{produto['nome']}*!\n\n"
                    "Escaneie o QR Code acima ou copie o código completo na próxima mensagem."
                )
                bot.send_photo(chat_id, qr_code_image, caption=caption_text, parse_mode='Markdown')

                bot.send_message(chat_id, qr_code_data)

                bot.send_message(chat_id, "Você receberá o produto aqui assim que o pagamento for confirmado.")
            else:
                bot.send_message(chat_id, "Ocorreu um erro ao gerar o PIX. Tente novamente.")
                print(f"[ERRO] Falha ao gerar PIX. Resposta do MP: {pagamento}")
    except Exception as e:
        print(f"ERRO GERAR COBRANCA: Falha ao gerar cobrança/PIX: {e}")
        traceback.print_exc()
        bot.send_message(chat_id, "Ocorreu um erro interno ao gerar sua cobrança. Tente novamente.")
        if conn and not conn.closed: conn.rollback()
    finally:
        if conn: conn.close()


# ────────────────────────────────────────────────────────────────────
# 7. WORKER de mensagens agendadas (Corrigido)
# ────────────────────────────────────────────────────────────────────

def scheduled_message_worker():
    print("DEBUG WORKER: Iniciado...")
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
                    
                    delivered_to_any = False
                    for chat_id in targets:
                        try:
                            if row["image_url"]:
                                bot.send_photo(chat_id, row["image_url"], caption=row["message_text"], parse_mode="Markdown")
                            else:
                                bot.send_message(chat_id, row["message_text"], parse_mode="Markdown")
                            delivered_to_any = True
                        except telebot.apihelper.ApiTelegramException as e:
                            print(f"ERRO envio Telegram para {chat_id}:", e)
                            if "blocked" in str(e).lower() or "not found" in str(e).lower() or "deactivated" in str(e).lower():
                                print(f"AVISO: Usuário {chat_id} bloqueou/não encontrado. Inativando...")
                                temp_conn = None
                                try:
                                    temp_conn = get_db_connection()
                                    with temp_conn.cursor() as temp_cur:
                                        temp_cur.execute("UPDATE users SET is_active=FALSE WHERE id=%s", (chat_id,))
                                        temp_conn.commit()
                                except Exception as db_e:
                                    print(f"ERRO ao inativar usuário {chat_id}:", db_e)
                                    if temp_conn: temp_conn.rollback()
                                finally:
                                    if temp_conn: temp_conn.close()
                        except Exception as e:
                            print("ERRO envio inesperado:", e)
                            traceback.print_exc()

                    status = "sent" if delivered_to_any else "failed"
                    cur.execute(
                        "UPDATE scheduled_messages SET status=%s, sent_at=NOW() WHERE id=%s",
                        (status, row["id"]),
                    )
                conn.commit()
        except Exception as e:
            print("ERRO WORKER PRINCIPAL:", e)
            traceback.print_exc()
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()
        time_module.sleep(60) # CORRIGIDO: Agora tem .sleep()


# ────────────────────────────────────────────────────────────────────
# 8. ROTAS FLASK
# ────────────────────────────────────────────────────────────────────

# Rota de health check para verificar se a aplicação está viva
@app.route('/health')
def health_check():
    """Rota simples para verificar o status da aplicação."""
    print("DEBUG HEALTH: Requisição para /health.")
    return "OK", 200

# Webhook do Telegram
@app.route(f"/{API_TOKEN}", methods=['POST'])
def telegram_webhook():
    print(f"DEBUG WEBHOOK TELEGRAM: Recebida requisição para /{API_TOKEN}. Method: {request.method}")
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        try:
            update = types.Update.de_json(json_str)
            bot.process_new_updates([update])
            print("DEBUG WEBHOOK TELEGRAM: Update processado com sucesso.")
            return '!', 200
        except Exception as e:
            print(f"ERRO WEBHOOK TELEGRAM: Falha ao processar update: {e}")
            traceback.print_exc()
            return "Erro ao processar update", 500
    else:
        print("AVISO WEBHOOK TELEGRAM: Content-Type não suportado:", request.headers.get('content-type'))
        return "Unsupported Media Type", 415

# Webhook do Mercado Pago
@app.route('/webhook/mercado-pago', methods=['GET', 'POST'])
def webhook_mercado_pago():
    print(f"DEBUG WEBHOOK MP: Recebida requisição para /webhook/mercado-pago. Method: {request.method}")

    if request.method == 'GET':
        print("DEBUG WEBHOOK MP: Requisição GET de teste do Mercado Pago recebida. Respondendo 200 OK.")
        return jsonify({'status': 'ok_test_webhook'}), 200

    notification = request.json
    print(f"DEBUG WEBHOOK MP: Corpo da notificação POST: {notification}")

    if notification and notification.get('type') == 'payment':
        print(f"DEBUG WEBHOOK MP: Notificação de pagamento detectada. ID: {notification.get('data', {}).get('id')}")
        payment_id = notification['data']['id']
        payment_info = pagamentos.verificar_status_pagamento(payment_id)

        print(f"DEBUG WEBHOOK MP: Status do pagamento verificado: {payment_info.get('status') if payment_info else 'N/A'}")

        if payment_info and payment_info['status'] == 'approved':
            conn = None
            try:
                conn = get_db_connection()
                with conn.cursor() as cur:
                    venda_id = payment_info.get('external_reference')
                    print(f"DEBUG WEBHOOK MP: Pagamento aprovado. Venda ID (external_reference): {venda_id}")

                    if not venda_id:
                        print("DEBUG WEBHOOK MP: external_reference não encontrado na notificação. Ignorando.")
                        return jsonify({'status': 'ignored_no_external_ref'}), 200

                    cur.execute('SELECT * FROM vendas WHERE id = %s AND status = %s', (venda_id, 'pendente'))
                    venda = cur.fetchone()

                    if venda:
                        print(f"DEBUG WEBHOOK MP: Venda {venda_id} encontrada no DB com status 'pendente'.")
                        data_venda_dt = venda['data_venda'] if isinstance(venda['data_venda'], datetime) else datetime.strptime(str(venda['data_venda']), '%Y-%m-%d %H:%M:%S.%f')
                        
                        if datetime.now() > data_venda_dt + timedelta(hours=1):
                            print(f"DEBUG WEBHOOK MP: Pagamento recebido para venda expirada (ID: {venda_id}). Ignorando entrega.")
                            cur.execute('UPDATE vendas SET status = %s WHERE id = %s', ('expirado', venda_id))
                            conn.commit()
                            return jsonify({'status': 'expired_and_ignored'}), 200

                        payer_info = payment_info.get('payer', {})
                        payer_name = f"{payer_info.get('first_name', '')} {payer_info.get('last_name', '')}".strip()
                        payer_email = payer_info.get('email')
                        cur.execute('UPDATE vendas SET status = %s, payment_id = %s, payer_name = %s, payer_email = %s WHERE id = %s',
                                     ('aprovado', payment_id, payer_name, payer_email, venda_id))
                        conn.commit()
                        cur.execute('SELECT * FROM produtos WHERE id = %s', (venda['produto_id'],))
                        produto = cur.fetchone()
                        if produto:
                            print(f"DEBUG WEBHOOK MP: Enviando produto {produto['nome']} para user {venda['user_id']}.")
                            enviar_produto_telegram(venda['user_id'], produto['nome'], produto['link'])
                        print(f"DEBUG WEBHOOK MP: Venda {venda_id} aprovada e entregue com sucesso.")
                        return jsonify({'status': 'success'}), 200
                    else:
                        print(f"DEBUG WEBHOOK MP: Venda {venda_id} já processada ou não encontrada no DB como 'pendente'.")
                        return jsonify({'status': 'already_processed_or_not_pending'}), 200
            except Exception as e:
                print(f"ERRO WEBHOOK MP: Erro no processamento da notificação de pagamento: {e}")
                traceback.print_exc()
                if conn and not conn.closed: conn.rollback()
                return jsonify({'status': 'error_processing_webhook'}), 500
            finally:
                if conn: conn.close()
        else:
            print(f"DEBUG WEBHOOK MP: Pagamento {payment_id} não aprovado ou info inválida. Status: {payment_info.get('status') if payment_info else 'N/A'}")
            return jsonify({'status': 'payment_not_approved'}), 200

    print("DEBUG WEBHOOK MP: Notificação ignorada (não é tipo 'payment' ou JSON inválido).")
    return jsonify({'status': 'ignored_general'}), 200


@app.route('/login', methods=['GET', 'POST'])
def login():
    print(f"DEBUG LOGIN: Requisição para /login. Method: {request.method}")
    print(f"DEBUG LOGIN: session.get('logged_in'): {session.get('logged_in')}")

    if session.get('logged_in'):
        print("DEBUG LOGIN: Usuário já logado. Redirecionando para index.")
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM admin WHERE username = %s', (username,))
                admin_user = cur.fetchone()

                if not admin_user:
                    print(f"DEBUG LOGIN: Usuário '{username}' NÃO ENCONTRADO no banco de dados.")
                    flash('Usuário ou senha inválidos.', 'danger')
                    return render_template('login.html')

                print(f"DEBUG LOGIN: Usuário '{username}' encontrado. Verificando a senha.")
                print(f"DEBUG LOGIN: Hash no DB: {admin_user['password_hash']}")
                
                is_password_correct = check_password_hash(admin_user['password_hash'], password)
                
                if is_password_correct:
                    session['logged_in'] = True
                    session['username'] = admin_user['username']
                    print(f"DEBUG LOGIN: Login BEM-SUCEDIDO para {session['username']}.")
                    return redirect(url_for('index'))
                else:
                    print("DEBUG LOGIN: Senha INCORRETA.")
                    flash('Usuário ou senha inválidos.', 'danger')
                    
        except Exception as e:
            print(f"ERRO LOGIN: Falha no processo de login: {e}")
            traceback.print_exc()
            flash('Erro no servidor ao tentar login.', 'danger')
            if conn and not conn.closed: conn.rollback()
        finally:
            if conn: conn.close()

    print("DEBUG LOGIN: Renderizando login.html.")
    return render_template('login.html')

# ==============================================================================
# !! ROTA TEMPORÁRIA PARA RESET DE SENHA !!
# !! REMOVA ESTA ROTA APÓS O USO !!
# ==============================================================================
@app.route('/reset-admin-password-now/muito-secreto-12345')
def reset_admin_password_route():
    USERNAME_TO_RESET = 'admin'
    NEW_PASSWORD = 'admin123' 

    print(f"DEBUG RESET: Rota de reset de senha acessada para o usuário '{USERNAME_TO_RESET}'.")
    
    hashed_password = generate_password_hash(NEW_PASSWORD)
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE admin SET password_hash = %s WHERE username = %s", (hashed_password, USERNAME_TO_RESET))
            
            if cur.rowcount == 0:
                print(f"DEBUG RESET: Usuário '{USERNAME_TO_RESET}' não encontrado para atualizar. Tentando criar...")
                cur.execute("INSERT INTO admin (username, password_hash) VALUES (%s, %s)", (USERNAME_TO_RESET, hashed_password))
                conn.commit()
                message = f"Usuário '{USERNAME_TO_RESET}' não encontrado. Um novo usuário foi criado com a senha definida. Por favor, remova esta rota agora."
                print(f"[SUCESSO RESET] {message}")
                return f"<h1>Sucesso</h1><p>{message}</p>", 200

            conn.commit()
            message = f"A senha para o usuário '{USERNAME_TO_RESET}' foi resetada com sucesso. Por favor, remova esta rota de 'app.py' IMEDIATELY."
            print(f"[SUCESSO RESET] {message}")
            return f"<h1>Sucesso</h1><p>{message}</p>", 200

    except Exception as e:
        error_message = f"Ocorreu um erro ao resetar a senha: {e}"
        print(f"ERRO RESET: {error_message}")
        traceback.print_exc()
        if conn:
            conn.rollback()
        return f"<h1>Erro</h1><p>{error_message}</p>", 500
    finally:
        if conn:
            conn.close()
# ==============================================================================
# !! FIM DA ROTA TEMPORÁRIA !!
# ==============================================================================


@app.route('/logout')
def logout():
    print(f"DEBUG LOGOUT: Desconectando usuário {session.get('username')}.")
    session.clear()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

@app.route('/')
def index():
    print(f"DEBUG INDEX: Requisição para /. session.get('logged_in'): {session.get('logged_in')}")

    if not session.get('logged_in'):
        print("DEBUG INDEX: Usuário não logado. Redirecionando para login.")
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(id) FROM users WHERE is_active = TRUE')
            total_usuarios_row = cur.fetchone()
            print(f"DEBUG INDEX: Resultado fetchone COUNT(users): {total_usuarios_row}")
            total_usuarios = total_usuarios_row['count'] if total_usuarios_row and 'count' in total_usuarios_row and total_usuarios_row['count'] is not None else 0

            cur.execute('SELECT COUNT(id) FROM produtos')
            total_produtos_row = cur.fetchone()
            print(f"DEBUG INDEX: Resultado fetchone COUNT(produtos): {total_produtos_row}")
            total_produtos = total_produtos_row['count'] if total_produtos_row and 'count' in total_produtos_row and total_produtos_row['count'] is not None else 0

            cur.execute("SELECT COUNT(id) AS count, SUM(preco) AS sum FROM vendas WHERE status = %s", ('aprovado',))
            vendas_data_row = cur.fetchone()
            print(f"DEBUG INDEX: Resultado fetchone COUNT/SUM(vendas): {vendas_data_row}")
            total_vendas_aprovadas = vendas_data_row['count'] if vendas_data_row and 'count' in vendas_data_row and vendas_data_row['count'] is not None else 0
            receita_total = vendas_data_row['sum'] if vendas_data_row and 'sum' in vendas_data_row and vendas_data_row['sum'] is not None else 0.0
            print(f"DEBUG INDEX: total_vendas_aprovadas: {total_vendas_aprovadas}, receita_total: {receita_total}")

            cur.execute("SELECT v.id, u.username, u.first_name, p.nome, v.preco, v.data_venda, p.id as produto_id, CASE WHEN v.status = 'aprovado' THEN 'aprovado' WHEN v.status = 'pendente' AND EXTRACT(EPOCH FROM (NOW() - v.data_venda)) > 3600 THEN 'expirado' ELSE v.status END AS status FROM vendas v JOIN users u ON v.user_id = u.id JOIN produtos p ON v.produto_id = p.id ORDER BY v.id DESC LIMIT 5")
            vendas_recentes = cur.fetchall()

            chart_labels, chart_data = [], []
            today = datetime.now()
            for i in range(6, -1, -1):
                day = today - timedelta(days=i)
                start_of_day, end_of_day = datetime.combine(day.date(), time.min), datetime.combine(day.date(), time.max)
                chart_labels.append(day.strftime('%d/%m'))
                cur.execute("SELECT SUM(preco) AS sum FROM vendas WHERE status = %s AND data_venda BETWEEN %s AND %s", ('aprovado', start_of_day, end_of_day))
                daily_revenue_row = cur.fetchone()
                daily_revenue = daily_revenue_row['sum'] if daily_revenue_row and 'sum' in daily_revenue_row and daily_revenue_row['sum'] is not None else 0
                chart_data.append(daily_revenue)

            print("DEBUG INDEX: Renderizando index.html.")
            return render_template('index.html', total_vendas=total_vendas_aprovadas, total_usuarios=total_usuarios, total_produtos=total_produtos, receita_total=receita_total, vendas_recentes=vendas_recentes, chart_labels=json.dumps(chart_labels), chart_data=json.dumps(chart_data))
    except Exception as e:
        print(f"ERRO INDEX: Falha ao renderizar o dashboard: {e}")
        traceback.print_exc()
        flash('Erro ao carregar o dashboard.', 'danger')
        return redirect(url_for('login'))
    finally:
        if conn: conn.close()

# ----------------------------------------------------------------------
# ROTAS PARA GERENCIAMENTO DE PRODUTOS E VENDAS
# ----------------------------------------------------------------------

@app.route('/produtos')
def produtos():
    """
    Rota para exibir a lista de produtos na interface web do dashboard.
    Requer que o usuário esteja logado.
    Busca todos os produtos do banco de dados e os renderiza no template produtos.html.
    """
    print("DEBUG PRODUTOS: Requisição para /produtos.")

    # Verifica se o usuário está logado antes de permitir o acesso
    if not session.get('logged_in'):
        print("DEBUG PRODUTOS: Usuário não logado. Redirecionando para login.")
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Busca todos os produtos do banco de dados
            cur.execute('SELECT * FROM produtos ORDER BY nome ASC')
            produtos_lista = cur.fetchall()
            print(f"DEBUG PRODUTOS: {len(produtos_lista)} produtos encontrados.")

        # Renderiza o template 'produtos.html', passando a lista de produtos
        return render_template('produtos.html', produtos=produtos_lista)

    except Exception as e:
        print(f"ERRO PRODUTOS: Falha ao carregar produtos para o dashboard: {e}")
        traceback.print_exc()
        flash('Erro ao carregar os produtos.', 'danger')
        # Em caso de erro, redireciona para o dashboard ou login
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()

@app.route('/adicionar_produto', methods=['GET', 'POST'])
def adicionar_produto():
    """
    Rota para adicionar um novo produto.
    Permite exibir um formulário (GET) e processar o envio do formulário (POST).
    Requer que o usuário esteja logado.
    """
    print(f"DEBUG ADICIONAR_PRODUTO: Requisição para /adicionar_produto. Method: {request.method}")

    if not session.get('logged_in'):
        print("DEBUG ADICIONAR_PRODUTO: Usuário não logado. Redirecionando para login.")
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        nome = request.form.get('nome')
        preco = request.form.get('preco')
        link = request.form.get('link')

        if not nome or not preco or not link:
            flash('Todos os campos são obrigatórios!', 'danger')
            return render_template('adicionar_produto.html')

        try:
            preco = float(preco)
            if preco <= 0:
                flash('Preço deve ser um valor positivo.', 'danger')
                return render_template('adicionar_produto.html')
        except ValueError:
            flash('Preço inválido. Use um número.', 'danger')
            return render_template('adicionar_produto.html')

        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO produtos (nome, preco, link) VALUES (%s, %s, %s)",
                    (nome, preco, link)
                )
                conn.commit()
            print(f"DEBUG ADICIONAR_PRODUTO: Produto '{nome}' adicionado com sucesso.")
            flash('Produto adicionado com sucesso!', 'success')
            return redirect(url_for('produtos')) # Redireciona para a lista de produtos
        except Exception as e:
            print(f"ERRO ADICIONAR_PRODUTO: Falha ao adicionar produto: {e}")
            traceback.print_exc()
            flash('Erro ao adicionar produto.', 'danger')
            if conn and not conn.closed: conn.rollback()
        finally:
            if conn: conn.close()
    
    # Se for um GET request, apenas renderiza o formulário
    return render_template('adicionar_produto.html')


@app.route('/editar_produto/<int:produto_id>', methods=['GET', 'POST'])
def editar_produto(produto_id):
    """
    Rota para editar um produto existente.
    Exibe um formulário pré-preenchido (GET) e processa as atualizações (POST).
    Requer que o usuário esteja logado.
    """
    print(f"DEBUG EDITAR_PRODUTO: Requisição para /editar_produto/{produto_id}. Method: {request.method}")

    if not session.get('logged_in'):
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM produtos WHERE id = %s', (produto_id,))
            produto = cur.fetchone()

            if not produto:
                flash('Produto não encontrado.', 'danger')
                return redirect(url_for('produtos'))

            if request.method == 'POST':
                nome = request.form.get('nome')
                preco = request.form.get('preco')
                link = request.form.get('link')

                if not nome or not preco or not link:
                    flash('Todos os campos são obrigatórios!', 'danger')
                    return render_template('edit_product.html', produto=produto)
                
                try:
                    preco = float(preco)
                    if preco <= 0:
                        flash('Preço deve ser um valor positivo.', 'danger')
                        return render_template('edit_product.html', produto=produto)
                except ValueError:
                    flash('Preço inválido. Use um número.', 'danger')
                    return render_template('edit_product.html', produto=produto)

                cur.execute(
                    "UPDATE produtos SET nome = %s, preco = %s, link = %s WHERE id = %s",
                    (nome, preco, link, produto_id)
                )
                conn.commit()
                print(f"DEBUG EDITAR_PRODUTO: Produto ID {produto_id} atualizado com sucesso.")
                flash('Produto atualizado com sucesso!', 'success')
                return redirect(url_for('produtos'))
            
            # GET request: Renderiza o formulário de edição com os dados do produto
            return render_template('edit_product.html', produto=produto)

    except Exception as e:
        print(f"ERRO EDITAR_PRODUTO: Falha ao editar produto: {e}")
        traceback.print_exc()
        flash('Erro ao editar produto.', 'danger')
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('produtos'))
    finally:
        if conn: conn.close()

@app.route('/deletar_produto/<int:produto_id>', methods=['POST'])
def deletar_produto(produto_id):
    """
    Rota para deletar um produto existente.
    Requer que o usuário esteja logado.
    Esta rota deve ser acessada via POST (por exemplo, por um botão de formulário).
    """
    print(f"DEBUG DELETAR_PRODUTO: Requisição para /deletar_produto/{produto_id}. Method: {request.method}")

    if not session.get('logged_in'):
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Opcional: Verificar se o produto existe antes de tentar deletar
            cur.execute('SELECT id FROM produtos WHERE id = %s', (produto_id,))
            if not cur.fetchone():
                flash('Produto não encontrado.', 'danger')
                return redirect(url_for('produtos'))
            
            # Deleta o produto
            cur.execute('DELETE FROM produtos WHERE id = %s', (produto_id,))
            conn.commit()
            print(f"DEBUG DELETAR_PRODUTO: Produto ID {produto_id} deletado com sucesso.")
            flash('Produto deletado com sucesso!', 'success')
            return redirect(url_for('produtos'))
    except Exception as e:
        print(f"ERRO DELETAR_PRODUTO: Falha ao deletar produto: {e}")
        traceback.print_exc()
        flash('Erro ao deletar produto.', 'danger')
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('produtos'))
    finally:
        if conn: conn.close()

@app.route('/vendas')
def vendas():
    """
    Rota para exibir a lista de vendas na interface web do dashboard.
    Requer que o usuário esteja logado.
    Busca todas as vendas do banco de dados e as renderiza no template vendas.html.
    """
    print("DEBUG VENDAS: Requisição para /vendas.")

    if not session.get('logged_in'):
        print("DEBUG VENDAS: Usuário não logado. Redirecionando para login.")
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Busca todas as vendas com informações de usuário e produto
            cur.execute("""
                SELECT 
                    v.id, 
                    u.username, 
                    u.first_name, 
                    p.nome AS nome_produto, 
                    v.preco, 
                    v.status, 
                    v.data_venda,
                    v.payment_id,
                    v.payer_name,
                    v.payer_email
                FROM vendas v
                JOIN users u ON v.user_id = u.id
                JOIN produtos p ON v.produto_id = p.id
                ORDER BY v.data_venda DESC
            """)
            vendas_lista = cur.fetchall()
            print(f"DEBUG VENDAS: {len(vendas_lista)} vendas encontradas.")

        return render_template('vendas.html', vendas=vendas_lista)

    except Exception as e:
        print(f"ERRO VENDAS: Falha ao carregar vendas para o dashboard: {e}")
        traceback.print_exc()
        flash('Erro ao carregar as vendas.', 'danger')
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    # Inicializa o banco de dados e cria tabelas se não existirem
    init_db()

    # Inicia o worker de mensagens agendadas em uma thread separada
    worker_thread = Thread(target=scheduled_message_worker)
    worker_thread.daemon = True # Define como daemon para que termine com a thread principal
    worker_thread.start()
    print("DEBUG: Thread do worker de mensagens agendadas iniciada.")

    # Inicia a aplicação Flask
    # No Render, ele usará Gunicorn ou um WSGI server similar, então esta parte será para desenvolvimento local
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000), debug=True)