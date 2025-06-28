import os
import requests
import telebot
from telebot import types
import traceback
import time as time_module
from datetime import datetime, timedelta, time
from threading import Thread

# Importações Flask e Werkzeug (para segurança e hashing de senha)
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from werkzeug.security import check_password_hash, generate_password_hash

# Carrega variáveis de ambiente do arquivo .env (apenas para desenvolvimento local)
from dotenv import load_dotenv
load_dotenv()

# IMPORTAÇÃO CORRETA DAS FUNÇÕES DO BANCO DE DADOS
# Agora importamos diretamente de database.database e database.db_init
from database.database import get_db_connection
from database.db_init import init_db

# Importa o módulo de pagamentos do Mercado Pago
import pagamentos

# Importações de handlers e blueprints (seus módulos existentes do bot e web)
from bot.utils.keyboards import confirm_18_keyboard, menu_principal
from bot.handlers.chamadas import register_chamadas_handlers
from bot.handlers.comunidades import register_comunidades_handlers
from bot.handlers.ofertas import register_ofertas_handlers
from bot.handlers.conteudos import register_conteudos_handlers
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


if not API_TOKEN:
    print("ERRO: A variável de ambiente 'API_TOKEN' não está definida. O bot não pode funcionar.")
    # raise RuntimeError("API_TOKEN não configurado.") # Descomente se quiser deploy falhe sem token


# ────────────────────────────────────────────────────────────────────
# 2. FLASK & TELEBOT (Inicialização dos objetos principais)
# ────────────────────────────────────────────────────────────────────
# ATENÇÃO: template_folder APONTA PARA A PASTA 'templates' NA RAIZ DO PROJETO
app = Flask(__name__, template_folder="templates", static_folder="web/static")
app.secret_key = FLASK_SECRET_KEY
bot = telebot.TeleBot(API_TOKEN, threaded=False, parse_mode="Markdown")

# ────────────────────────────────────────────────────────────────────
# 3. FUNÇÕES DE UTILIDADE (Bot e Usuário) - Usam get_db_connection
#    Estas funções chamam get_db_connection do módulo database.database
# ────────────────────────────────────────────────────────────────────

def get_or_register_user(user: types.User):
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            print("ERRO DB: Não foi possível obter conexão para get_or_register_user.")
            return 
            
        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
            if is_sqlite:
                cur.execute("SELECT * FROM users WHERE id = ?", (user.id,))
            else:
                cur.execute("SELECT * FROM users WHERE id = %s", (user.id,))
            
            db_user = cur.fetchone()
            if db_user is None:
                data_registro = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if is_sqlite:
                    cur.execute("INSERT INTO users (id, username, first_name, last_name, data_registro, is_active) VALUES (?, ?, ?, ?, ?, ?)",
                                 (user.id, user.username, user.first_name, user.last_name, data_registro, True))
                else:
                    cur.execute("INSERT INTO users (id, username, first_name, last_name, data_registro, is_active) VALUES (%s, %s, %s, %s, %s, %s)",
                                 (user.id, user.username, user.first_name, user.last_name, data_registro, True))
                conn.commit()
            else:
                if not db_user['is_active']:
                    if is_sqlite:
                        cur.execute("UPDATE users SET is_active = ? WHERE id = ?", (True, user.id,))
                    else:
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
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print(f"DEBUG: Mensagem de entrega para {user_id} enviada com sucesso.")
    except requests.exceptions.RequestException as e:
        print(f"ERRO: Falha ao enviar mensagem de entrega para {user_id}: {e}")
        traceback.print_exc()

def mostrar_produtos_bot(chat_id): # Renomeada para evitar conflito com rota Flask
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            bot.send_message(chat_id, "Ocorreu um erro interno ao conectar ao banco de dados.")
            return
            
        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
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
            
        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
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
                cur.execute("INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (?, ?, ?, ?, ?) RETURNING id",
                             (user_id, produto['id'], produto['preco'], 'pendente', data_venda))
            else:
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
        print(f"ERRO GENERAR COBRANCA: Falha ao gerar cobrança/PIX: {e}")
        traceback.print_exc()
        bot.send_message(chat_id, "Ocorreu um erro interno ao gerar sua cobrança. Tente novamente.")
        if conn and not conn.closed: conn.rollback()
    finally:
        if conn: conn.close()


