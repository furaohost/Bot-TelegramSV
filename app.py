import os
import requests
import telebot
from telebot import types
import traceback
import time as time_module
from datetime import datetime, timedelta, time
from threading import Thread
import sqlite3
import base64
import json

#importe datetime


# Importações Flask e Werkzeug
from datetime import datetime
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
from bot.utils.keyboards import confirm_18_keyboard, menu_principal
from bot.handlers.chamadas import register_chamadas_handlers
from bot.handlers.comunidades import register_comunidades_handlers
# Se 'ofertas.py' ainda existe para outras funcionalidades:
 
from bot.handlers.conteudos import register_conteudos_handlers
from bot.handlers.produtos import register_produtos_handlers # <<== ESTE É O NOVO IMPORT para o seu 'produtos.py'
from web.routes.comunidades import create_comunidades_blueprint


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


# Verifica se o API_TOKEN está configurado
if not API_TOKEN:
    print("ERRO: A variável de ambiente 'API_TOKEN' não está definida. O bot não pode funcionar.")
    raise RuntimeError("API_TOKEN não configurado. O bot não pode funcionar.")


# ────────────────────────────────────────────────────────────────────
# 2. FLASK & TELEBOT (Inicialização dos objetos principais)
# ────────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder='web/templates', static_folder='web/static')
app.secret_key = FLASK_SECRET_KEY
bot = telebot.TeleBot(API_TOKEN, threaded=False, parse_mode='Markdown')

# Adicione este bloco:
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
            print("ERRO DB: get_or_register_user - Não foi possível obter conexão com a base de dados.")
            return

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn: # Use 'with conn' for transaction management and auto-closing
            cur = conn.cursor()

            # Verifica se o utilizador já existe
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

def mostrar_produtos_bot(chat_id):
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            bot.send_message(chat_id, "Ocorreu um erro interno ao conectar ao banco de dados.")
            return

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            if is_sqlite:
                cur.execute('SELECT * FROM produtos')
            else:
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
        print(f"ERRO MOSTRAR PRODUTOS BOT: Falha ao mostrar produtos: {e}")
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
        if conn is None:
            bot.send_message(chat_id, "Ocorreu um erro interno ao conectar ao banco de dados para gerar cobrança.")
            return

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            if is_sqlite:
                cur.execute('SELECT * FROM produtos WHERE id = ?', (produto_id,))
            else:
                cur.execute('SELECT * FROM produtos WHERE id = %s', (produto_id,))
            produto = cur.fetchone()

            if not produto:
                bot.send_message(chat_id, "Produto não encontrado.")
                return

            data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if is_sqlite:
                cur.execute("INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (?, ?, ?, ?, ?)",
                                (user_id, produto['id'], produto['preco'], 'pendente', data_venda))
                cur.execute("SELECT last_insert_rowid()")
                venda_id = cur.fetchone()[0]
            else:
                cur.execute("INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                                (user_id, produto['id'], produto['preco'], 'pendente', data_venda))
                venda_id = cur.fetchone()[0]

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
        print(f"ERRO GENERAR COBRANCA: Falha ao gerar cobrança/PIX: {e}")
        traceback.print_exc()
        bot.send_message(chat_id, "Ocorreu um erro interno ao gerar sua cobrança. Tente novamente.")
    finally:
        if conn: conn.close()


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
# 5. HANDLERS / BLUEPRINTS (Registro dos handlers do bot e blueprints Flask)
# ────────────────────────────────────────────────────────────────────
register_chamadas_handlers(bot, get_db_connection)
register_comunidades_handlers(bot, get_db_connection)

register_conteudos_handlers(bot, get_db_connection)

app.register_blueprint(create_comunidades_blueprint(get_db_connection))


# ────────────────────────────────────────────────────────────────────
# 6. MIDDLEWARE DE AUTENTICAÇÃO (para painel web)
# ────────────────────────────────────────────────────────────────────
@app.before_request
def require_login():
    """
    Middleware that checks if the user is logged in before accessing certain routes.
    Redirects to the login page if not authenticated.
    """
    if request.endpoint in ['login', 'static', 'telegram_webhook', 'health_check', 'webhook_mercado_pago', 'reset_admin_password_route', None]:
        return

    if not session.get('logged_in'):
        print(f"DEBUG AUTH: Unauthorized access to '{request.path}'. Redirecting to login.")
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))


