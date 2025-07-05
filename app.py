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
# Importa inline_ver_produtos_keyboard para o botão inline
from bot.utils.keyboards import confirm_18_keyboard, menu_principal, inline_ver_produtos_keyboard 
from bot.handlers.chamadas import register_chamadas_handlers
from bot.handlers.comunidades import register_comunidades_handlers
from bot.handlers.conteudos import register_conteudos_handlers
from bot.handlers.produtos import register_produtos_handlers 
from web.routes.comunidades import comunidades_bp


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
    print("ERRO: A variável de ambiente 'API_TOKEN' não está definida. O bot não pode funcionar.")
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

                # --- CORREÇÃO AQUI: FORÇAR UMA ÚNICA LINHA NO QR_CODE_DATA E USAR HTML ---
                qr_code_data_clean = qr_code_data.replace('\n', '').strip()
                
                caption_text = (
                    f"✅ PIX gerado para *{produto['nome']}*!\n\n"
                    "Escaneie o QR Code acima ou copie o código completo na próxima mensagem."
                )
                bot.send_photo(chat_id, qr_code_image, caption=caption_text, parse_mode='Markdown')

                # Usar <pre> tag com HTML parse_mode para melhor copiabilidade em blocos de código.
                # O botão inline permite "Copiar texto" mais facilmente em muitos clientes.
                markup_copy = types.InlineKeyboardMarkup()
                btn_copy = types.InlineKeyboardButton("📋 Copiar Código PIX", callback_data="copy_pix")
                markup_copy.add(btn_copy)

                # Enviei a mensagem com o código PIX usando HTML <pre> para melhor copiabilidade
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
# ADICIONAR UM HANDLER PARA O BOTÃO 'COPIAR PIX' (opcional, para feedback)
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
# IMPORTANTE: Definir antes das rotas que o utilizam
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
    print(f"DEBUG WEBHOOK MP: Recebida requisição para /webhook/mercado-pago. Method: {request.method}")

    if request.method == 'GET':
        print(f"DEBUG WEBHOOK MP: Requisição GET de teste do Mercado Pago recebida. Respondendo 200 OK.")
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
                    print(f"ERRO WEBHOOK MP: Não foi possível obter conexão com a base de dados.")
                    return jsonify({'status': 'db_connection_error'}), 500

                is_sqlite = isinstance(conn, sqlite3.Connection)
                with conn:
                    cur = conn.cursor()
                    venda_id = payment_info.get('external_reference')
                    print(f"DEBUG WEBHOOK MP: Pagamento aprovado. Venda ID (external_reference): {venda_id}")

                    if not venda_id:
                        print(f"DEBUG WEBHOOK MP: external_reference não encontrado na notificação. Ignorando.")
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

    print(f"DEBUG WEBHOOK MP: Notificação ignorada (não é tipo 'payment' ou JSON inválvido).")
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
# =================================────────────────────────────────────
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
            # Fallback para mensagem padrão se DB não disponível
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
    
    # Comportamento: Mensagem de boas-vindas COM botão inline "Melhores Vips e Novinhas"
    bot.reply_to(message, formatted_message, reply_markup=inline_ver_produtos_keyboard())

    # NÃO chamar mostrar_produtos_bot_func() aqui se a intenção é que o botão inline faça isso.
    # O clique no botão inline acionará o `handle_ver_produtos_inline` que chamará `mostrar_produtos_bot`.

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

        # REGISTRAR HANDLERS (COM A CORREÇÃO DE IMPORTAÇÃO CIRCULAR PARA PRODUTOS)
        register_chamadas_handlers(bot, get_db_connection)
        register_comunidades_handlers(bot, get_db_connection)
        register_conteudos_handlers(bot, get_db_connection)
        
        # Passando 'generar_cobranca' como argumento.
        # A função mostrar_produtos_bot NÃO é mais retornada para o escopo global do app.py,
        # pois ela será chamada pelo handler do botão inline em bot/handlers/produtos.py.
        register_produtos_handlers(bot, get_db_connection, generar_cobranca) 
        
        # REGISTRAR BLUEPRINT DE COMUNIDADES (EXISTENTE)
        app.register_blueprint(comunidades_bp, url_prefix='/') 

    except Exception as e:
        print(f"ERRO NA INICIALIZAÇÃO DO SERVIDOR: {e}")
        traceback.print_exc()