# ────────────────────────────────────────────────────────────────────
# 4. WORKER de mensagens agendadas
# ────────────────────────────────────────────────────────────────────
def scheduled_message_worker():
    print("DEBUG WORKER: iniciado …")
    while True:
        conn = None
        try:
            conn = get_db_connection()
            if conn is None:
                print("ERRO WORKER: Não foi possível obter conexão com o banco de dados. Tentando novamente em 30s...")
                time_module.sleep(30)
                continue

            is_sqlite = 'sqlite3' in conn.__class__.__module__
            with conn.cursor() as cur:
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
                    
                    delivered = False
                    for chat_id in targets:
                        try:
                            if row["image_url"]:
                                bot.send_photo(chat_id, row["image_url"], caption=row["message_text"], parse_mode="Markdown")
                            else:
                                bot.send_message(chat_id, row["message_text"], parse_mode="Markdown")
                            delivered = True
                        except telebot.apihelper.ApiTelegramException as e:
                            print(f"ERRO envio Telegram para {chat_id}:", e)
                            if "blocked" in str(e).lower() or "not found" in str(e).lower() or "deactivated" in str(e).lower():
                                print(f"AVISO: Usuário {chat_id} bloqueou/não encontrado. Inativando...")
                                temp_conn = None
                                try:
                                    temp_conn = get_db_connection()
                                    if temp_conn:
                                        temp_is_sqlite = 'sqlite3' in temp_conn.__class__.__module__
                                        with temp_conn.cursor() as temp_cur:
                                            if temp_is_sqlite:
                                                temp_cur.execute("UPDATE users SET is_active=0 WHERE id=?", (chat_id,))
                                            else:
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
                    status = "sent" if delivered else "failed"
                    if is_sqlite:
                        cur.execute(
                            "UPDATE scheduled_messages SET status=?, sent_at=CURRENT_TIMESTAMP WHERE id=?",
                            (status, row["id"]),
                        )
                    else:
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
        time_module.sleep(60)

# ────────────────────────────────────────────────────────────────────
# 5. HANDLERS / BLUEPRINTS (Registro dos handlers do bot e blueprints Flask)
# ────────────────────────────────────────────────────────────────────
# Essas linhas precisam estar fora da função main para serem registradas na inicialização
register_chamadas_handlers(bot, get_db_connection)
register_comunidades_handlers(bot, get_db_connection)
register_ofertas_handlers(bot, get_db_connection)
register_conteudos_handlers(bot, get_db_connection)

app.register_blueprint(create_comunidades_blueprint(get_db_connection))

# ────────────────────────────────────────────────────────────────────
# 6. ROTAS FLASK (Ajustadas para o fluxo "tudo em produtos.html")
# ────────────────────────────────────────────────────────────────────

