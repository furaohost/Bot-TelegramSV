import os
import requests
import telebot
from telebot import types
import traceback
import time as time_module
from datetime import datetime, timedelta, time
import sqlite3
import base64
import json
from threading import Thread

# Importações Flask e Werkzeug
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from werkzeug.security import check_password_hash, generate_password_hash

# Carrega variáveis de ambiente do arquivo .env (apenas para desenvolvimento local)
from dotenv import load_dotenv
load_dotenv()

# Importa as funções centralizadas de conexão e inicialização do banco de dados
from database import get_db_connection
from database.db_init import init_db

# Importa o módulo de pagamentos do Mercado Pago
import pagamentos

# Importa os módulos de handlers e blueprints
# IMPORTANTE: AQUI ESTÁ A IMPORTAÇÃO DE 'inline_ver_produtos_keyboard'
from bot.utils.keyboards import confirm_18_keyboard, menu_principal, inline_ver_produtos_keyboard 
from bot.handlers.chamadas import register_chamadas_handlers
from bot.handlers.comunidades import register_comunidades_handlers
from bot.handlers.conteudos import register_conteudos_handlers
from bot.handlers.produtos import register_produtos_handlers 
from web.routes.comunidades import comunidades_bp
from bot.handlers.access_passes import register_access_pass_handlers
from web.routes.access_passes import passes_bp


# ────────────────────────────────────────────────────────────────────
# 1. CONFIGURAÇÃO INICIAL (Variáveis de Ambiente)
# ────────────────────────────────────────────────────────────────────
API_TOKEN = os.getenv('API_TOKEN')
BASE_URL = os.getenv('BASE_URL')
DATABASE_URL = os.getenv('DATABASE_URL')
FLASK_SECRET_KEY = os.getenv(
    'FLASK_SECRET_KEY',
    'uma_chave_padrao_muito_segura_e_longa_para_dev_local_1234567890'
)
MERCADOPAGO_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN')


print(f"DEBUG: API_TOKEN lido: {'***' if API_TOKEN else 'NULO'}")
print(f"DEBUG: BASE_URL lida: {BASE_URL}")
print(f"DEBUG: DATABASE_URL lida: {'***' if DATABASE_URL else 'NULO (usando SQLite)'}")
print(f"DEBUG: MERCADOPAGO_ACCESS_TOKEN lido: {'***' if MERCADOPAGO_ACCESS_TOKEN else 'NULO'}")


if not API_TOKEN:
    print(f"ERRO: A variável de ambiente 'API_TOKEN' não está definida. O bot não pode funcionar.")
    raise RuntimeError("API_TOKEN não configurado. O bot não pode funcionar.")


# ────────────────────────────────────────────────────────────────────
# 2. FLASK & TELEBOT (Inicialização dos objetos principais)
# ────────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder='web/templates', static_folder='web/static')
app.secret_key = FLASK_SECRET_KEY
bot = telebot.TeleBot(API_TOKEN, threaded=False, parse_mode='Markdown')

@app.context_processor
def inject_datetime():
    """Injeta o objeto datetime em todos os contextos de template."""
    return {'datetime': datetime}

# ────────────────────────────────────────────────────────────────────
# 3. FUNÇÕES DE UTILIDADE DE BASE DE DADOS
# ────────────────────────────────────────────────────────────────────
def get_or_register_user(user: types.User):
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            print(f"ERRO DB: get_or_register_user - Não foi possível obter conexão com a base de dados.")
            return

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()

            cur.execute("SELECT id, is_active FROM users WHERE id = %s" if not is_sqlite else "SELECT id, is_active FROM users WHERE id = ?", (user.id,))
            db_user = cur.fetchone()

            if db_user is None:
                cur.execute("INSERT INTO users (id, username, first_name, last_name, is_active) VALUES (%s, %s, %s, %s, %s)" if not is_sqlite else "INSERT INTO users (id, username, first_name, last_name, is_active) VALUES (?, ?, ?, ?, ?)",
                            (user.id, user.username, user.first_name, user.last_name, True))
                print(f"DEBUG DB: Novo utilizador registado: {user.username or user.first_name} (ID: {user.id})")
            else:
                if not db_user['is_active']:
                    cur.execute("UPDATE users SET is_active = %s WHERE id = %s" if not is_sqlite else "UPDATE users SET is_active = ? WHERE id = ?", (True, user.id))
                    print(f"DEBUG DB: Utilizador reativado: {user.username or user.first_name} (ID: {user.id})")

    except Exception as e:
        print(f"ERRO DB: get_or_register_user falhou: {e}")
        traceback.print_exc() 
    finally:
        if conn:
            conn.close()

def enviar_produto_telegram(user_id, nome_produto, link_produto):
    url = f"https://api.telegram.org/bot{API_TOKEN}/sendMessage"
    texto = (f"🎉 Pagamento Aprovado!\n\nObrigado por comprar *{nome_produto}*.\n\nAqui está o seu link de acesso:\n{link_produto}")
    payload = { 'chat_id': user_id, 'text': texto, 'parse_mode': 'Markdown' }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print(f"DEBUG: Mensagem de entrega para {user_id} enviada com sucesso.")
    except requests.exceptions.RequestException as e:
        print(f"ERRO: Falha ao enviar mensagem de entrega para {user_id}: {e}")
        traceback.print_exc()
        
def mostrar_produtos_bot_REMOVIDA(chat_id): 
    pass 

def generar_cobranca(call: types.CallbackQuery, produto_id: int):
    user_id, chat_id = call.from_user.id, call.message.chat.id
    conn = None
    venda_id = None 

    try:
        conn = get_db_connection()
        if conn is None:
            bot.send_message(chat_id, "Ocorreu um erro interno ao conectar ao banco de dados para gerar cobrança.")
            return

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            
            if is_sqlite and not hasattr(cur, 'keys'): 
                 conn.row_factory = sqlite3.Row
                 cur = conn.cursor()

            if is_sqlite:
                cur.execute('SELECT id, nome, preco, link FROM produtos WHERE id = ?', (produto_id,)) 
            else:
                cur.execute('SELECT id, nome, preco, link FROM produtos WHERE id = %s', (produto_id,)) 
            produto = cur.fetchone()

            if not produto:
                bot.send_message(chat_id, "Produto não encontrado.")
                return

            data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if is_sqlite:
                cur.execute("INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (?, ?, ?, ?, ?)",
                            (user_id, produto['id'], produto['preco'], 'pendente', data_venda))
                cur.execute("SELECT last_insert_rowid()")
                result_id = cur.fetchone()
                if result_id:
                    venda_id = result_id[0] 
            else:
                cur.execute("INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                            (user_id, produto['id'], produto['preco'], 'pendente', data_venda))
                result_id = cur.fetchone()
                if result_id:
                    venda_id = result_id['id'] 

            if venda_id is None: 
                bot.send_message(chat_id, "Erro ao registrar a venda. Tente novamente.")
                print(f"ERRO GENERAR COBRANCA: Venda não foi registrada, ID nulo.")
                return

            produto_link = produto.get('link') 
            if not produto_link:
                bot.send_message(chat_id, "Erro: Link do produto não configurado.")
                print(f"ERRO GENERAR COBRANCA: Link do produto {produto['nome']} (ID: {produto['id']}) é nulo.")
                return

            pagamento = pagamentos.criar_pagamento_pix(produto=produto, user=call.from_user, venda_id=venda_id)

            if pagamento and 'point_of_interaction' in pagamento:
                qr_code_base64 = pagamento['point_of_interaction']['transaction_data']['qr_code_base64']
                qr_code_data = pagamento['point_of_interaction']['transaction_data']['qr_code']
                qr_code_image = base64.b64decode(qr_code_base64)

                qr_code_data_clean = qr_code_data.replace('\n', '').strip()
                
                caption_text = (
                    f"✅ PIX gerado para *{produto['nome']}*!\n\n"
                    "Escaneie o QR Code acima ou copie o código completo na próxima mensagem."
                )
                bot.send_photo(chat_id, qr_code_image, caption=caption_text, parse_mode='Markdown')

                markup_copy = types.InlineKeyboardMarkup()
                btn_copy = types.InlineKeyboardButton("📋 Copiar Código PIX", callback_data="copy_pix")
                markup_copy.add(btn_copy)

                bot.send_message(chat_id, f"<pre>{qr_code_data_clean}</pre>", parse_mode='HTML', reply_markup=markup_copy)
                
                bot.send_message(chat_id, "Você receberá o produto aqui assim que o pagamento for confirmado.")
                print(f"DEBUG: PIX gerado e enviado para {chat_id} para venda {venda_id}.")
            else:
                bot.send_message(chat_id, "Ocorreu um erro ao gerar o PIX. Tente novamente.")
                print(f"ERRO GENERAR COBRANCA: Falha ao gerar PIX. Resposta do MP: {pagamento}")
    except Exception as e:
        print(f"ERRO GENERAR COBRANCA: Falha ao gerar cobrança/PIX: {e}")
        traceback.print_exc()
        bot.send_message(chat_id, "Ocorreu um erro interno ao gerar sua cobrança. Tente novamente.")
    finally:
        if conn: conn.close()


# ────────────────────────────────────────────────────────────────────
# ADICIONAR UM HANDLER PARA O BOTÃO 'COPIAR PIX'
# ────────────────────────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data == "copy_pix")
def handle_copy_pix_callback(call: types.CallbackQuery):
    bot.answer_callback_query(call.id, "Código PIX copiado para a área de transferência!") 


# ────────────────────────────────────────────────────────────────────
# 4. WORKER de mensagens agendadas
# ────────────────────────────────────────────────────────────────────
@app.template_filter('datetimeformat')
def format_datetime(value, format="%d/%m/%Y %H:%M:%S"):
    """
    Filtro Jinja2 para formatar objetos datetime.
    Deteta se o valor é string (SQLite) ou datetime (PostgreSQL/Python) e formata.
    """
    if isinstance(value, str):
        try:
            if 'T' in value and ('+' in value or value.count(':') == 3):
                dt_obj = datetime.fromisoformat(value.replace('Z', '+00:00') if value.endswith('Z') else value)
            elif ' ' in value and '.' in value:
                dt_obj = datetime.strptime(value.split('.')[0], "%Y-%m-%d %H:%M:%S")
            else:
                dt_obj = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return value
    elif isinstance(value, datetime):
        dt_obj = value
    else:
        return value

    return dt_obj.strftime(format)

app.jinja_env.filters['datetimeformat'] = format_datetime

# ────────────────────────────────────────────────────────────────────
# 5. MIDDLEWARE DE AUTENTICAÇÃO (para painel web)
# ────────────────────────────────────────────────────────────────────
@app.before_request
def require_login():
    """
    Middleware that checks if the user is logged in before accessing certain routes.
    Redirects to the login page if not authenticated.
    """
    # Rotas que não exigem login
    if request.endpoint in ['login', 'static', 'telegram_webhook', 'health_check', 'webhook_mercado_pago', 'reset_admin_password_route', None, 'get_sales_data']:
        return
    
    # As rotas de blueprint são referenciadas como 'blueprint_name.endpoint_function_name'
    if request.endpoint and request.endpoint.startswith('comunidades.') and not session.get('logged_in'):
        print(f"DEBUG AUTH: Unauthorized access to '{request.path}' (Comunidades Blueprint). Redirecting to login.")
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login')) 

    if request.endpoint not in ['login', 'static', 'telegram_webhook', 'health_check', 'webhook_mercado_pago', 'reset_admin_password_route', None, 'get_sales_data'] and not session.get('logged_in'):
        print(f"DEBUG AUTH: Unauthorized access to '{request.path}'. Redirecting to login.")
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))