# ────────────────────────────────────────────────────────────────────
# 7. ROTAS FLASK (Painel Administrativo e Webhooks)
# ────────────────────────────────────────────────────────────────────

@app.route('/health')
def health_check():
    print("DEBUG HEALTH: Requisição para /health.")
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
        bot.process_new_updates([update])
        return '!', 200
    else:
        return "Unsupported Media Type", 415

@app.route('/webhook/mercado-pago', methods=['GET', 'POST'])
def webhook_mercado_pago():
    """
    Endpoint para o webhook do Mercado Pago. Processa notificações de pagamento.
    Lida com testes GET e notificações POST de pagamentos aprovados.
    """
    print(f"DEBUG WEBHOOK MP: Recebida requisição para /webhook/mercado-pago. Method: {request.method}")

    if request.method == 'GET':
        print("DEBUG WEBHOOK MP: Requisição GET de teste do Mercado Pago recebida. Respondendo 200 OK.")
        return jsonify({'status': 'ok_test_webhook'}), 200

    notification = request.json
    print(f"DEBUG WEBHOOK MP: Corpo da notificação POST: {notification}")

    if notification and notification.get('type') == 'payment':
        print(f"DEBUG WEBHOOK MP: Notificação de pagamento detetada. ID: {notification.get('data', {}).get('id')}")
        payment_id = notification['data']['id']
        payment_info = pagamentos.verificar_status_pagamento(payment_id)

        print(f"DEBUG WEBHOOK MP: Estado do pagamento verificado: {payment_info.get('status') if payment_info else 'N/A'}")

        if payment_info and payment_info['status'] == 'approved':
            conn = None
            try:
                conn = get_db_connection()
                if conn is None:
                    print("ERRO WEBHOOK MP: Não foi possível obter conexão com a base de dados.")
                    return jsonify({'status': 'db_connection_error'}), 500

                is_sqlite = isinstance(conn, sqlite3.Connection)
                with conn:
                    cur = conn.cursor()
                    venda_id = payment_info.get('external_reference')
                    print(f"DEBUG WEBHOOK MP: Pagamento aprovado. Venda ID (external_reference): {venda_id}")

                    if not venda_id:
                        print("DEBUG WEBHOOK MP: external_reference não encontrado na notificação. Ignorando.")
                        return jsonify({'status': 'ignored_no_external_ref'}), 200

                    cur.execute('SELECT * FROM vendas WHERE id = %s AND status = %s' if not is_sqlite else 'SELECT * FROM vendas WHERE id = ? AND status = ?', (venda_id, 'pendente'))
                    venda = cur.fetchone()

                    if venda:
                        print(f"DEBUG WEBHOOK MP: Venda {venda_id} encontrada no DB com status 'pendente'.")
                        data_venda_dt = datetime.fromisoformat(venda['data_venda']) if isinstance(venda['data_venda'], str) else venda['data_venda']

                        if datetime.now() > data_venda_dt + timedelta(hours=1):
                            print(f"DEBUG WEBHOOK MP: Pagamento recebido para venda expirada (ID: {venda_id}). Ignorando entrega.")
                            cur.execute('UPDATE vendas SET status = %s WHERE id = %s' if not is_sqlite else 'UPDATE vendas SET status = ? WHERE id = ?', ('expirado', venda_id))
                            return jsonify({'status': 'expired_and_ignored'}), 200

                        payer_info = payment_info.get('payer', {})
                        payer_name = f"{payer_info.get('first_name', '')} {payer_info.get('last_name', '')}".strip()
                        payer_email = payer_info.get('email')
                        cur.execute('UPDATE vendas SET status = %s, payment_id = %s, payer_name = %s, payer_email = %s WHERE id = %s' if not is_sqlite else 'UPDATE vendas SET status = ?, payment_id = ?, payer_name = ?, payer_email = ? WHERE id = ?',
                                        ('aprovado', payment_id, payer_name, payer_email, venda_id))

                        cur.execute('SELECT * FROM produtos WHERE id = %s' if not is_sqlite else 'SELECT * FROM produtos WHERE id = ?', (venda['produto_id'],))
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
                    print("DEBUG LOGIN: Usuário ou senha incorretos.")
                    flash('Usuário ou senha inválidos.', 'danger')

        except Exception as e:
            print(f"ERRO LOGIN: Falha no processo de login: {e}")
            traceback.print_exc()
            flash('Erro no servidor ao tentar login.', 'error')
        finally:
            if conn: conn.close()

    print("DEBUG LOGIN: Renderizando login.html.")
    return render_template('login.html')