@app.route('/health')
def health_check():
    print("DEBUG HEALTH: Requisição para /health.")
    return "OK", 200

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
                if conn is None:
                    print("ERRO WEBHOOK MP: Não foi possível obter conexão com o banco de dados para processar pagamento.")
                    return jsonify({'status': 'db_connection_error'}), 500

                is_sqlite = 'sqlite3' in conn.__class__.__module__
                with conn.cursor() as cur:
                    venda_id = payment_info.get('external_reference')
                    print(f"DEBUG WEBHOOK MP: Pagamento aprovado. Venda ID (external_reference): {venda_id}")

                    if not venda_id:
                        print("DEBUG WEBHOOK MP: external_reference não encontrado na notificação. Ignorando.")
                        return jsonify({'status': 'ignored_no_external_ref'}), 200

                    if is_sqlite:
                         cur.execute('SELECT * FROM vendas WHERE id = ? AND status = ?', (venda_id, 'pendente'))
                    else:
                         cur.execute('SELECT * FROM vendas WHERE id = %s AND status = %s', (venda_id, 'pendente'))
                    venda = cur.fetchone()

                    if venda:
                        print(f"DEBUG WEBHOOK MP: Venda {venda_id} encontrada no DB com status 'pendente'.")
                        data_venda_dt = venda['data_venda'] if isinstance(venda['data_venda'], datetime) else datetime.strptime(str(venda['data_venda']), '%Y-%m-%d %H:%M:%S.%f')
                        
                        if datetime.now() > data_venda_dt + timedelta(hours=1):
                            print(f"DEBUG WEBHOOK MP: Pagamento recebido para venda expirada (ID: {venda_id}). Ignorando entrega.")
                            if is_sqlite:
                                cur.execute('UPDATE vendas SET status = ? WHERE id = ?', ('expirado', venda_id))
                            else:
                                cur.execute('UPDATE vendas SET status = %s WHERE id = %s', ('expirado', venda_id))
                            conn.commit()
                            return jsonify({'status': 'expired_and_ignored'}), 200

                        payer_info = payment_info.get('payer', {})
                        payer_name = f"{payer_info.get('first_name', '')} {payer_info.get('last_name', '')}".strip()
                        payer_email = payer_info.get('email')
                        if is_sqlite:
                             cur.execute('UPDATE vendas SET status = ?, payment_id = ?, payer_name = ?, payer_email = ? WHERE id = ?',
                                         ('aprovado', payment_id, payer_name, payer_email, venda_id))
                        else:
                             cur.execute('UPDATE vendas SET status = %s, payment_id = %s, payer_name = %s, payer_email = %s WHERE id = %s',
                                         ('aprovado', payment_id, payer_name, payer_email, venda_id))
                        conn.commit()
                        if is_sqlite:
                            cur.execute('SELECT * FROM produtos WHERE id = ?', (venda['produto_id'],))
                        else:
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

    print("DEBUG WEBHOOK MP" Notificação ignorada (não é tipo 'payment' ou JSON Inválido).")
    return jsonify({'status': 'ignorad_general'}), 200

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
            if conn is None:
                flash('Erro de conexão com o banco de dados.', 'danger')
                return render_template('login.html')

            is_sqlite = 'sqlite3' in conn.__class__.__module__
            with conn.cursor() as cur:
                if is_sqlite:
                    cur.execute('SELECT * FROM admin WHERE username = ?', (username,))
                else:
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
        if conn is None:
            return f"<h1>Erro</h1><p>Erro de conexão com o banco de dados.</p>", 500

        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
            if is_sqlite:
                cur.execute("UPDATE admin SET password_hash = ? WHERE username = ?", (hashed_password, USERNAME_TO_RESET))
            else:
                cur.execute("UPDATE admin SET password_hash = %s WHERE username = %s", (hashed_password, USERNAME_TO_RESET))
            
            if cur.rowcount == 0:
                print(f"DEBUG RESET: Usuário '{USERNAME_TO_RESET}' não encontrado para atualizar. Tentando criar...")
                if is_sqlite:
                    cur.execute("INSERT INTO admin (username, password_hash) VALUES (?, ?)", (USERNAME_TO_RESET, hashed_password))
                else:
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
        if conn and not conn.closed: conn.rollback()
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
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('login'))

        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
            if is_sqlite:
                cur.execute('SELECT COUNT(id) FROM users WHERE is_active = 1')
            else:
                cur.execute('SELECT COUNT(id) FROM users WHERE is_active = TRUE')
            total_usuarios_row = cur.fetchone()
            print(f"DEBUG INDEX: Resultado fetchone COUNT(users): {total_usuarios_row}")
            total_usuarios = total_usuarios_row['count'] if total_usuarios_row and 'count' in total_usuarios_row and total_usuarios_row['count'] is not None else 0

            cur.execute('SELECT COUNT(id) FROM produtos')
            total_produtos_row = cur.fetchone()
            print(f"DEBUG INDEX: Resultado fetchone COUNT(produtos): {total_produtos_row}")
            total_produtos = total_produtos_row['count'] if total_produtos_row and 'count' in total_produtos_row and total_produtos_row['count'] is not None else 0

            if is_sqlite:
                cur.execute("SELECT COUNT(id) AS count, SUM(preco) AS sum FROM vendas WHERE status = ?", ('aprovado',))
            else:
                cur.execute("SELECT COUNT(id) AS count, SUM(preco) AS sum FROM vendas WHERE status = %s", ('aprovado',))
            vendas_data_row = cur.fetchone()
            print(f"DEBUG INDEX: Resultado fetchone COUNT/SUM(vendas): {vendas_data_row}")
            total_vendas_aprovadas = vendas_data_row['count'] if vendas_data_row and 'count' in vendas_data_row and vendas_data_row['count'] is not None else 0
            receita_total = vendas_data_row['sum'] if vendas_data_row and 'sum' in vendas_data_row and vendas_data_row['sum'] is not None else 0.0
            print(f"DEBUG INDEX: total_vendas_aprovadas: {total_vendas_aprovadas}, receita_total: {receceita_total}")

            cur.execute("SELECT v.id, u.username, u.first_name, p.nome, v.preco, v.data_venda, p.id as produto_id, CASE WHEN v.status = 'aprovado' THEN 'aprovado' WHEN v.status = 'pendente' AND EXTRACT(EPOCH FROM (NOW() - v.data_venda)) > 3600 THEN 'expirado' ELSE v.status END AS status FROM vendas v JOIN users u ON v.user_id = u.id JOIN produtos p ON v.produto_id = p.id ORDER BY v.id DESC LIMIT 5")
            vendas_recentes = cur.fetchall()

            chart_labels, chart_data = [], []
            today = datetime.now()
            for i in range(6, -1, -1):
                day = today - timedelta(days=i)
                start_of_day, end_of_day = datetime.combine(day.date(), time.min), datetime.combine(day.date(), time.max)
                chart_labels.append(day.strftime('%d/%m'))
                
                if is_sqlite:
                    cur.execute("SELECT SUM(preco) AS sum FROM vendas WHERE status = ? AND data_venda BETWEEN ? AND ?", ('aprovado', start_of_day, end_of_day))
                else:
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
    print("DEBUG PRODUTOS: Requisição para /produtos.")

    if not session.get('logged_in'):
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('index'))

        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
            if is_sqlite:
                cur.execute('SELECT * FROM produtos ORDER BY nome ASC')
            else:
                cur.execute('SELECT * FROM produtos ORDER BY nome ASC')
            produtos_lista = cur.fetchall()
            print(f"DEBUG PRODUTOS: {len(produtos_lista)} produtos encontrados.")

        return render_template('produtos.html', produtos=produtos_lista)

    except Exception as e:
        print(f"ERRO PRODUTOS: Falha ao carregar produtos para o dashboard: {e}")
        traceback.print_exc()
        flash('Erro ao carregar os produtos.', 'danger')
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()