# ────────────────────────────────────────────────────────────────────
# 6. ROTAS FLASK (Painel Administrativo e Webhooks)
# ────────────────────────────────────────────────────────────────────

@app.route('/health')
def health_check():
    print(f"DEBUG HEALTH: Requisição para /health. Method: {request.method}")
    return "OK", 200

@app.route(f"/{API_TOKEN}", methods=['POST'])
def telegram_webhook():
    """
    Endpoint para o webhook do Telegram. Recebe as atualizações do bot.
    O caminho da rota é o API_TOKEN para maior segurança.
    """
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_str)
        print(f"DEBUG WEBHOOK: Recebido update: {update}") 
        if update.message: 
            print(f"DEBUG WEBHOOK MESSAGE: Texto da mensagem: '{update.message.text}'")
        if update.callback_query: 
            print(f"DEBUG WEBHOOK CALLBACK: Callback data: '{update.callback_query.data}'")
        
        bot.process_new_updates([update])
        return '!', 200
    else:
        return "Unsupported Media Type", 415

@app.route('/webhook/mercado-pago', methods=['GET', 'POST'])
def webhook_mercado_pago():
    if request.method == 'GET':
        return jsonify({'status': 'ok_test_webhook'}), 200

    notification = request.json
    print(f"DEBUG WEBHOOK MP: Notificação recebida: {notification}")

    if not notification or 'data' not in notification or 'id' not in notification['data']:
        return jsonify({'status': 'invalid_notification'}), 400

    payment_id = notification['data']['id']
    payment_info = pagamentos.verificar_status_pagamento(payment_id)

    if not payment_info or payment_info.get('status') != 'approved':
        status = payment_info.get('status', 'não encontrado')
        print(f"DEBUG WEBHOOK MP: Pagamento {payment_id} não aprovado. Status: {status}")
        return jsonify({'status': f'payment_not_approved_{status}'}), 200

    external_reference = payment_info.get('external_reference')
    print(f"DEBUG WEBHOOK MP: Pagamento aprovado. External Reference: {external_reference}")

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # LÓGICA PARA COMPRA DE PASSE DE ACESSO
            if external_reference and external_reference.startswith('pass_purchase:'):
                parts = external_reference.replace('pass_purchase:', '').split(':')
                user_id = int(parts[0].split('=')[1])
                pass_id = int(parts[1].split('=')[1])

                # Busca os detalhes do passe E o ID REAL do chat do Telegram da comunidade associada
                # <-- ALTERAÇÃO AQUI: Trocamos 'c.invite_link' por 'c.chat_id'
                cur.execute("""
                    SELECT ap.*, c.chat_id
                    FROM access_passes ap
                    LEFT JOIN comunidades c ON ap.community_id = c.id
                    WHERE ap.id = %s
                """, (pass_id,))
                pass_item = cur.fetchone()

                if not pass_item:
                    print(f"ERRO: Passe de acesso com ID {pass_id} não encontrado no banco.")
                    return jsonify({'status': 'pass_not_found'}), 404

                duration = timedelta(days=pass_item['duration_days'])
                start_date = datetime.now()
                expiration_date = start_date + duration

                cur.execute(
                    """
                    INSERT INTO user_access
                    (user_id, pass_id, status, start_date, expiration_date, payment_id)
                    VALUES (%s, %s, 'active', %s, %s, %s)
                    """,
                    (user_id, pass_id, start_date, expiration_date, payment_id)
                )
                conn.commit()
                print(f"SUCESSO: Acesso para user {user_id} ao passe {pass_id} registrado. Expira em: {expiration_date}")

                # --- LÓGICA DE GERAÇÃO E ENVIO DE LINK ÚNICO ---
                # <-- ALTERAÇÃO AQUI: Usamos o campo 'chat_id' que buscamos do banco.
                telegram_chat_id = pass_item.get('chat_id')

                if telegram_chat_id:
                    try:
                        # Gera um novo link de convite que expira em 1 dia e só pode ser usado 1 vez.
                        link_info = bot.create_chat_invite_link(
                            chat_id=telegram_chat_id,  # <-- ALTERAÇÃO AQUI: Passa o ID correto para o bot.
                            expire_date=int(time_module.time()) + 86400, # Expira em 24 horas
                            member_limit=1 # Apenas 1 pessoa pode usar
                        )
                        invite_link = link_info.invite_link
                        
                        success_message = (
                            f"✅ Pagamento confirmado! Seu acesso ao *{pass_item['name']}* está ativo.\n\n"
                            f"Use o seu link de acesso exclusivo e de uso único abaixo. Ele é válido por 24 horas:\n"
                            f"{invite_link}"
                        )
                        bot.send_message(user_id, success_message, parse_mode='Markdown')
                    except Exception as e:
                        print(f"ERRO ao criar link de convite para a comunidade com chat_id {telegram_chat_id}: {e}")
                        bot.send_message(user_id, f"✅ Pagamento confirmado! Seu acesso ao *{pass_item['name']}* está ativo, mas houve um erro ao gerar seu link. Por favor, entre em contato com o suporte.")
                else:
                    print(f"ERRO CRÍTICO: Passe {pass_id} está associado a uma comunidade que não possui um 'chat_id' do Telegram cadastrado.")
                    bot.send_message(user_id, f"✅ Pagamento confirmado! Seu acesso ao *{pass_item['name']}* está ativo, mas houve um erro ao gerar seu link. Por favor, entre em contato com o suporte.")
            
            # LÓGICA PARA VENDA DE PRODUTO NORMAL (continua a mesma)
            else:
                venda_id = external_reference
                cur.execute("UPDATE vendas SET status = 'aprovado', payment_id = %s WHERE id = %s", (payment_id, venda_id))
                
                cur.execute("SELECT * FROM vendas WHERE id = %s", (venda_id,))
                venda = cur.fetchone()
                
                cur.execute("SELECT * FROM produtos WHERE id = %s", (venda['produto_id'],))
                produto = cur.fetchone()
                
                if produto:
                    enviar_produto_telegram(venda['user_id'], produto['nome'], produto['link'])
                
                conn.commit()
                print(f"SUCESSO: Venda de produto {venda_id} processada.")

    except Exception as e:
        print(f"ERRO CRÍTICO no processamento do webhook: {e}")
        traceback.print_exc()
        return jsonify({'status': 'internal_server_error'}), 500
    finally:
        if conn:
            conn.close()

    return jsonify({'status': 'notification_processed_successfully'}), 200