# ==============================================================================
# !! ROTA TEMPORÁRIA PARA RESET DE SENHA !!
# !! REMOVA ESTA ROTA APÓS O USO EM PRODUÇÃO !!
# ==============================================================================
@app.route('/reset-admin-password-now/muito-secreto-12345')
def reset_admin_password_route():
    USERNAME_TO_RESET = 'admin'
    NEW_PASSWORD = 'admin123' # CHANGE THIS IN PRODUCTION!

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
# ==============================================================================
# !! END OF TEMPORARY ROUTE !!
# ==============================================================================


@app.route('/logout')
def logout():
    """
    Route to log out the user from the admin panel.
    Clears the session and redirects to the login page.
    """
    print(f"DEBUG LOGOUT: Disconnecting user {session.get('username')}.")
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/')
def index():
    """
    Home page of the admin panel (dashboard).
    Displays statistics and recent sales.
    """
    print(f"DEBUG INDEX: Request for /. session.get('logged_in'): {session.get('logged_in')}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('login'))

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()

            # **CORREÇÃO:** Inicializa as variáveis com valores padrão aqui
            total_usuarios = 0
            total_produtos = 0
            total_vendas_aprovadas = 0
            receita_total = 0.0
            vendas_recentes = []
            chart_labels = []
            chart_data = []

            # Total users
            cur.execute('SELECT COUNT(id) AS count FROM users WHERE is_active = TRUE' if not is_sqlite else 'SELECT COUNT(id) AS count FROM users WHERE is_active = 1')
            total_usuarios_row = cur.fetchone()
            if total_usuarios_row and 'count' in total_usuarios_row and total_usuarios_row['count'] is not None:
                total_usuarios = total_usuarios_row['count']

            # Total products
            cur.execute('SELECT COUNT(id) AS count FROM produtos')
            total_produtos_row = cur.fetchone()
            if total_produtos_row and 'count' in total_produtos_row and total_produtos_row['count'] is not None:
                total_produtos = total_produtos_row['count']

            # Approved sales and total revenue
            cur.execute("SELECT COUNT(id) AS count, SUM(preco) AS sum FROM vendas WHERE status = %s" if not is_sqlite else "SELECT COUNT(id) AS count, SUM(preco) AS sum FROM vendas WHERE status = ?", ('aprovado',))
            vendas_data_row = cur.fetchone()
            
            # **CORREÇÃO:** Atribui os valores após a consulta, sobrescrevendo os padrões
            if vendas_data_row: # Verifica se a linha retornada não é None
                if 'count' in vendas_data_row and vendas_data_row['count'] is not None:
                    total_vendas_aprovadas = vendas_data_row['count']
                if 'sum' in vendas_data_row and vendas_data_row['sum'] is not None:
                    receita_total = float(vendas_data_row['sum'])
            
            print(f"DEBUG INDEX: total_vendas_aprovadas: {total_vendas_aprovadas}, receita_total: {receita_total}")

            # Recent sales (LIMIT 5)
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
            else: # PostgreSQL
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

            # Data for daily revenue chart (last 7 days)
            today_date = datetime.now().date()
            for i in range(6, -1, -1):
                day = today_date - timedelta(days=i)
                start_of_day = datetime.combine(day, time.min)
                end_of_day = datetime.combine(day, time.max)
                chart_labels.append(day.strftime('%d/%m'))

                if is_sqlite:
                    cur.execute(
                        "SELECT SUM(preco) AS sum FROM vendas WHERE status = ? AND data_venda BETWEEN ? AND ?",
                        ('aprovado', start_of_day.isoformat(), end_of_day.isoformat())
                    )
                else: # PostgreSQL
                    cur.execute(
                        "SELECT SUM(preco) AS sum FROM vendas WHERE status = %s AND data_venda BETWEEN %s AND %s",
                        ('aprovado', start_of_day, end_of_day)
                    )

                daily_revenue_row = cur.fetchone()
                daily_revenue = float(daily_revenue_row['sum']) if daily_revenue_row and 'sum' in daily_revenue_row and daily_revenue_row['sum'] is not None else 0
                chart_data.append(daily_revenue)

            print("DEBUG INDEX: Rendering index.html with dashboard data.")
            return render_template(
                'index.html',
                total_vendas=total_vendas_aprovadas,
                total_usuarios=total_usuarios,
                total_produtos=total_produtos,
                receita_total=receita_total,
                vendas_recentes=vendas_recentes,
                chart_labels=json.dumps(chart_labels),
                chart_data=json.dumps(chart_data),
                current_year=datetime.now().year
            )
    except Exception as e:
        print(f"ERRO INDEX: Falha ao renderizar o dashboard: {e}")
        traceback.print_exc()
        flash('Erro ao carregar o dashboard.', 'danger')
        return redirect(url_for('login'))
    finally:
        if conn:
            conn.close()


@app.route('/produtos', methods=['GET', 'POST'])
def produtos():
    """
    Route for managing products (add, list, edit, delete).
    Only accessible for logged-in users.
    """
    print("DEBUG PRODUTOS: Requisição para /produtos.")
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com a base de dados.', 'error')
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
                    flash('Preço inválido. Use um número (ex: 19.99).', 'danger')
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
    """
    Route to edit an existing product.
    Accessible only to logged-in users.
    """
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
                        flash('Preço deve ser um valor positivo.', 'danger')
                        return redirect(url_for('produtos', edit_id=produto_id, nome_val=nome, preco_val=preco_str, link_val=link))
                except ValueError:
                    flash('Preço inválido. Use um número.', 'danger')
                    return redirect(url_for('produtos', edit_id=produto_id, nome_val=nome, preco_val=preco_str, link_val=link))

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
    """
    Route to delete a product from the database.
    Accessible only to logged-in users.
    """
    print(f"DEBUG DELETAR_PRODUTO: Requisição para /deletar_produto/{produto_id}. Method: {request.method}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com a base de dados.', 'error')
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
    """
    Route to view and filter the sales list.
    Accessible only to logged-in users.
    """
    print("DEBUG VENDAS: Requisição para /vendas.")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com a base de dados.', 'error')
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
    """
    Route to get details of a specific sale via API (JSON).
    Accessible only to logged-in users.
    """
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
    print("DEBUG USUARIOS: Requisição para /usuarios.")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com a base de dados.', 'error')
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
            flash('Erro de conexão com a base de dados.', 'error')
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
        print(f"ERRO CONFIG MENSAGENS: Falha ao configurar mensagens: {e}")
        traceback.print_exc()
        flash('Erro ao carregar ou atualizar mensagens.', 'error')
        return redirect(url_for('index'))
    finally:
        if conn: conn.close()

@app.route('/add_scheduled_message', methods=['GET', 'POST'])
def add_scheduled_message():
    print(f"DEBUG ADD_SCHEDULED_MESSAGE: Requisição para /add_scheduled_message. Method: {request.method}")

    if not session.get('logged_in'):
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))

    conn = None
    users = []
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('scheduled_messages'))

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            if is_sqlite:
                cur.execute('SELECT id, username, first_name FROM users ORDER BY username ASC')
            else:
                cur.execute('SELECT id, username, first_name FROM users ORDER BY username ASC')
            users = cur.fetchall()

        if request.method == 'POST':
            message_text = request.form.get('message_text')
            target_chat_id = request.form.get('target_chat_id')
            image_url = request.form.get('image_url')
            schedule_time_str = request.form.get('schedule_time')

            if not message_text or not schedule_time_str:
                flash('Texto da mensagem e tempo de agendamento são obrigatórios!', 'danger')
                return render_template('add_scheduled_message.html', users=users, message_text=message_text, target_chat_id=target_chat_id, image_url=image_url, schedule_time_str=schedule_time_str)

            try:
                schedule_time = datetime.strptime(schedule_time_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash('Formato de data/hora inválido. Use AAAA-MM-DDTHH:MM.', 'danger')
                return render_template('add_scheduled_message.html', users=users, message_text=message_text, target_chat_id=target_chat_id, image_url=image_url, schedule_time_str=schedule_time_str)

            if schedule_time <= datetime.now():
                flash('A data e hora de agendamento devem ser no futuro.', 'danger')
                return render_template('add_scheduled_message.html', users=users, message_text=message_text, target_chat_id=target_chat_id, image_url=image_url, schedule_time_str=schedule_time_str)

            if target_chat_id == 'all_users':
                target_chat_id_db = None
            else:
                try:
                    target_chat_id_db = int(target_chat_id)
                except (ValueError, TypeError):
                    flash('ID do chat de destino inválido.', 'danger')
                    return render_template('add_scheduled_message.html', users=users, message_text=message_text, target_chat_id=target_chat_id, image_url=image_url, schedule_time_str=schedule_time_str)

            with conn:
                insert_cur = conn.cursor()
                if is_sqlite:
                    insert_cur.execute(
                        "INSERT INTO scheduled_messages (message_text, target_chat_id, image_url, schedule_time, status) VALUES (?, ?, ?, ?, ?)",
                        (message_text, target_chat_id_db, image_url if image_url else None, schedule_time, 'pending')
                    )
                else:
                    insert_cur.execute(
                        "INSERT INTO scheduled_messages (message_text, target_chat_id, image_url, schedule_time, status) VALUES (%s, %s, %s, %s, %s)",
                        (message_text, target_chat_id_db, image_url if image_url else None, schedule_time, 'pending')
                    )
                flash('Mensagem agendada com sucesso!', 'success')
                return redirect(url_for('scheduled_messages'))
        # GET request for the form
        return render_template('add_scheduled_message.html', users=users)

    except Exception as e:
        print(f"ERRO ADD_SCHEDULED_MESSAGE (GET/POST common): Falha ao carregar/processar formulário: {e}")
        traceback.print_exc()
        flash('Erro ao carregar o formulário de agendamento.', 'danger')
        return redirect(url_for('scheduled_messages'))
    finally:
        if conn: conn.close()


@app.route('/edit_scheduled_message/<int:message_id>', methods=['GET', 'POST'])
def edit_scheduled_message(message_id):
    print(f"DEBUG EDIT_SCHEDULED_MESSAGE: Requisição para /edit_scheduled_message/{message_id}. Method: {request.method}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('scheduled_messages', error='edit_db_connection_error'))

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            if is_sqlite:
                cur.execute('SELECT * FROM scheduled_messages WHERE id = ?', (message_id,))
            else:
                cur.execute('SELECT * FROM scheduled_messages WHERE id = %s', (message_id,))
            message = cur.fetchone()

            if not message:
                flash('Mensagem agendada não encontrada.', 'danger')
                return redirect(url_for('scheduled_messages'))

            if is_sqlite:
                cur.execute('SELECT id, username, first_name FROM users ORDER BY username ASC')
            else:
                cur.execute('SELECT id, username, first_name FROM users ORDER BY username ASC')
            users = cur.fetchall()

            if request.method == 'POST':
                message_text = request.form.get('message_text')
                target_chat_id = request.form.get('target_chat_id')
                image_url = request.form.get('image_url')
                schedule_time_str = request.form.get('schedule_time')
                status = request.form.get('status')

                if not message_text or not schedule_time_str:
                    flash('Texto da mensagem e tempo de agendamento são obrigatórios!', 'danger')
                    return render_template('edit_scheduled_message.html', message=message, users=users, message_text_val=message_text, target_chat_id_val=target_chat_id, image_url_val=image_url, schedule_time_str_val=schedule_time_str)

                try:
                    schedule_time = datetime.strptime(schedule_time_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    flash('Formato de data/hora inválido. Use AAAA-MM-DDTHH:MM.', 'danger')
                    return render_template('edit_scheduled_message.html', message=message, users=users, message_text_val=message_text, target_chat_id_val=target_chat_id, image_url_val=image_url, schedule_time_str_val=schedule_time_str)

                if target_chat_id == 'all_users':
                    target_chat_id_db = None
                else:
                    try:
                        target_chat_id_db = int(target_chat_id)
                    except (ValueError, TypeError):
                        flash('ID do chat de destino inválido.', 'danger')
                        return render_template('edit_scheduled_message.html', message=message, users=users, message_text_val=message_text, target_chat_id_val=target_chat_id, image_url_val=image_url, schedule_time_str_val=schedule_time_str)

                if is_sqlite:
                    cur.execute(
                        "UPDATE scheduled_messages SET message_text = ?, target_chat_id = ?, image_url = ?, schedule_time = ?, status = ? WHERE id = ?",
                        (message_text, target_chat_id_db, image_url if image_url else None, schedule_time, status, message_id)
                    )
                else:
                    cur.execute(
                        "UPDATE scheduled_messages SET message_text = %s, target_chat_id = %s, image_url = %s, schedule_time = %s, status = %s WHERE id = %s",
                        (message_text, target_chat_id_db, image_url if image_url else None, schedule_time, status, message_id)
                    )
                print(f"DEBUG EDIT_SCHEDULED_MESSAGE: Mensagem agendada ID {message_id} atualizada com sucesso.")
                flash('Mensagem agendada atualizada com sucesso!', 'success')
                return redirect(url_for('scheduled_messages'))

            # For GET request, format the schedule_time for the form
            message['schedule_time_formatted'] = message['schedule_time'].strftime('%Y-%m-%dT%H:%M') if message['schedule_time'] else ''
            message['target_chat_id_selected'] = message['target_chat_id'] if message['target_chat_id'] is not None else 'all_users'
            return render_template('edit_scheduled_message.html', message=message, users=users)

    except Exception as e:
        print(f"ERRO EDIT_SCHEDULED_MESSAGE: Falha ao editar mensagem agendada: {e}")
        traceback.print_exc()
        flash('Erro ao editar mensagem agendada.', 'danger')
        return redirect(url_for('scheduled_messages'))
    finally:
        if conn: conn.close()

@app.route('/delete_scheduled_message/<int:message_id>', methods=['POST'])
def delete_scheduled_message(message_id):
    print(f"DEBUG DELETE_SCHEDULED_MESSAGE: Requisição para /delete_scheduled_message/{message_id}. Method: {request.method}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('scheduled_messages', error='delete_db_connection_error'))

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            if is_sqlite:
                cur.execute('DELETE FROM scheduled_messages WHERE id = ?', (message_id,))
            else:
                cur.execute('DELETE FROM scheduled_messages WHERE id = %s', (message_id,))
            print(f"DEBUG DELETE_SCHEDULE_MESSAGE: Mensagem agendada ID {message_id} deletada com sucesso.")
            flash('Mensagem agendada deletada com sucesso!', 'success')
            return redirect(url_for('scheduled_messages'))
    except Exception as e:
        print(f"ERRO DELETE_SCHEDULE_MESSAGE: Falha ao deletar mensagem agendada: {e}")
        traceback.print_exc()
        flash('Erro ao deletar mensagem agendada.', 'danger')
        return redirect(url_for('scheduled_messages'))
    finally:
        if conn: conn.close()

@app.route('/send_broadcast', methods=['GET', 'POST'])
def send_broadcast():
    print(f"DEBUG SEND_BROADCAST: Requisição para /send_broadcast. Method: {request.method}")

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
                cur.execute('SELECT id, username, first_name FROM users WHERE is_active = 1 ORDER BY username ASC')
            else:
                cur.execute('SELECT id, username, first_name FROM users WHERE is_active = TRUE ORDER BY username ASC')
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
                                    finally:
                                        if temp_conn_update: temp_conn_update.close()
                            failed_count += 1
                        except Exception as e:
                            print(f"ERRO UNEXPECTED BROADCAST to {user_id}: {e}")
                            traceback.print_exc()
                            failed_count += 1

                flash(f'Broadcast enviado com sucesso para {sent_count} usuários. Falha em {failed_count} usuários.', 'success')
                return redirect(url_for('index'))
            except Exception as e:
                print(f"ERRO SEND_BROADCAST (send logic): {e}")
                traceback.print_exc()
                flash('Ocorreu um erro ao tentar enviar o broadcast.', 'danger')
                return render_template('send_broadcast.html', active_users=active_users, message_text_val=message_text, image_url_val=image_url)
            finally:
                if cur_conn_send: cur_conn_send.close()

        return render_template('send_broadcast.html', active_users=active_users)

    except Exception as e:
        print(f"ERRO SEND_BROADCAST (GET): Falha ao carregar usuários para o formulário: {e}")
        traceback.print_exc()
        flash('Erro ao carregar a página de broadcast.', 'danger')
        return redirect(url_for('index'))
    finally:
        if conn: conn.close()

@app.route('/config_messages', methods=['GET', 'POST'])
def config_messages():
    print(f"DEBUG CONFIG_MESSAGES: Requisição para /config_messages. Method: {request.method}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('index'))

        is_sqlite = isinstance(conn, sqlite3.Connection)
        with conn:
            cur = conn.cursor()
            if request.method == 'POST':
                welcome_bot_message = request.form.get('welcome_message_bot')
                welcome_community_message = request.form.get('welcome_message_community')

                if welcome_bot_message is not None:
                    if is_sqlite:
                        cur.execute(
                            "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value;",
                            ('welcome_message_bot', welcome_bot_message)
                        )
                    else:
                        cur.execute(
                            "INSERT INTO config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;",
                            ('welcome_message_bot', welcome_bot_message)
                        )
                if welcome_community_message is not None:
                    if is_sqlite:
                        cur.execute(
                            "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value;",
                            ('welcome_message_community', welcome_community_message)
                        )
                    else:
                        cur.execute(
                            "INSERT INTO config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;",
                            ('welcome_message_community', welcome_community_message)
                        )
                flash('Configurações de mensagens atualizadas com sucesso!', 'success')
                return redirect(url_for('config_messages'))

            # For GET request, fetch current configurations
            if is_sqlite:
                cur.execute("SELECT key, value FROM config WHERE key IN (?, ?)", ('welcome_message_bot', 'welcome_message_community'))
            else:
                cur.execute("SELECT key, value FROM config WHERE key IN (%s, %s)", ('welcome_message_bot', 'welcome_message_community'))
            configs_raw = cur.fetchall()
            configs = {row['key']: row['value'] for row in configs_raw}

            welcome_message_bot = configs.get('welcome_message_bot', 'Olá, {first_name}! Bem-vindo(a) ao bot!')
            welcome_message_community = configs.get('welcome_message_community', 'Bem-vindo(a) à nossa comunidade, {first_name}!')

            return render_template(
                'config_messages.html',
                welcome_message_bot=welcome_message_bot,
                welcome_message_community=welcome_message_community
            )

    except Exception as e:
        print(f"ERRO CONFIG_MESSAGES: Falha ao carregar/salvar configurações de mensagens: {e}")
        traceback.print_exc()
        flash('Erro ao carregar/salvar configurações de mensagens.', 'danger')
        return redirect(url_for('index'))
    finally:
        if conn: conn.close()

# ────────────────────────────────────────────────────────────────────
# 8. WORKER de mensagens agendadas
# ────────────────────────────────────────────────────────────────────
def scheduled_message_worker():
    """
    Worker that checks and sends scheduled messages to users.
    It runs in a separate thread or as a worker process.
    """
    print("DEBUG WORKER: Initiated...")
    while True:
        conn = None
        try:
            conn = get_db_connection()
            if conn is None:
                print("ERRO WORKER: Could not get database connection. Retrying in 30s...")
                time_module.sleep(30)
                continue

            is_sqlite = isinstance(conn, sqlite3.Connection)
            with conn:
                cur = conn.cursor()
                if is_sqlite:
                    cur.execute(
                        "SELECT * FROM scheduled_messages WHERE status='pending' AND schedule_time<=datetime('now') ORDER BY schedule_time"
                    )
                else:
                    cur.execute(
                        "SELECT * FROM scheduled_messages WHERE status='pending' AND schedule_time<=NOW() AT TIME ZONE 'UTC' ORDER BY schedule_time"
                    )
                rows = cur.fetchall()

                for row in rows:
                    targets = []
                    if row["target_chat_id"]:
                        targets.append(row["target_chat_id"])
                    else:
                        if is_sqlite:
                            cur.execute("SELECT id FROM users WHERE is_active=1")
                        else:
                            cur.execute("SELECT id FROM users WHERE is_active=TRUE")
                        targets = [u["id"] for u in cur.fetchall()]

                    delivered_to_any_user = False
                    for chat_id in targets:
                        try:
                            if row["image_url"]:
                                bot.send_photo(chat_id, row["image_url"], caption=row["message_text"], parse_mode="Markdown")
                            else:
                                bot.send_message(chat_id, row["message_text"], parse_mode="Markdown")
                            delivered_to_any_user = True
                            print(f"DEBUG WORKER: Message {row['id']} sent to {chat_id}.")
                        except telebot.apihelper.ApiTelegramException as e:
                            print(f"ERRO Telegram API for chat_id {chat_id}: {e}")
                            if "blocked" in str(e).lower() or "not found" in str(e).lower() or "deactivated" in str(e).lower():
                                print(f"AVISO: User {chat_id} blocked/not found. Deactivating...")
                                temp_conn_for_user_update = get_db_connection()
                                if temp_conn_for_user_update:
                                    temp_is_sqlite_for_user_update = isinstance(temp_conn_for_user_update, sqlite3.Connection)
                                    try:
                                        with temp_conn_for_user_update:
                                            temp_cur_user_update = temp_conn_for_user_update.cursor()
                                            if temp_is_sqlite_for_user_update:
                                                temp_cur_user_update.execute("UPDATE users SET is_active=0 WHERE id=?", (chat_id,))
                                            else:
                                                temp_cur_user_update.execute("UPDATE users SET is_active=FALSE WHERE id=%s", (chat_id,))
                                    except Exception as db_e:
                                        print(f"ERRO updating user {chat_id} status during worker run: {db_e}")
                                    finally:
                                        if temp_conn_for_user_update: temp_conn_for_user_update.close()
                            failed_count += 1
                        except Exception as e:
                            print(f"ERRO WORKER: Failed to send message {row['id']} to {chat_id}: {e}")
                            traceback.print_exc()

                    status_to_update = "sent" if delivered_to_any_user else "failed"
                    if is_sqlite:
                        cur.execute(
                            "UPDATE scheduled_messages SET status=?, sent_at=? WHERE id=?",
                            (status_to_update, datetime.now().isoformat(), row["id"]),
                        )
                    else:
                        cur.execute(
                            "UPDATE scheduled_messages SET status=%s, sent_at=NOW() AT TIME ZONE 'UTC' WHERE id=%s",
                            (status_to_update, row["id"]),
                        )

        except Exception as e:
            print(f"ERRO WORKER Main Loop: {e}")
            traceback.print_exc()
        finally:
            if conn:
                conn.close()

        time_module.sleep(30)

# ────────────────────────────────────────────────────────────────────
# 9. FINAL INITIALIZATION AND EXECUTION
# ────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """
    Handler para o comando /start. Regista o utilizador e envia uma mensagem de boas-vindas.
    """
    get_or_register_user(message.from_user)

    # Fetch welcome message from config
    conn = None
    welcome_message_text = "Olá, {first_name}! Bem-vindo(a) ao bot!"
    try:
        conn = get_db_connection()
        if conn:
            is_sqlite = isinstance(conn, sqlite3.Connection)
            with conn:
                cur = conn.cursor()
                if is_sqlite:
                    cur.execute("SELECT value FROM config WHERE key = ?", ('welcome_message_bot',))
                else:
                    cur.execute("SELECT value FROM config WHERE key = %s", ('welcome_message_bot',))
                row = cur.fetchone()
                if row:
                    welcome_message_text = row['value']
    except Exception as e:
        print(f"ERRO ao carregar mensagem de boas-vindas: {e}")
        traceback.print_exc()
    finally:
        if conn: conn.close()

    formatted_message = welcome_message_text.format(
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name or '',
        username=message.from_user.username or 'usuário'
    )
    bot.reply_to(message, formatted_message, reply_markup=menu_principal())

# Condition for execution in production environment (Render) or locally
if __name__ != '__main__':
    # This part is executed when the application is imported by a WSGI server (e.g., gunicorn on Render)
    print("DEBUG: Running in production mode (gunicorn/Render).")
    try:
        init_db() # Initialize the database (create tables if they don't exist)

        # Initialize Mercado Pago SDK
        pagamentos.init_mercadopago_sdk()

        # Configure Telegram webhook
        if API_TOKEN and BASE_URL:
            webhook_url = f"{BASE_URL}/{API_TOKEN}"
            bot.set_webhook(url=webhook_url)
            print(f"DEBUG: Telegram webhook configured for: {webhook_url}")
        else:
            print("ERRO: API_TOKEN or BASE_URL environment variables not defined for webhook. Bot may not receive updates.")

        print("DEBUG: Flask application ready. Scheduled worker not started embedded.")
    except Exception as e:
        print(f"ERRO ON SERVER INITIALIZATION: {e}")
        traceback.print_exc()

else:
    # This part is executed when the script is run directly (local development)
    print("DEBUG: Running in local development mode (python app.py).")
    init_db() # Initialize the database (create tables if they don't exist)

    # Initialize Mercado Pago SDK (for local testing)
    pagamentos.init_mercadopago_sdk()

    worker_thread = Thread(target=scheduled_message_worker)
    worker_thread.daemon = True
    worker_thread.start()
    print("DEBUG: Scheduled message worker started in background (local mode).")

    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))