@app.route('/adicionar_produto', methods=['GET', 'POST'])
def adicionar_produto():
    print(f"DEBUG ADICIONAR_PRODUTO: Requisição para /adicionar_produto. Method: {request.method}")

    if not session.get('logged_in'):
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        nome = request.form.get('nome')
        preco = request.form.get('preco')
        link = request.form.get('link')

        if not nome or not preco or not link:
            flash('Todos os campos são obrigatórios!', 'danger')
            return redirect(url_for('produtos', error='add_fields_missing',
                                    nome_val=nome, preco_val=preco, link_val=link))
        try:
            preco = float(preco)
            if preco <= 0:
                flash('Preço deve ser um valor positivo.', 'danger')
                return redirect(url_for('produtos', error='add_invalid_price',
                                        nome_val=nome, preco_val=preco, link_val=link))
        except ValueError:
            flash('Preço inválido. Use um número.', 'danger')
            return redirect(url_for('produtos', error='add_invalid_price_type',
                                    nome_val=nome, preco_val=preco, link_val=link))

        conn = None
        try:
            conn = get_db_connection()
            if conn is None:
                flash('Erro de conexão com o banco de dados para adicionar produto.', 'danger')
                return redirect(url_for('produtos', error='add_db_connection_error'))

            is_sqlite = 'sqlite3' in conn.__class__.__module__
            with conn.cursor() as cur:
                if is_sqlite:
                    cur.execute("INSERT INTO produtos (nome, preco, link) VALUES (?, ?, ?)", (nome, preco, link))
                else:
                    cur.execute("INSERT INTO produtos (nome, preco, link) VALUES (%s, %s, %s)", (nome, preco, link))
                conn.commit()
            print(f"DEBUG ADICIONAR_PRODUTO: Produto '{nome}' adicionado com sucesso.")
            flash('Produto adicionado com sucesso!', 'success')
            return redirect(url_for('produtos'))
        except Exception as e:
            print(f"ERRO ADICIONAR_PRODUTO: Falha ao adicionar produto: {e}")
            traceback.print_exc()
            flash('Erro ao adicionar produto.', 'danger')
            if conn and not conn.closed: conn.rollback()
            return redirect(url_for('produtos', error='add_db_error',
                                    nome_val=nome, preco_val=preco, link_val=link))
        finally:
            if conn: conn.close()
    
    return redirect(url_for('produtos', add_new_product=True))