@app.route('/login', methods=['GET', 'POST'])
def login():
    print(f"DEBUG LOGIN: Requisição para /login. Method: {request.method}")

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = None
        try:
            conn = get_db_connection()
            if conn is None:
                flash('Erro de conexão com a base de dados.', 'error')
                return render_template('login.html')

            is_sqlite = isinstance(conn, sqlite3.Connection)
            with conn:
                cur = conn.cursor()
                if is_sqlite:
                    cur.execute('SELECT * FROM admin WHERE username = ?', (username,))
                else:
                    cur.execute('SELECT * FROM admin WHERE username = %s', (username,))
                admin_user = cur.fetchone()

                if admin_user and check_password_hash(admin_user['password_hash'], password):
                    session['logged_in'] = True
                    session['username'] = admin_user['username']
                    print(f"DEBUG LOGIN: Login realizado com sucesso para {session['username']}.")
                    flash("Login realizado com sucesso!", "success")
                    return redirect(url_for('index')) 
                else:
                    print(f"DEBUG LOGIN: Usuário ou senha incorretos.")
                    flash('Usuário ou senha inválidos.', 'danger')

        except Exception as e:
            print(f"ERRO LOGIN: Falha no processo de login: {e}")
            traceback.print_exc()
            flash('Erro no servidor ao tentar login.', 'error')
        finally:
            if conn: conn.close()

    print(f"DEBUG LOGIN: Renderizando login.html.")
    return render_template('login.html')


# ==============================================================================
# !! ROTA TEMPORÁRIA PARA RESET DE SENHA !!
# !! REMOVA ESTA ROTA APÓS O USO EM PRODUÇÃO !!
# ==============================================================================
@app.route('/reset-admin-password-now/muito-secreto-12345')
def reset_admin_password_route():
    print(f"DEBUG RESET: Requisição para /reset-admin-password-now/muito-secreto-12345. Method: {request.method}")

    USERNAME_TO_RESET = 'admin'
    NEW_PASSWORD = 'admin123' 

    print(f"DEBUG RESET: Password reset route accessed for user '{USERNAME_TO_RESET}'.")

    hashed_password = generate_password_hash(NEW_PASSWORD)
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            return f"<h1>Error</h1><p>Database connection error.</p>", 500

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            if is_sqlite:
                cur.execute("UPDATE admin SET password_hash = ? WHERE username = ?", (hashed_password, USERNAME_TO_RESET))
            else:
                cur.execute("UPDATE admin SET password_hash = %s WHERE username = %s", (hashed_password, USERNAME_TO_RESET))

            if cur.rowcount == 0:
                print(f"DEBUG RESET: User '{USERNAME_TO_RESET}' not found for update. Attempting to create...")
                if is_sqlite:
                    cur.execute("INSERT INTO admin (username, password_hash) VALUES (?, ?)", (USERNAME_TO_RESET, hashed_password))
                else:
                    cur.execute("INSERT INTO admin (username, password_hash) VALUES (%s, %s)", (USERNAME_TO_RESET, hashed_password))
                message = f"User '{USERNAME_TO_RESET}' not found. A new user was created with the default password. PLEASE, REMOVE THIS ROUTE NOW!"
                print(f"[SUCCESS RESET] {message}")
                return f"<h1>Success</h1><p>{message}</p>", 200

            message = f"Password for user '{USERNAME_TO_RESET}' has been reset successfully. PLEASE, REMOVE THIS ROUTE FROM 'app.py' IMMEDIATELY!"
            print(f"[SUCCESS RESET] {message}")
            return f"<h1>Success</h1><p>{message}</p>", 200

    except Exception as e:
        error_message = f"An error occurred while resetting the password: {e}"
        print(f"ERRO RESET: {error_message}")
        traceback.print_exc()
        return f"<h1>Error</h1><p>{error_message}</p>", 500
    finally:
        if conn:
            conn.close()

@app.route('/logout')
def logout():
    print(f"DEBUG LOGOUT: Requisição para /logout. Method: {request.method}")

    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login')) 