@app.route('/editar_produto/<int:produto_id>', methods=['GET', 'POST'])
def editar_produto(produto_id):
    print(f"DEBUG EDITAR_PRODUTO: Requisição para /editar_produto/{produto_id}. Method: {request.method}")

    if not session.get('logged_in'):
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados para editar produto.', 'danger')
            return redirect(url_for('produtos', error='edit_db_connection_error'))

        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
            if is_sqlite:
                cur.execute('SELECT * FROM produtos WHERE id = ?', (produto_id,))
            else:
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
                    return redirect(url_for('produtos', edit_id=produto_id,
                                            nome_val=nome, preco_val=preco, link_val=link))
                
                try:
                    preco = float(preco)
                    if preco <= 0:
                        flash('Preço deve ser um valor positivo.', 'danger')
                        return redirect(url_for('produtos', edit_id=produto_id,
                                                nome_val=nome, preco_val=preco, link_val=link))
                except ValueError:
                    flash('Preço inválido. Use um número.', 'danger')
                    return redirect(url_for('produtos', edit_id=produto_id,
                                            nome_val=nome, preco_val=preco, link_val=link))

                if is_sqlite:
                    cur.execute(
                        "UPDATE produtos SET nome = ?, preco = ?, link = ? WHERE id = ?",
                        (nome, preco, link, produto_id)
                    )
                else:
                    cur.execute(
                        "UPDATE produtos SET nome = %s, preco = %s, link = %s WHERE id = %s",
                        (nome, preco, link, produto_id)
                    )
                conn.commit()
                print(f"DEBUG EDITAR_PRODUTO: Produto ID {produto_id} atualizado com sucesso.")
                flash('Produto atualizado com sucesso!', 'success')
                return redirect(url_for('produtos'))
            
            return redirect(url_for('produtos', edit_id=produto_id,
                                    nome_val=produto['nome'],
                                    preco_val=f"{produto['preco']:.2f}",
                                    link_val=produto['link']))

    except Exception as e:
        print(f"ERRO EDITAR_PRODUTO: Falha ao editar produto: {e}")
        traceback.print_exc()
        flash('Erro ao editar produto.', 'danger')
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('produtos', edit_id=produto_id,
                                nome_val=request.form.get('nome', ''),
                                preco_val=request.form.get('preco', ''),
                                link_val=request.form.get('link', '')))
    finally:
        if conn: conn.close()

@app.route('/deletar_produto/<int:produto_id>', methods=['POST'])
def deletar_produto(produto_id):
    print(f"DEBUG DELETAR_PRODUTO: Requisição para /deletar_produto/{produto_id}. Method: {request.method}")

    if not session.get('logged_in'):
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados para deletar produto.', 'danger')
            return redirect(url_for('produtos', error='delete_db_connection_error'))

        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
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
    print("DEBUG VENDAS: Requisição para /vendas.")

    if not session.get('logged_in'):
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('index'))

        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
            if is_sqlite:
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
            else:
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

@app.route('/usuarios')
def usuarios():
    print("DEBUG USUARIOS: Requisição para /usuarios.")

    if not session.get('logged_in'):
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('index'))

        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
            if is_sqlite:
                cur.execute('SELECT * FROM users ORDER BY data_registro DESC')
            else:
                cur.execute('SELECT * FROM users ORDER BY data_registro DESC')
            usuarios_lista = cur.fetchall()
            print(f"DEBUG USUARIOS: {len(usuarios_lista)} usuários encontrados.")

        return render_template('usuarios.html', usuarios=usuarios_lista)

    except Exception as e:
        print(f"ERRO USUARIOS: Falha ao carregar usuários para o dashboard: {e}")
        traceback.print_exc()
        flash('Erro ao carregar os usuários.', 'danger')
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()

@app.route('/toggle_user_status/<int:user_id>', methods=['POST'])
def toggle_user_status(user_id):
    print(f"DEBUG TOGGLE_USER_STATUS: Requisição para /toggle_user_status/{user_id}. Method: {request.method}")

    if not session.get('logged_in'):
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('usuarios', error='toggle_db_connection_error'))

        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
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
            conn.commit()
            
            status_text = "ativado" if new_status else "desativado"
            print(f"DEBUG TOGGLE_USER_STATUS: Usuário {user_id} {status_text} com sucesso.")
            flash(f'Usuário {user_id} {status_text} com sucesso!', 'success')
            return redirect(url_for('usuarios'))
    except Exception as e:
        print(f"ERRO TOGGLE_USER_STATUS: Falha ao alterar status do usuário: {e}")
        traceback.print_exc()
        flash('Erro ao alterar status do usuário.', 'danger')
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('usuarios'))
    finally:
        if conn: conn.close()

@app.route('/scheduled_messages')
def scheduled_messages():
    print(f"DEBUG SCHEDULED_MESSAGES: Requisição para /scheduled_messages. Method: {request.method}")

    if not session.get('logged_in'):
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('index'))

        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
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
        print(f"ERRO SCHEDULED_MESSAGES: Falha ao carregar mensagens agendadas: {e}")
        traceback.print_exc()
        flash('Erro ao carregar mensagens agendadas.', 'danger')
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
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('scheduled_messages', error='add_db_connection_error'))

        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
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
                target_chat_id = None
            else:
                try:
                    target_chat_id = int(target_chat_id)
                except (ValueError, TypeError):
                    flash('ID do chat de destino inválido.', 'danger')
                    return render_template('add_scheduled_message.html', users=users, message_text=message_text, target_chat_id=target_chat_id, image_url=image_url, schedule_time_str=schedule_time_str)

            cur_conn = get_db_connection()
            if cur_conn is None:
                flash('Erro de conexão com o banco de dados.', 'danger')
                return render_template('add_scheduled_message.html', users=users, message_text=message_text, target_chat_id=target_chat_id, image_url=image_url, schedule_time_str=schedule_time_str)

            try:
                with cur_conn.cursor() as cur_inner:
                    if is_sqlite:
                        cur_inner.execute(
                            "INSERT INTO scheduled_messages (message_text, target_chat_id, image_url, schedule_time, status) VALUES (?, ?, ?, ?, ?)",
                            (message_text, target_chat_id, image_url if image_url else None, schedule_time, 'pending')
                        )
                    else:
                        cur_inner.execute(
                            "INSERT INTO scheduled_messages (message_text, target_chat_id, image_url, schedule_time, status) VALUES (%s, %s, %s, %s, %s)",
                            (message_text, target_chat_id, image_url if image_url else None, schedule_time, 'pending')
                        )
                    cur_conn.commit()
                flash('Mensagem agendada com sucesso!', 'success')
                return redirect(url_for('scheduled_messages'))
            except Exception as e:
                print(f"ERRO ADD_SCHEDULED_MESSAGE: Falha ao adicionar mensagem agendada: {e}")
                traceback.print_exc()
                flash('Erro ao agendar mensagem.', 'danger')
                if cur_conn and not cur_conn.closed: cur_conn.rollback()
                return render_template('add_scheduled_message.html', users=users, message_text=message_text, target_chat_id=target_chat_id, image_url=image_url, schedule_time_str=schedule_time_str)
            finally:
                if cur_conn: cur_conn.close()

        return render_template('add_scheduled_message.html', users=users)

    except Exception as e:
        print(f"ERRO ADD_SCHEDULED_MESSAGE (GET): Falha ao carregar usuários para o formulário: {e}")
        traceback.print_exc()
        flash('Erro ao carregar o formulário de agendamento.', 'danger')
        return redirect(url_for('scheduled_messages'))
    finally:
        if conn: conn.close()