@app.route('/')
def index():
    print(f"DEBUG INDEX: Requisição para /. session.get('logged_in'): {session.get('logged_in')}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('login')) 

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()

            # Inicializa as variáveis com valores padrão
            total_usuarios = 0
            total_produtos = 0
            receita_total = 0.0 
            vendas_recentes = []
            chart_labels = []
            chart_data_receita = [] 
            chart_data_quantidade = []

            # --- Métricas de Período Atual e Período Anterior ---
            today = datetime.now().date() 
            
            start_of_current_month = datetime(today.year, today.month, 1)
            last_day_of_month = (datetime(today.year, today.month + 1, 1) - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999) if today.month < 12 else datetime(today.year, 12, 31, 23, 59, 59, 999999)
            end_of_current_month = last_day_of_month

            start_of_previous_month = (start_of_current_month - timedelta(days=1)).replace(day=1) 
            end_of_previous_month = (start_of_current_month - timedelta(microseconds=1)).replace(hour=23, minute=59, second=59, microsecond=999999) 
            
            def get_sales_data_for_period_internal(start_dt, end_dt, cursor, is_sqlite_db):
                if is_sqlite_db:
                    cursor.execute(
                        "SELECT COUNT(id) AS count, SUM(preco) AS sum FROM vendas WHERE status = 'aprovado' AND data_venda BETWEEN ? AND ?",
                        (start_dt.isoformat(), end_dt.isoformat())
                    )
                else: 
                    cursor.execute(
                        "SELECT COUNT(id) AS count, SUM(preco) AS sum FROM vendas WHERE status = %s AND data_venda BETWEEN %s AND %s",
                        ('aprovado', start_dt, end_dt)
                    )
                row = cursor.fetchone()
                count = row['count'] if row and 'count' in row and row['count'] is not None else 0
                total_sum = float(row['sum']) if row and 'sum' in row and row['sum'] is not None else 0.0
                return count, total_sum

            periodo_atual_vendas_quantidade, periodo_atual_vendas_valor = get_sales_data_for_period_internal(start_of_current_month, end_of_current_month, cur, is_sqlite)
            
            periodo_anterior_vendas_quantidade, periodo_anterior_vendas_valor = get_sales_data_for_period_internal(start_of_previous_month, end_of_previous_month, cur, is_sqlite)

            if periodo_anterior_vendas_quantidade > 0:
                variacao_vendas_quantidade = ((periodo_atual_vendas_quantidade - periodo_anterior_vendas_quantidade) / periodo_anterior_vendas_quantidade) * 100
            else:
                variacao_vendas_quantidade = 100.0 if periodo_atual_vendas_quantidade > 0 else 0.0
            
            if periodo_anterior_vendas_valor > 0:
                variacao_vendas_valor = ((periodo_atual_vendas_valor - periodo_anterior_vendas_valor) / periodo_anterior_vendas_valor) * 100
            else:
                variacao_vendas_valor = 100.0 if periodo_atual_vendas_valor > 0 else 0.0


            cur.execute('SELECT COUNT(id) AS count FROM users WHERE is_active = TRUE' if not is_sqlite else 'SELECT COUNT(id) AS count FROM users WHERE is_active = 1')
            total_usuarios_row = cur.fetchone()
            if total_usuarios_row and 'count' in total_usuarios_row and total_usuarios_row['count'] is not None:
                total_usuarios = total_usuarios_row['count']

            cur.execute('SELECT COUNT(id) AS count FROM produtos')
            total_produtos_row = cur.fetchone()
            if total_produtos_row and 'count' in total_produtos_row and total_produtos_row['count'] is not None:
                total_produtos = total_produtos_row['count']

            cur.execute("SELECT COUNT(id) AS count, SUM(preco) AS sum FROM vendas WHERE status = %s" if not is_sqlite else "SELECT COUNT(id) AS count, SUM(preco) AS sum FROM vendas WHERE status = ?", ('aprovado',))
            vendas_data_row_geral = cur.fetchone()
            if vendas_data_row_geral and 'sum' in vendas_data_row_geral and vendas_data_row_geral['sum'] is not None:
                receita_total = float(vendas_data_row_geral['sum'])
            
            if is_sqlite:
                cur.execute("""
                    SELECT v.id, u.username, u.first_name, p.nome, v.preco, v.data_venda, p.id AS produto_id,
                    CASE WHEN v.status = 'aprovado' THEN 'aprovado'
                         WHEN v.status = 'pendente' AND (strftime('%s', 'now') - strftime('%s', v.data_venda)) > 3600 THEN 'expirado'
                         ELSE v.status
                    END AS status
                    FROM vendas v JOIN users u ON v.user_id = u.id JOIN produtos p ON v.produto_id = p.id
                    ORDER BY v.id DESC LIMIT 5
                """)
            else: 
                cur.execute("""
                    SELECT v.id, u.username, u.first_name, p.nome, v.preco, v.data_venda, p.id AS produto_id,
                    CASE WHEN v.status = 'aprovado' THEN 'aprovado'
                         WHEN v.status = 'pendente' AND EXTRACT(EPOCH FROM (NOW() AT TIME ZONE 'UTC' - v.data_venda)) > 3600 THEN 'expirado'
                         ELSE v.status
                    END AS status
                    FROM vendas v JOIN users u ON v.user_id = u.id JOIN produtos p ON v.produto_id = p.id
                    ORDER BY v.id DESC LIMIT 5
                """)
            vendas_recentes = cur.fetchall()

            today_date_chart = datetime.now().date()
            for i in range(6, -1, -1): 
                day = today_date_chart - timedelta(days=i)
                start_of_day = datetime.combine(day, time.min)
                end_of_day = datetime.combine(day, time.max)
                chart_labels.append(day.strftime('%d/%m'))

                if is_sqlite:
                    cur.execute(
                        "SELECT SUM(preco) AS sum, COUNT(id) AS count FROM vendas WHERE status = ? AND data_venda BETWEEN ? AND ?",
                        ('aprovado', start_of_day.isoformat(), end_of_day.isoformat())
                    )
                else: 
                    cur.execute(
                        "SELECT SUM(preco) AS sum, COUNT(id) AS count FROM vendas WHERE status = %s AND data_venda BETWEEN %s AND %s",
                        ('aprovado', start_of_day, end_of_day)
                    )

                daily_data_row = cur.fetchone()
                daily_revenue = float(daily_data_row['sum']) if daily_data_row and 'sum' in daily_data_row and daily_data_row['sum'] is not None else 0
                daily_quantity = int(daily_data_row['count']) if daily_data_row and 'count' in daily_data_row and daily_data_row['count'] is not None else 0

                chart_data_receita.append(daily_revenue)
                chart_data_quantidade.append(daily_quantity)
                
            print(f"DEBUG INDEX: Rendering index.html with dashboard data.")
            return render_template(
                'index.html',
                total_usuarios=total_usuarios,
                total_produtos=total_produtos,
                receita_total=receita_total,
                periodo_atual_vendas_quantidade=periodo_atual_vendas_quantidade,
                periodo_atual_vendas_valor=periodo_atual_vendas_valor,
                variacao_vendas_quantidade=f"{variacao_vendas_quantidade:.1f}", 
                variacao_vendas_valor=f"{variacao_vendas_valor:.1f}",
                periodo_anterior_vendas_quantidade=periodo_anterior_vendas_quantidade,
                periodo_anterior_vendas_valor=periodo_anterior_vendas_valor,
                
                vendas_recentes=vendas_recentes,
                chart_labels=json.dumps(chart_labels),
                chart_data_receita=json.dumps(chart_data_receita), 
                chart_data_quantidade=json.dumps(chart_data_quantidade), 
                current_year=datetime.now().year,
                data_inicio_periodo_atual=start_of_current_month.strftime('%d/%m/%Y'),
                data_fim_periodo_atual=today.strftime('%d/%m/%Y') 
            )
    except Exception as e:
        print(f"ERRO INDEX: Falha ao renderizar o dashboard: {e}")
        traceback.print_exc()
        flash('Erro ao carregar o dashboard.', 'danger')
        return redirect(url_for('login')) 
    finally:
        if conn:
            conn.close()

@app.route('/api/sales_data', methods=['GET'])
def get_sales_data():
    print(f"DEBUG API SALES DATA: Requisição para /api/sales_data. Method: {request.method}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({'error': 'Erro de conexão com o banco de dados'}), 500

        is_sqlite = isinstance(conn, sqlite3.Connection)
        
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        if not start_date_str or not end_date_str:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=6)
        else:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Formato de data inválido. UsebeginPath-MM-DD.'}), 400
        
        chart_labels = []
        chart_data_receita = []
        chart_data_quantidade = []

        print(f"DEBUG API SALES DATA: start_date={start_date}, end_date={end_date}")

        current_day = start_date 
        
        with conn: 
            cur = conn.cursor()
            while current_day <= end_date: 
                chart_labels.append(current_day.strftime('%d/%m')) 
                start_of_day_dt = datetime.combine(current_day, time.min)
                end_of_day_dt = datetime.combine(current_day, time.max)

                if is_sqlite:
                    cur.execute(
                        "SELECT SUM(preco) AS sum, COUNT(id) AS count FROM vendas WHERE status = 'aprovado' AND data_venda BETWEEN ? AND ?",
                        ('aprovado', start_of_day_dt.isoformat(), end_of_day_dt.isoformat())
                    )
                else: 
                    cur.execute(
                        "SELECT SUM(preco) AS sum, COUNT(id) AS count FROM vendas WHERE status = %s AND data_venda BETWEEN %s AND %s",
                        ('aprovado', start_of_day_dt, end_of_day_dt)
                    )

                daily_data_row = cur.fetchone()
                daily_revenue = float(daily_data_row['sum']) if daily_data_row and 'sum' in daily_data_row and daily_data_row['sum'] is not None else 0
                daily_quantity = int(daily_data_row['count']) if daily_data_row and 'count' in daily_data_row and daily_data_row['count'] is not None else 0

                chart_data_receita.append(daily_revenue)
                chart_data_quantidade.append(daily_quantity)
                
                current_day += timedelta(days=1) 
                
        return jsonify({
            'labels': chart_labels,
            'data_receita': chart_data_receita,
            'data_quantidade': chart_data_quantidade
        }), 200
    except Exception as e:
        print(f"ERRO API SALES DATA: Falha ao obter dados de vendas: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Erro interno do servidor'}), 500
    finally:
        if conn: conn.close()


@app.route('/produtos', methods=['GET', 'POST'])
def produtos():
    print(f"DEBUG PRODUTOS: Requisição para /produtos. Method: {request.method}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'error')
            return redirect(url_for('index')) 

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            if request.method == 'POST':
                nome = request.form.get('nome').strip()
                preco_str = request.form.get('preco')
                link = request.form.get('link').strip()

                if not nome or not preco_str or not link:
                    flash('Todos os campos (Nome, Preço, Link) são obrigatórios.', 'danger')
                    return redirect(url_for('produtos', nome_val=nome, preco_val=preco_str, link_val=link))
                try:
                    preco = float(preco_str)
                    if preco <= 0:
                        flash('O preço deve ser um valor positivo.', 'danger')
                        return redirect(url_for('produtos', nome_val=nome, preco_val=preco_str, link_val=link))
                except ValueError:
                    flash('Preço inválido. Use um número.', 'danger')
                    return redirect(url_for('produtos', nome_val=nome, preco_val=preco_str, link_val=link))

                if is_sqlite:
                    cur.execute('INSERT INTO produtos (nome, preco, link) VALUES (?, ?, ?)', (nome, preco, link))
                else:
                    cur.execute('INSERT INTO produtos (nome, preco, link) VALUES (%s, %s, %s)', (nome, preco, link))
                flash('Produto adicionado com sucesso!', 'success')
                return redirect(url_for('produtos'))

            # For GET request, just fetch and display products
            if is_sqlite:
                cur.execute('SELECT * FROM produtos ORDER BY id DESC')
            else:
                cur.execute('SELECT * FROM produtos ORDER BY id DESC')
            produtos_lista = cur.fetchall()
            print(f"DEBUG PRODUTOS: {len(produtos_lista)} produtos encontrados.")
            return render_template('produtos.html', produtos=produtos_lista)

    except Exception as e:
        print(f"ERRO PRODUTOS: Falha ao gerenciar produtos: {e}")
        traceback.print_exc()
        flash('Erro ao carregar ou adicionar produtos.', 'danger')
        return redirect(url_for('index')) 
    finally:
        if conn:
            conn.close()

@app.route('/editar_produto/<int:produto_id>', methods=['GET', 'POST'])
def editar_produto(produto_id):
    print(f"DEBUG EDITAR_PRODUTO: Requisição para /editar_produto/{produto_id}. Method: {request.method}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados para editar produto.', 'danger')
            return redirect(url_for('produtos')) 

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            if request.method == 'POST':
                nome = request.form.get('nome').strip()
                preco_str = request.form.get('preco')
                link = request.form.get('link').strip()

                if not nome or not preco_str or not link:
                    flash('Todos os campos são obrigatórios!', 'danger')
                    return redirect(url_for('produtos', edit_id=produto_id, nome_val=nome, preco_val=preco_str, link_val=link))

                try:
                    preco = float(preco_str)
                    if preco <= 0:
                        flash('O preço deve ser um valor positivo.', 'danger')
                        return redirect(url_for('produtos', nome_val=nome, preco_val=preco_str, link_val=link))
                except ValueError:
                    flash('Preço inválido. Use um número.', 'danger')
                    return redirect(url_for('produtos', nome_val=nome, preco_val=preco_str, link_val=link))

                if is_sqlite:
                    cur.execute("UPDATE produtos SET nome = ?, preco = ?, link = ? WHERE id = ?", (nome, preco, link, produto_id))
                else:
                    cur.execute("UPDATE produtos SET nome = %s, preco = %s, link = %s WHERE id = %s", (nome, preco, link, produto_id))
                print(f"DEBUG EDITAR_PRODUTO: Produto ID {produto_id} atualizado com sucesso.")
                flash('Produto atualizado com sucesso!', 'success')
                return redirect(url_for('produtos')) 
            else: # GET request to show edit form
                if is_sqlite:
                    cur.execute('SELECT * FROM produtos WHERE id = ?', (produto_id,))
                else:
                    cur.execute('SELECT * FROM produtos WHERE id = %s', (produto_id,))
                produto = cur.fetchone()

                if not produto:
                    flash('Produto não encontrado.', 'danger')
                    return redirect(url_for('produtos')) 

                return render_template('edit_product.html',
                                       produto=produto,
                                       nome_val=produto['nome'],
                                       preco_val=f"{produto['preco']:.2f}",
                                       link_val=produto['link'])

    except Exception as e:
        print(f"ERRO EDIT PRODUTO: Falha ao editar produto: {e}")
        traceback.print_exc()
        flash('Erro ao editar produto.', 'danger')
        return redirect(url_for('produtos', edit_id=produto_id,
                                 nome_val=request.form.get('nome', ''),
                                 preco_val=request.form.get('preco', ''),
                                 link_val=request.form.get('link', '')))
    finally:
        if conn: conn.close()

@app.route('/deletar_produto/<int:produto_id>', methods=['POST'])
def deletar_produto(produto_id):
    print(f"DEBUG DELETAR_PRODUTO: Requisição para /deletar_produto/{produto_id}. Method: {request.method}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'error')
            return redirect(url_for('produtos')) 

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            if is_sqlite:
                cur.execute('SELECT id FROM produtos WHERE id = ?', (produto_id,))
            else:
                cur.execute('SELECT id FROM produtos WHERE id = %s', (produto_id,))
            if not cur.fetchone():
                flash('Produto não encontrado.', 'danger')
                return redirect(url_for('produtos')) 

            if is_sqlite:
                cur.execute('DELETE FROM produtos WHERE id = ?', (produto_id,))
            else:
                cur.execute('DELETE FROM produtos WHERE id = %s', (produto_id,))
            print(f"DEBUG DELETAR_PRODUTO: Produto ID {produto_id} deletado com sucesso.")
            flash('Produto deletado com sucesso!', 'success')
            return redirect(url_for('produtos')) 
    except Exception as e:
        print(f"ERRO REMOVER PRODUTO: Falha ao remover produto: {e}")
        traceback.print_exc()
        flash('Erro ao remover produto.', 'error')
        return redirect(url_for('produtos')) 
    finally:
        if conn: conn.close()

@app.route('/vendas')
def vendas():
    print(f"DEBUG VENDAS: Requisição para /vendas. Method: {request.method}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'error')
            return redirect(url_for('index')) 

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            # Fetch available products for the filter
            cur.execute('SELECT id, nome FROM produtos ORDER BY nome')
            produtos_disponiveis = cur.fetchall()

            # Base SQL query for sales
            query_base = """
                SELECT
                    v.id,
                    u.username,
                    u.first_name,
                    p.nome AS nome_produto,
                    v.preco,
                    v.data_venda,
                    v.payment_id,
                    v.payer_name,
                    v.payer_email,
                    CASE
                        WHEN v.status = 'aprovado' THEN 'aprovado'
                        WHEN v.status = 'pendente' """

            if is_sqlite:
                query_base += " AND (strftime('%s', 'now') - strftime('%s', v.data_venda)) > 3600 THEN 'expirado'"
            else: # PostgreSQL
                query_base += " AND EXTRACT(EPOCH FROM (NOW() AT TIME ZONE 'UTC' - v.data_venda)) > 3600 THEN 'expirado'"
            query_base += """
                        ELSE v.status
                    END AS status
                FROM vendas v
                JOIN users u ON v.user_id = u.id
                JOIN produtos p ON v.produto_id = p.id
            """
            conditions = []
            params = []

            data_inicio_str = request.args.get('data_inicio')
            data_fim_str = request.args.get('data_fim')
            pesquisa_str = request.args.get('pesquisa')
            produto_id_str = request.args.get('produto_id')
            status_str = request.args.get('status')

            if data_inicio_str:
                conditions.append("DATE(v.data_venda) >= %s" if not is_sqlite else "DATE(v.data_venda) >= ?")
                params.append(data_inicio_str)
            if data_fim_str:
                conditions.append("DATE(v.data_venda) <= %s" if not is_sqlite else "DATE(v.data_venda) <= ?")
                params.append(data_fim_str)
            if pesquisa_str:
                conditions.append("(u.username {} %s OR p.nome {} %s OR u.first_name {} %s)".format("ILIKE" if not is_sqlite else "LIKE", "ILIKE" if not is_sqlite else "LIKE", "ILIKE" if not is_sqlite else "LIKE"))
                params.extend([f'%{pesquisa_str}%'] * 3)
            if produto_id_str:
                conditions.append("p.id = %s" if not is_sqlite else "p.id = ?")
                params.append(int(produto_id_str))
            if status_str:
                if status_str == 'expirado':
                    if is_sqlite:
                        conditions.append("(v.status = 'pendente' AND (strftime('%s', 'now') - strftime('%s', v.data_venda)) > 3600)")
                    else:
                        conditions.append("(v.status = 'pendente' AND EXTRACT(EPOCH FROM (NOW() AT TIME ZONE 'UTC' - v.data_venda)) > 3600)")
                else:
                    conditions.append("v.status = %s" if not is_sqlite else "v.status = ?")
                    params.append(status_str)

            if conditions:
                query_base += " WHERE " + " AND ".join(conditions)

            query_base += " ORDER BY v.id DESC"

            cur.execute(query_base, tuple(params))
            vendas_lista = cur.fetchall()
            return render_template('vendas.html', vendas=vendas_lista, produtos_disponiveis=produtos_disponiveis)
    except Exception as e:
        print(f"ERRO VENDAS: Falha ao carregar vendas para o dashboard: {e}")
        traceback.print_exc()
        flash('Erro ao carregar as vendas.', 'danger')
        return redirect(url_for('index')) 
    finally:
        if conn:
            conn.close()

@app.route('/venda_detalhes/<int:id>')
def venda_detalhes(id):
    print(f"DEBUG VENDA DETALHES: Requisição para /venda_detalhes. Method: {request.method}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({'error': 'Erro de conexão com o banco de dados'}), 500

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            if is_sqlite:
                cur.execute('SELECT * FROM vendas WHERE id = ?', (id,))
            else:
                cur.execute('SELECT * FROM vendas WHERE id = %s', (id,))

            venda = cur.fetchone()
            if venda:
                venda_dict = dict(venda)
                if 'data_venda' in venda_dict and isinstance(venda_dict['data_venda'], datetime):
                    venda_dict['data_venda'] = venda_dict['data_venda'].isoformat()
                return jsonify(venda_dict)
            return jsonify({'error': 'Venda não encontrada'}), 404
    except Exception as e:
        print(f"ERRO VENDA DETALHES: Falha ao obter detalhes da venda: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Erro interno do servidor'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/usuarios')
def usuarios():
    print(f"DEBUG USUARIOS: Requisição para /usuarios. Method: {request.method}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'error')
            return redirect(url_for('index')) 

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            if is_sqlite:
                cur.execute('SELECT * FROM users ORDER BY data_registro DESC')
            else:
                cur.execute('SELECT * FROM users ORDER BY data_registro DESC')
            usuarios_lista = cur.fetchall()
            print(f"DEBUG USUARIOS: {len(usuarios_lista)} usuários encontrados.")

        return render_template('usuarios.html', usuarios=usuarios_lista)

    except Exception as e:
        print(f"ERRO UTILIZADORES: Falha ao carregar utilizadores: {e}")
        traceback.print_exc()
        flash('Erro ao carregar utilizadores.', 'error')
        return redirect(url_for('index')) 
    finally:
        if conn:
            conn.close()

@app.route('/toggle_user_status/<int:user_id>', methods=['POST'])
def toggle_user_status(user_id):
    print(f"DEBUG TOGGLE_USER_STATUS: Requisição para /toggle_user_status/{user_id}. Method: {request.method}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'error')
            return redirect(url_for('usuarios')) 

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            if is_sqlite:
                cur.execute('SELECT is_active FROM users WHERE id = ?', (user_id,))
            else:
                cur.execute('SELECT is_active FROM users WHERE id = %s', (user_id,))
            user = cur.fetchone()

            if not user:
                flash('Usuário não encontrado.', 'danger')
                return redirect(url_for('usuarios')) 

            new_status = not user['is_active']
            if is_sqlite:
                cur.execute('UPDATE users SET is_active = ? WHERE id = ?', (new_status, user_id))
            else:
                cur.execute('UPDATE users SET is_active = %s WHERE id = %s', (new_status, user_id))

            status_text = "ativado" if new_status else "desativado"
            print(f"DEBUG TOGGLE_USER_STATUS: Usuário {user_id} {status_text} com sucesso.")
            flash(f'Usuário {user_id} {status_text} com sucesso!', 'success')
            return redirect(url_for('usuarios')) 
    except Exception as e:
        print(f"ERRO REMOVER UTILIZADOR: Falha ao remover utilizador: {e}")
        traceback.print_exc()
        flash('Erro ao remover utilizador.', 'error')
        return redirect(url_for('usuarios')) 
    finally:
        if conn: conn.close()

@app.route('/scheduled_messages')
def scheduled_messages():
    print(f"DEBUG SCHEDULED_MESSAGES: Requisição para /scheduled_messages. Method: {request.method}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'error')
            return redirect(url_for('login')) 

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            if is_sqlite:
                cur.execute("""
                    SELECT
                        sm.id,
                        sm.message_text,
                        sm.target_chat_id,
                        sm.image_url,
                        sm.schedule_time,
                        sm.status,
                        sm.created_at,
                        sm.sent_at,
                        COALESCE(u.username, 'Todos os usuários') AS target_username
                    FROM scheduled_messages sm
                    LEFT JOIN users u ON sm.target_chat_id = u.id
                    ORDER BY sm.schedule_time DESC
                """)
            else:
                cur.execute("""
                    SELECT
                        sm.id,
                        sm.message_text,
                        sm.target_chat_id,
                        sm.image_url,
                        sm.schedule_time,
                        sm.status,
                        sm.created_at,
                        sm.sent_at,
                        COALESCE(u.username, 'Todos os usuários') AS target_username
                    FROM scheduled_messages sm
                    LEFT JOIN users u ON sm.target_chat_id = u.id
                    ORDER BY sm.schedule_time DESC
                """)
            messages_list = cur.fetchall()
            print(f"DEBUG SCHEDULED_MESSAGES: {len(messages_list)} mensagens agendadas encontradas.")

        return render_template('scheduled_messages.html', messages=messages_list)
    except Exception as e:
        print(f"ERRO SCHEDULED MESSAGES: Falha ao carregar mensagens agendadas: {e}")
        traceback.print_exc()
        flash('Erro ao carregar ou atualizar mensagens.', 'error')
        return redirect(url_for('index')) 
    finally:
        if conn: conn.close()

@app.route('/add_scheduled_message', methods=['GET', 'POST'])
def add_scheduled_message():
    print(f"DEBUG ADD SCHEDULED MESSAGE: Requisição para /add_scheduled_message. Method: {request.method}")

    if request.method == 'POST':
        try:
            message_text = request.form.get('message_text')
            target_chat_id = request.form.get('target_chat_id')
            image_url = request.form.get('image_url')
            schedule_time_str = request.form.get('schedule_time')
            recurrence_rule = request.form.get('recurrence_rule', 'none') 

            if not message_text or not schedule_time_str:
                flash('Texto da mensagem e data/hora são obrigatórios!', 'danger')
                return redirect(url_for('add_scheduled_message'))

            schedule_time = datetime.strptime(schedule_time_str, '%Y-%m-%dT%H:%M')

            if schedule_time <= datetime.now():
                flash('A data e hora de agendamento devem ser no futuro.', 'danger')
                return redirect(url_for('add_scheduled_message'))

            target_chat_id_db = None if target_chat_id == 'all_users' else int(target_chat_id)
            
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO scheduled_messages 
                    (message_text, target_chat_id, image_url, schedule_time, status, recurrence_rule) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (message_text, target_chat_id_db, image_url or None, schedule_time, 'pending', recurrence_rule)
                )
            conn.commit()
            conn.close()

            flash('Mensagem agendada com sucesso!', 'success')
            return redirect(url_for('scheduled_messages')) 

        except ValueError:
            flash('Formato de dados inválido.', 'danger')
        except Exception as e:
            print(f"ERRO ADD SCHEDULED MESSAGE: {e}")
            traceback.print_exc()
            flash('Ocorreu um erro inesperado ao agendar a mensagem.', 'danger')
        
        return redirect(url_for('add_scheduled_message'))

    # Lógica para GET (exibir formulário)
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute('SELECT id, username, first_name FROM users WHERE is_active = TRUE ORDER BY username ASC')
        users = cur.fetchall()
    conn.close()
    return render_template('add_scheduled_message.html', users=users)

@app.route('/edit_scheduled_message/<int:message_id>', methods=['GET', 'POST'])
def edit_scheduled_message(message_id):
    print(f"DEBUG EDIT SCHEDULED MESSAGE: Requisição para /edit_scheduled_message/{message_id}. Method: {request.method}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('scheduled_messages')) 

        is_sqlite = isinstance(conn, sqlite3.Connection)
        
        # Busca os dados da mensagem para o GET e para o POST
        with conn.cursor() as cur:
            if is_sqlite:
                cur.execute('SELECT * FROM scheduled_messages WHERE id = ?', (message_id,))
            else:
                cur.execute('SELECT * FROM scheduled_messages WHERE id = %s', (message_id,))
            message = cur.fetchone()

        if not message:
            flash('Mensagem agendada não encontrada.', 'danger')
            return redirect(url_for('scheduled_messages')) 

        # Se a requisição for POST, tenta salvar as alterações
        if request.method == 'POST':
            message_text = request.form.get('message_text')
            target_chat_id_str = request.form.get('target_chat_id', '').strip()
            image_url = request.form.get('image_url')
            schedule_time_str = request.form.get('schedule_time')

            if not message_text or not schedule_time_str:
                flash('Texto da mensagem e tempo de agendamento são obrigatórios!', 'danger')
                return render_template('edit_scheduled_message.html', message=message)

            target_chat_id_db = None
            if target_chat_id_str:
                try:
                    target_chat_id_db = int(target_chat_id_str)
                except ValueError:
                    flash('ID do chat de destino inválido. Deve ser um número.', 'danger')
                    return render_template('edit_scheduled_message.html', message=message)
            
            schedule_time = datetime.strptime(schedule_time_str, '%Y-%m-%dT%H:%M')

            # Atualiza o banco de dados SEM ALTERAR O STATUS
            with conn.cursor() as cur:
                if is_sqlite:
                    cur.execute(
                        "UPDATE scheduled_messages SET message_text = ?, target_chat_id = ?, image_url = ?, schedule_time = ? WHERE id = ?",
                        (message_text, target_chat_id_db, image_url or None, schedule_time, message_id)
                    )
                else:
                    cur.execute(
                        "UPDATE scheduled_messages SET message_text = %s, target_chat_id = %s, image_url = %s, schedule_time = %s WHERE id = %s",
                        (message_text, target_chat_id_db, image_url or None, schedule_time, message_id)
                    )
            conn.commit()
            flash('Mensagem agendada atualizada com sucesso!', 'success')
            return redirect(url_for('scheduled_messages')) 

        # Se a requisição for GET, apenas exibe o formulário
        message['schedule_time_formatted'] = message['schedule_time'].strftime('%Y-%m-%dT%H:%M') if message['schedule_time'] else ''
        return render_template('edit_scheduled_message.html', message=message)

    except Exception as e:
        print(f"ERRO EDIT SCHEDULED MESSAGE: Falha ao editar mensagem agendada: {e}")
        traceback.print_exc()
        flash('Erro ao editar mensagem agendada.', 'danger')
        return redirect(url_for('scheduled_messages')) 
    finally:
        if conn:
            conn.close()

@app.route('/resend_scheduled_message/<int:message_id>', methods=['POST'])
def resend_scheduled_message(message_id):
    print(f"DEBUG CLONE SCHEDULED MESSAGE: Requisição para clonar a mensagem ID {message_id}.")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('scheduled_messages')) 

        with conn.cursor() as cur:
            if isinstance(conn, sqlite3.Connection):
                 cur.execute("SELECT * FROM scheduled_messages WHERE id = ?", (message_id,))
            else:
                 cur.execute("SELECT * FROM scheduled_messages WHERE id = %s", (message_id,))
            original_message = cur.fetchone()

            if not original_message:
                flash('Mensagem original não encontrada para clonar.', 'warning')
                return redirect(url_for('scheduled_messages')) 

            insert_query = """
                INSERT INTO scheduled_messages (message_text, target_chat_id, image_url, status, schedule_time)
                VALUES (%s, %s, %s, 'pending', NOW())
                RETURNING id
                """
            insert_params = (
                original_message['message_text'],
                original_message['target_chat_id'],
                original_message['image_url']
            )

            is_sqlite = isinstance(conn, sqlite3.Connection)
            if is_sqlite:
                insert_query = "INSERT INTO scheduled_messages (message_text, target_chat_id, image_url, status, schedule_time) VALUES (?, ?, ?, ?, ?)"
                insert_params = (
                    original_message['message_text'],
                    original_message['target_chat_id'],
                    original_message['image_url'],
                    'pending',
                    datetime.now()
                )
                cur.execute(insert_query, insert_params)
                cur.execute("SELECT last_insert_rowid()")
                new_message_id = cur.fetchone()[0]
            else:
                cur.execute(insert_query, insert_params)
                new_message_id = cur.fetchone()['id']
            
            conn.commit()

            flash('Mensagem clonada com sucesso! Por favor, defina um novo horário de agendamento.', 'success')
            
            return redirect(url_for('edit_scheduled_message', message_id=new_message_id, from_clone=True)) 

    except Exception as e:
        print(f"ERRO CLONE MESSAGE: {e}")
        traceback.print_exc()
        flash('Ocorreu um erro ao tentar clonar a mensagem.', 'danger')
        return redirect(url_for('scheduled_messages')) 
    finally:
        if conn:
            conn.close()


@app.route('/delete_scheduled_message/<int:message_id>', methods=['POST'])
def delete_scheduled_message(message_id):
    print(f"DEBUG DELETE SCHEDULED MESSAGE: Requisição para deletar a mensagem ID {message_id}.")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('scheduled_messages')) 

        with conn.cursor() as cur:
            if isinstance(conn, sqlite3.Connection):
                cur.execute("SELECT id FROM scheduled_messages WHERE id = ?", (message_id,))
            else:
                cur.execute("SELECT id FROM scheduled_messages WHERE id = %s", (message_id,))
            
            if cur.fetchone() is None:
                flash('Mensagem não encontrada para deletar.', 'warning')
            else:
                if isinstance(conn, sqlite3.Connection):
                    cur.execute("DELETE FROM scheduled_messages WHERE id = ?", (message_id,))
                else:
                    cur.execute("DELETE FROM scheduled_messages WHERE id = %s", (message_id,))
                conn.commit()
                flash('Mensagem agendada deletada com sucesso!', 'success')
                
    except Exception as e:
        print(f"ERRO DELETE MESSAGE: {e}")
        traceback.print_exc() 
        flash('Ocorreu um erro ao tentar deletar a mensagem.', 'danger')
    finally:
        if conn:
            conn.close()
            
    return redirect(url_for('scheduled_messages')) 

@app.route('/cancel_cloned_message/<int:message_id>', methods=['GET'])
def cancel_cloned_message(message_id):
    print(f"DEBUG CANCEL CLONE: Requisição para cancelar e deletar o clone ID {message_id}.")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None: 
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('scheduled_messages')) 

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn.cursor() as cur:
            if is_sqlite:
                cur.execute("DELETE FROM scheduled_messages WHERE id = ?", (message_id,))
            else:
                cur.execute("DELETE FROM scheduled_messages WHERE id = %s", (message_id,))
        conn.commit()
        flash('Reenvio cancelado e cópia da mensagem descartada.', 'info')
    except Exception as e:
        print(f"ERRO CANCEL CLONE: {e}")
        traceback.print_exc() 
        flash('Ocorreu um erro ao descartar a cópia da mensagem.', 'danger')
    finally:
        if conn:
            conn.close()
            
    return redirect(url_for('scheduled_messages')) 

@app.route('/send_broadcast', methods=['GET', 'POST'])
def send_broadcast():
    print(f"DEBUG SEND BROADCAST: Requisição para /send_broadcast. Method: {request.method}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('index', error='broadcast_db_connection_error')) 

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            if is_sqlite:
                cur.execute('SELECT id, username, first_name FROM users ORDER BY username ASC')
            else:
                cur.execute('SELECT id, username, first_name FROM users ORDER BY username ASC')
            active_users = cur.fetchall()

        if request.method == 'POST':
            message_text = request.form.get('message_text')
            image_url = request.form.get('image_url')

            if not message_text:
                flash('O texto da mensagem é obrigatório para o broadcast!', 'danger')
                return render_template('send_broadcast.html', active_users=active_users, message_text_val=message_text, image_url_val=image_url)

            sent_count = 0
            failed_count = 0

            cur_conn_send = get_db_connection()
            if cur_conn_send is None:
                flash('Erro de conexão com o banco de dados.', 'danger')
                return render_template('send_broadcast.html', active_users=active_users, message_text_val=message_text, image_url_val=image_url)

            try:
                with cur_conn_send:
                    cur_send = cur_conn_send.cursor()
                    if is_sqlite:
                        cur_send.execute("SELECT id FROM users WHERE is_active = 1")
                    else:
                        cur_send.execute("SELECT id FROM users WHERE is_active = TRUE")
                    users_to_send = cur_send.fetchall()

                    for user_data in users_to_send:
                        user_id = user_data['id']
                        try:
                            if image_url:
                                bot.send_photo(user_id, image_url, caption=message_text, parse_mode="Markdown")
                            else:
                                bot.send_message(user_id, message_text, parse_mode="Markdown")
                            sent_count += 1
                        except telebot.apihelper.ApiTelegramException as e:
                            print(f"ERRO BROADCAST para {user_id}: {e}")
                            if "blocked" in str(e).lower() or "not found" in str(e).lower() or "deactivated" in str(e).lower():
                                print(f"AVISO: Usuário {user_id} blocked/not found during broadcast. Deactivating...")
                                temp_conn_update = get_db_connection()
                                if temp_conn_update:
                                    temp_is_sqlite = isinstance(temp_conn_update, sqlite3.Connection)
                                    try:
                                        with temp_conn_update:
                                            cur_u = temp_conn_update.cursor()
                                            if temp_is_sqlite:
                                                cur_u.execute("UPDATE users SET is_active=0 WHERE id=?", (user_id,))
                                            else:
                                                cur_u.execute("UPDATE users SET is_active=FALSE WHERE id=%s", (user_id,))
                                    except Exception as db_e:
                                        print(f"ERRO inactivating user {user_id} during broadcast: {db_e}")
                                        traceback.print_exc()
                                    finally:
                                        if temp_conn_update: temp_conn_update.close()
                        except Exception as e:
                            print(f"ERRO UNEXPECTED BROADCAST to {user_id}: {e}")
                            traceback.print_exc()
                            failed_count += 1 

                flash(f'Broadcast enviado com sucesso para {sent_count} usuários. Falha em {failed_count} usuários.', 'success')
                return redirect(url_for('index')) 
            except Exception as e:
                print(f"ERRO SEND BROADCAST (send logic): {e}")
                traceback.print_exc()
                flash('Ocorreu um erro ao tentar enviar o broadcast.', 'danger')
                return render_template('send_broadcast.html', active_users=active_users, message_text_val=message_text, image_url_val=image_url)
            finally:
                if cur_conn_send: cur_conn_send.close()

        return render_template('send_broadcast.html', active_users=active_users)

    except Exception as e:
        print(f"ERRO SEND BROADCAST (GET): Falha ao carregar usuários para o formulário: {e}")
        traceback.print_exc()
        flash('Erro ao carregar a página de broadcast.', 'danger')
        return redirect(url_for('index')) 
    finally:
        if conn: conn.close()

@app.route('/config_messages', methods=['GET', 'POST'])
def config_messages():
    print(f"DEBUG CONFIG_MESSAGES: Requisição para /config_messages. Method: {request.method}")

    conn = None
    welcome_message_bot = 'Olá, {first_name}! Bem-vindo(a) ao bot!'
    welcome_message_community = 'Bem-vindo(a) à nossa comunidade, {first_name}!'

    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados. Não foi possível carregar/salvar configurações.', 'danger')
            return render_template(
                'config_messages.html',
                welcome_message_bot=welcome_message_bot,
                welcome_message_community=welcome_message_community
            )

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            
            if request.method == 'POST':
                welcome_bot_message_form = request.form.get('welcome_message_bot')
                welcome_community_message_form = request.form.get('welcome_message_community')

                if welcome_bot_message_form is not None:
                    if is_sqlite:
                        cur.execute(
                            "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value;",
                            ('welcome_message_bot', welcome_bot_message_form)
                        )
                    else:
                        cur.execute(
                            "INSERT INTO config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;",
                            ('welcome_message_bot', welcome_bot_message_form)
                        )
                
                if welcome_community_message_form is not None:
                    if is_sqlite:
                        cur.execute(
                            "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value;",
                            ('welcome_message_community', welcome_community_message_form)
                        )
                    else:
                        cur.execute(
                            "INSERT INTO config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;",
                            ('welcome_message_community', welcome_community_message_form)
                        )
                
                flash('Configurações de mensagens atualizadas com sucesso!', 'success')
                return redirect(url_for('config_messages')) 

            # Lógica para GET request (ou após POST e redirecionamento)
            if is_sqlite:
                cur.execute("SELECT key, value FROM config WHERE key IN (?, ?)", ('welcome_message_bot', 'welcome_message_community'))
            else:
                cur.execute("SELECT key, value FROM config WHERE key IN (%s, %s)", ('welcome_message_bot', 'welcome_message_community'))
            configs_raw = cur.fetchall()
            configs = {row['key']: row['value'] for row in configs_raw}

            welcome_message_bot = configs.get('welcome_message_bot', welcome_message_bot)
            welcome_message_community = configs.get('welcome_message_community', welcome_message_community)

            return render_template(
                'config_messages.html',
                welcome_message_bot=welcome_message_bot,
                welcome_message_community=welcome_message_community
            )

    except Exception as e:
        print(f"ERRO CONFIG_MESSAGES: Falha ao carregar/salvar configurações de mensagens: {e}")
        traceback.print_exc()
        flash('Erro ao carregar/salvar configurações de mensagens.', 'danger')
        return render_template(
            'config_messages.html',
            welcome_message_bot=welcome_message_bot,
            welcome_message_community=welcome_message_community
        )
    finally:
        if conn: conn.close()

# ────────────────────────────────────────────────────────────────────
# 7. WORKER de mensagens agendadas
# ────────────────────────────────────────────────────────────────────
def scheduled_message_worker():
    print(f"DEBUG WORKER: Iniciado e aguardando para verificar mensagens...")
    while True:
        conn = None
        try:
            conn = get_db_connection()
            if conn is None:
                print(f"ERRO WORKER: Não foi possível obter conexão. Tentando novamente em 60s...")
                time_module.sleep(60)
                continue

            with conn.cursor() as cur:
                if isinstance(conn, sqlite3.Connection):
                    cur.execute(
                        "SELECT * FROM scheduled_messages WHERE status='pending' AND schedule_time <= DATETIME('now') ORDER BY schedule_time"
                    )
                else:
                    cur.execute(
                        "SELECT * FROM scheduled_messages WHERE status='pending' AND schedule_time <= NOW() ORDER BY schedule_time"
                    )
                rows = cur.fetchall()

                if rows:
                    print(f"DEBUG WORKER: Encontradas {len(rows)} mensagens para enviar.")

                for row in rows:
                    print(f"DEBUG WORKER: Processando mensagem ID {row['id']} para o alvo: {row['target_chat_id'] or 'Todos'}")
                    
                    targets = []
                    if row["target_chat_id"]:
                        targets.append(row["target_chat_id"])
                    else: # Se for para todos (broadcast)
                        if isinstance(conn, sqlite3.Connection):
                            cur.execute("SELECT id FROM users WHERE is_active = 1")
                        else:
                            cur.execute("SELECT id FROM users WHERE is_active = TRUE")
                        all_users = cur.fetchall()
                        targets = [u["id"] for u in all_users]

                    print(f"DEBUG WORKER: A mensagem {row['id']} será enviada para {len(targets)} usuários.")
                    
                    sent_successfully = False 
                    for chat_id in targets:
                        try:
                            if row["image_url"]:
                                bot.send_photo(chat_id, row["image_url"], caption=row["message_text"], parse_mode="Markdown")
                            else:
                                bot.send_message(chat_id, row["message_text"], parse_mode="Markdown")
                            sent_successfully = True 
                        except Exception as e:
                            print(f"ERRO WORKER: Falha ao enviar msg {row['id']} para o chat {chat_id}: {e}")
                            traceback.print_exc()
                    
                    final_status = 'sent' if sent_successfully else 'failed'
                    if isinstance(conn, sqlite3.Connection):
                        cur.execute(
                            "UPDATE scheduled_messages SET status=?, sent_at=DATETIME('now') WHERE id=?",
                            (final_status, row["id"]),
                        )
                    else:
                        cur.execute(
                            "UPDATE scheduled_messages SET status=%s, sent_at=NOW() WHERE id=%s",
                            (final_status, row["id"]),
                        )
                    print(f"DEBUG WORKER: Mensagem ID {row['id']} atualizada para status '{final_status}'.")
            
            conn.commit()

        except Exception as e:
            print(f"ERRO CRÍTICO no Loop do Worker: {e}")
            traceback.print_exc()
        finally:
            if conn:
                conn.close()

        time_module.sleep(60)

# ====================================================================
# NOVA FUNÇÃO PARA GERENCIAR O ACESSO ÀS COMUNIDADES
# ====================================================================
def manage_community_access(user_id, community_id, should_have_access):
    """
    Adiciona ou remove um usuário de uma comunidade no Telegram.
    """
    if not community_id:
        print(f"AVISO: Tentativa de gerenciar acesso para user {user_id} sem um community_id.")
        return

    try:
        if should_have_access:
            # Esta ação permite que um usuário que foi removido possa voltar a entrar.
            # O ideal é enviar um novo link de convite para o usuário.
            bot.unban_chat_member(community_id, user_id, only_if_banned=True)
            print(f"ACESSO LIBERADO: Acesso para user {user_id} na comunidade {community_id} foi permitido.")
        else:
            # Remove (expulsa) o usuário do grupo/canal.
            bot.kick_chat_member(community_id, user_id)
            print(f"ACESSO REMOVIDO: User {user_id} foi removido da comunidade {community_id}.")
            bot.send_message(user_id, "Seu passe de acesso expirou e você foi removido da comunidade. Para voltar, compre um novo passe usando o comando /passes.")
    except Exception as e:
        # Erros comuns: bot não é admin, usuário não está no grupo, etc.
        print(f"ERRO ao gerenciar acesso do user {user_id} na comunidade {community_id}: {e}")

def access_expiration_worker():
    """
    Worker que roda em segundo plano para verificar e expirar passes de acesso.
    """
    print("WORKER DE EXPIRAÇÃO: Iniciado. Verificando passes a cada hora.")
    while True:
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                # Busca todos os acessos que estão ativos mas cuja data de expiração já passou
                cur.execute("""
                    SELECT ua.id, ua.user_id, ap.community_id
                    FROM user_access ua
                    JOIN access_passes ap ON ua.pass_id = ap.id
                    WHERE ua.status = 'active' AND ua.expiration_date <= NOW();
                """)
                expired_passes = cur.fetchall()

                if expired_passes:
                    print(f"WORKER DE EXPIRAÇÃO: Encontrados {len(expired_passes)} passes expirados.")
                    for expired_pass in expired_passes:
                        user_id_to_remove = expired_pass['user_id']
                        community_id_to_remove_from = expired_pass['community_id']
                        access_id_to_update = expired_pass['id']

                        print(f"WORKER: Expirando acesso ID {access_id_to_update} para o usuário {user_id_to_remove}.")

                        # 1. Remove o acesso do usuário no Telegram
                        manage_community_access(user_id_to_remove, community_id_to_remove_from, should_have_access=False)
                        
                        # 2. Atualiza o status do acesso no banco de dados para 'expired'
                        cur.execute("UPDATE user_access SET status = 'expired' WHERE id = %s", (access_id_to_update,))
                    
                    conn.commit()
                else:
                    print("WORKER DE EXPIRAÇÃO: Nenhum passe expirado encontrado nesta verificação.")

        except Exception as e:
            print(f"ERRO CRÍTICO no Worker de Expiração: {e}")
            traceback.print_exc()
        finally:
            if conn:
                conn.close()
        
        # Espera 1 hora (3600 segundos) antes da próxima verificação
        time_module.sleep(3600)

# ────────────────────────────────────────────────────────────────────
# 9. FINAL INITIALIZATION AND EXECUTION
# ────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=['start'])
def send_welcome(message):
    print(f"DEBUG SEND WELCOME: Requisição para /start. Message: {message.text}")

    get_or_register_user(message.from_user)

    conn = None
    welcome_message_text = "Olá, {first_name}! Bem-vindo(a) ao bot!" 
    try:
        conn = get_db_connection()
        if conn is None:
            print(f"ERRO: Não foi possível obter conexão com o DB para carregar mensagem de boas-vindas do bot.")
            pass
        else:
            is_sqlite = isinstance(conn, sqlite3.Connection)
            with conn:
                cur = conn.cursor()
                if is_sqlite:
                    cur.execute("SELECT value FROM config WHERE key = ?", ('welcome_message_bot',))
                else:
                    cur.execute("SELECT value FROM config WHERE key = %s", ('welcome_message_bot',))
                row = cur.fetchone()
                if row and row['value']: 
                    welcome_message_text = row['value']
    except Exception as e:
        print(f"ERRO ao carregar mensagem de boas-vindas do bot: {e}")
        traceback.print_exc()
    finally:
        if conn: conn.close()

    formatted_message = welcome_message_text.format(
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name or '',
        username=message.from_user.username or 'usuário'
    )
    
    # MUDANÇA AQUI: Mensagem de boas-vindas com botão INLINE "Melhores Vips e Novinhas"
    bot.reply_to(message, formatted_message, reply_markup=inline_ver_produtos_keyboard())

    # REMOVIDO: A chamada direta a `mostrar_produtos_bot_func` não é mais feita aqui,
    # pois o clique no botão inline "Melhores Vips e Novinhas" acionará a listagem.


if __name__ != '__main__':
    print(f"DEBUG: Executando em modo de produção (gunicorn/Render).")
    try:
        init_db()
        pagamentos.init_mercadopago_sdk()
        if API_TOKEN and BASE_URL:
            webhook_url = f"{BASE_URL}/{API_TOKEN}"
            bot.set_webhook(url=webhook_url)
            print(f"DEBUG: Webhook do Telegram configurado para: {webhook_url}")
        
        worker_thread = Thread(target=scheduled_message_worker)
        worker_thread.daemon = True
        worker_thread.start()
        print(f"DEBUG: Worker de mensagens agendadas iniciado em background para o modo de produção.")

        # REGISTRAR HANDLERS 
        register_chamadas_handlers(bot, get_db_connection)
        register_comunidades_handlers(bot, get_db_connection)
        register_conteudos_handlers(bot, get_db_connection)
        register_access_pass_handlers(bot) 
        
        # Passando 'generar_cobranca' como argumento.
        # A função `mostrar_produtos_bot` NÃO é mais retornada,
        # pois ela será chamada pelo handler do botão inline em `bot/handlers/produtos.py`.
        register_produtos_handlers(bot, get_db_connection, generar_cobranca) 
        
        # REGISTRAR BLUEPRINT DE COMUNIDADES (EXISTENTE)
        app.register_blueprint(comunidades_bp, url_prefix='/') 
        app.register_blueprint(passes_bp)

    except Exception as e:
        print(f"ERRO NA INICIALIZAÇÃO DO SERVIDOR: {e}")
        traceback.print_exc()