@app.route('/edit_scheduled_message/<int:message_id>', methods=['GET', 'POST'])
def edit_scheduled_message(message_id):
    print(f"DEBUG EDIT_SCHEDULED_MESSAGE: Requisição para /edit_scheduled_message/{message_id}. Method: {request.method}")

    if not session.get('logged_in'):
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('scheduled_messages', error='edit_db_connection_error'))

        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
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
                    target_chat_id = None
                else:
                    try:
                        target_chat_id = int(target_chat_id)
                    except (ValueError, TypeError):
                        flash('ID do chat de destino inválido.', 'danger')
                        return render_template('edit_scheduled_message.html', message=message, users=users, message_text_val=message_text, target_chat_id_val=target_chat_id, image_url_val=image_url, schedule_time_str_val=schedule_time_str)

                if is_sqlite:
                    cur.execute(
                        "UPDATE scheduled_messages SET message_text = ?, target_chat_id = ?, image_url = ?, schedule_time = ?, status = ? WHERE id = ?",
                        (message_text, target_chat_id, image_url if image_url else None, schedule_time, status, message_id)
                    )
                else:
                    cur.execute(
                        "UPDATE scheduled_messages SET message_text = %s, target_chat_id = %s, image_url = %s, schedule_time = %s, status = %s WHERE id = %s",
                        (message_text, target_chat_id, image_url if image_url else None, schedule_time, status, message_id)
                    )
                conn.commit()
                print(f"DEBUG EDIT_SCHEDULED_MESSAGE: Mensagem agendada ID {message_id} atualizada com sucesso.")
                flash('Mensagem agendada atualizada com sucesso!', 'success')
                return redirect(url_for('scheduled_messages'))
            
            message['schedule_time_formatted'] = message['schedule_time'].strftime('%Y-%m-%dT%H:%M') if message['schedule_time'] else ''
            return render_template('edit_scheduled_message.html', message=message, users=users)

    except Exception as e:
        print(f"ERRO EDIT_SCHEDULED_MESSAGE: Falha ao editar mensagem agendada: {e}")
        traceback.print_exc()
        flash('Erro ao editar mensagem agendada.', 'danger')
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('scheduled_messages'))
    finally:
        if conn: conn.close()

@app.route('/delete_scheduled_message/<int:message_id>', methods=['POST'])
def delete_scheduled_message(message_id):
    print(f"DEBUG DELETE_SCHEDULED_MESSAGE: Requisição para /delete_scheduled_message/{message_id}. Method: {request.method}")

    if not session.get('logged_in'):
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('scheduled_messages', error='delete_db_connection_error'))

        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
            if is_sqlite:
                cur.execute('DELETE FROM scheduled_messages WHERE id = ?', (message_id,))
            else:
                cur.execute('DELETE FROM scheduled_messages WHERE id = %s', (message_id,))
            conn.commit()
            print(f"DEBUG DELETE_SCHEDULE_MESSAGE: Mensagem agendada ID {message_id} deletada com sucesso.")
            flash('Mensagem agendada deletada com sucesso!', 'success')
            return redirect(url_for('scheduled_messages'))
    except Exception as e:
        print(f"ERRO DELETE_SCHEDULE_MESSAGE: Falha ao deletar mensagem agendada: {e}")
        traceback.print_exc()
        flash('Erro ao deletar mensagem agendada.', 'danger')
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('scheduled_messages'))
    finally:
        if conn: conn.close()

@app.route('/send_broadcast', methods=['GET', 'POST'])
def send_broadcast():
    print(f"DEBUG SEND_BROADCAST: Requisição para /send_broadcast. Method: {request.method}")

    if not session.get('logged_in'):
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('index', error='broadcast_db_connection_error'))

        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
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
                return render_template('send_broadcast.html', active_users=active_users)

            sent_count = 0
            failed_count = 0
            
            cur_conn_send = get_db_connection()
            if cur_conn_send is None:
                flash('Erro de conexão com o banco de dados.', 'danger')
                return render_template('send_broadcast.html', active_users=active_users)

            try:
                with cur_conn_send.cursor() as cur_send:
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
                            delivered = True
                        except telebot.apihelper.ApiTelegramException as e:
                            print(f"ERRO BROADCAST para {user_id}:", e)
                            if "blocked" in str(e).lower() or "not found" in str(e).lower() or "deactivated" in str(e).lower():
                                print(f"AVISO: Usuário {user_id} bloqueou/não encontrado durante broadcast. Inativando...")
                                cur_update_user = get_db_connection()
                                if cur_update_user:
                                    temp_is_sqlite = 'sqlite3' in cur_update_user.__class__.__module__
                                    try:
                                        with cur_update_user.cursor() as cur_u:
                                            if temp_is_sqlite:
                                                cur_u.execute("UPDATE users SET is_active=0 WHERE id=?", (user_id,))
                                            else:
                                                cur_u.execute("UPDATE users SET is_active=FALSE WHERE id=%s", (user_id,))
                                            cur_update_user.commit()
                                    except Exception as db_e:
                                        print(f"ERRO ao inativar usuário {user_id} durante broadcast: {db_e}")
                                        if cur_update_user: cur_update_user.rollback()
                                    finally:
                                        if cur_update_user: cur_update_user.close()
                            failed_count += 1
                        except Exception as e:
                            print(f"ERRO INESPERADO BROADCAST para {user_id}: {e}")
                            traceback.print_exc()
                            failed_count += 1
                
                flash(f'Broadcast enviado com sucesso para {sent_count} usuários. Falha em {failed_count} usuários.', 'success')
                return redirect(url_for('index'))
            except Exception as e:
                print(f"ERRO SEND_BROADCAST (lógica de envio): {e}")
                traceback.print_exc()
                flash('Ocorreu um erro ao tentar enviar o broadcast.', 'danger')
                if cur_conn_send and not cur_conn_send.closed: cur_conn_send.rollback()
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

    if not session.get('logged_in'):
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('index'))

        is_sqlite = 'sqlite3' in conn.__class__.__module__
        with conn.cursor() as cur:
            if request.method == 'POST':
                welcome_bot_message = request.form.get('welcome_message_bot')
                welcome_community_message = request.form.get('welcome_message_community')

                if welcome_bot_message:
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
                if welcome_community_message:
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
                conn.commit()
                flash('Configurações de mensagens atualizadas com sucesso!', 'success')
                return redirect(url_for('config_messages'))
            
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
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('index'))
    finally:
        if conn: conn.close()


if __name__ == '__main__':
    print("DEBUG: Iniciando inicialização do banco de dados...")
    if not init_db():
        print("CRÍTICO: A inicialização do banco de dados falhou. Saindo...")
        exit(1)
    print("DEBUG: Inicialização do banco de dados concluída.")

    worker_thread = Thread(target=scheduled_message_worker)
    worker_thread.daemon = True
    worker_thread.start()
    print("DEBUG: Thread do worker de mensagens agendadas iniciada.")

    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000), debug=True)