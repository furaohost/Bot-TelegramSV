import os
import sqlite3
import json
import requests
import telebot
from telebot import types
import base64
import pagamentos
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta, time
from threading import Thread # Para rodar o worker em uma thread separada
import time as time_module # Para time.sleep
import traceback # Para imprimir o stack trace completo dos erros

# Imports para PostgreSQL
import psycopg2
from psycopg2.extras import RealDictCursor


# --- 1. CONFIGURAÇÃO INICIAL (Leitura de Variáveis de Ambiente) ---
API_TOKEN = os.getenv('API_TOKEN')
BASE_URL = os.getenv('BASE_URL')
DATABASE_URL = os.getenv('DATABASE_URL')

print(f"DEBUG: API_TOKEN lido: {API_TOKEN}")
print(f"DEBUG: BASE_URL lida: {BASE_URL}")
print(f"DEBUG: DATABASE_URL lida: {DATABASE_URL}")


# --- 2. INICIALIZAÇÃO DO FLASK E DO BOT ---
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'uma_chave_padrao_muito_segura_e_longa_para_dev_local_1234567890')
bot = telebot.TeleBot(API_TOKEN, threaded=False)

# --- 3. FUNÇÕES AUXILIARES DE BANCO DE DADOS ---

def get_db_connection():
    if not DATABASE_URL:
        print("AVISO: DATABASE_URL não definida, usando SQLite localmente (dashboard_local.db).")
        import sqlite3
        db_path = os.path.join(os.getcwd(), 'dashboard_local.db')
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    else:
        try:
            conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode='require')
            print("DEBUG DB: Conectado ao PostgreSQL.")
            return conn
        except Exception as e:
            print(f"ERRO DB: Falha ao conectar ao PostgreSQL: {e}")
            raise

def init_db():
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            print("DEBUG DB INIT: Iniciando criação/verificação de tabelas...")

            print("DEBUG DB INIT: Criando tabela 'users'...")
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                );
            ''')
            print("DEBUG DB INIT: Tabela 'users' criada.")

            # Adicionar is_active se a coluna não existir
            try:
                cur.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE;")
                print("DEBUG DB INIT: Coluna 'is_active' adicionada à tabela 'users'.")
            except psycopg2.errors.DuplicateColumn:
                print("DEBUG DB INIT: Coluna 'is_active' já existe em 'users'.")
            except Exception as e:
                print(f"ERRO DB INIT: Falha ao adicionar coluna 'is_active' em users: {e}")
                traceback.print_exc()

            print("DEBUG DB INIT: Criando tabela 'produtos'...")
            cur.execute('''
                CREATE TABLE IF NOT EXISTS produtos (
                    id SERIAL PRIMARY KEY,
                    nome TEXT NOT NULL,
                    preco NUMERIC(10, 2) NOT NULL,
                    link TEXT NOT NULL
                );
            ''')
            print("DEBUG DB INIT: Tabela 'produtos' criada.")

            print("DEBUG DB INIT: Criando tabela 'vendas'...")
            cur.execute('''
                CREATE TABLE IF NOT EXISTS vendas (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    produto_id INTEGER NOT NULL,
                    preco NUMERIC(10, 2) NOT NULL,
                    status TEXT NOT NULL,
                    data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    payment_id TEXT,
                    payer_name TEXT,
                    payer_email TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (produto_id) REFERENCES produtos (id)
                );
            ''')
            print("DEBUG DB INIT: Tabela 'vendas' criada.")

            print("DEBUG DB INIT: Criando tabela 'admin'...")
            cur.execute('''
                CREATE TABLE IF NOT EXISTS admin (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                );
            ''')
            print("DEBUG DB INIT: Tabela 'admin' criada.")

            print("DEBUG DB INIT: Criando tabela 'config'...")
            cur.execute('''
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
            ''')
            print("DEBUG DB INIT: Tabela 'config' criada.")

            # --- Lógica para inserir/verificar o usuário admin padrão ---
            print("DEBUG DB INIT: Verificando/inserindo usuário admin padrão...")
            cur.execute("SELECT id FROM admin WHERE username = %s", ('admin',))
            existing_admin = cur.fetchone()

            if not existing_admin:
                print("DEBUG DB INIT: Usuário 'admin' não encontrado. Inserindo...")
                hashed_password = generate_password_hash('admin123')
                cur.execute("INSERT INTO admin (username, password_hash) VALUES (%s, %s)", ('admin', hashed_password))
                print("DEBUG DB INIT: Usuário 'admin' padrão inserido com sucesso!")
            else:
                print("DEBUG DB INIT: Usuário 'admin' já existe.")
            # --- Fim da lógica do usuário admin ---

            print("DEBUG DB INIT: Inserindo/verificando mensagem de boas-vindas padrão (bot)...")
            cur.execute('''
                INSERT INTO config (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO NOTHING;
            ''', ('welcome_message_bot', 'Olá, {first_name}! Bem-vindo(a) ao bot!'))
            print("DEBUG DB INIT: Mensagem de boas-vindas padrão (bot) processada.")

            # --- Adicionando mensagem de boas-vindas à comunidade ---
            print("DEBUG DB INIT: Inserindo/verificando mensagem de boas-vindas padrão (comunidade)...")
            cur.execute('''
                INSERT INTO config (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO NOTHING;
            ''', ('welcome_message_community', 'Bem-vindo(a) à nossa comunidade, {first_name}!'))
            print("DEBUG DB INIT: Mensagem de boas-vindas padrão (comunidade) processada.")
            # --- Fim da adição de mensagem de boas-vindas à comunidade ---


            # --- TABELA: scheduled_messages ---
            print("DEBUG DB INIT: Criando tabela 'scheduled_messages'...")
            cur.execute('''
                CREATE TABLE IF NOT EXISTS scheduled_messages (
                    id SERIAL PRIMARY KEY,
                    message_text TEXT NOT NULL,
                    target_chat_id BIGINT,
                    image_url TEXT, -- COLUNA PARA IMAGEM/VÍDEO
                    schedule_time TIMESTAMP WITH TIME ZONE NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sent_at TIMESTAMP
                );
            ''')
            print("DEBUG DB INIT: Tabela 'scheduled_messages' criada.")

            # Adicionar a coluna image_url se ela não existir (para deploys existentes)
            try:
                # Usa ALTER TABLE IF NOT EXISTS para compatibilidade
                cur.execute("ALTER TABLE scheduled_messages ADD COLUMN image_url TEXT;")
                print("DEBUG DB INIT: Coluna 'image_url' adicionada à tabela 'scheduled_messages'.")
            except psycopg2.errors.DuplicateColumn:
                print("DEBUG DB INIT: Coluna 'image_url' já existe em 'scheduled_messages'.")
            except Exception as e:
                print(f"ERRO DB INIT: Falha ao adicionar coluna 'image_url': {e}")
                traceback.print_exc() # Imprime o stack trace completo
            # --- FIM DA TABELA E ALTERAÇÃO ---


            conn.commit()
            print("DEBUG DB: Tabelas do banco de dados verificadas/criadas (PostgreSQL/SQLite).")
    except Exception as e:
        print(f"ERRO DB: Falha ao inicializar o banco de dados: {e}")
        traceback.print_exc() # Imprime o stack trace completo
        if conn:
            conn.rollback()
        raise
    finally:
        if conn: conn.close()


def get_or_register_user(user: types.User):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            print("DEBUG DB: get_or_register_user - Testando conexão antes da query.")
            cur.execute('SELECT 1') # Teste de conexão
            print("DEBUG DB: get_or_register_user - Conexão OK.")

            # Adicionado para registrar a is_active
            cur.execute("SELECT * FROM users WHERE id = %s", (user.id,))
            db_user = cur.fetchone()
            if db_user is None:
                data_registro = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cur.execute("INSERT INTO users (id, username, first_name, last_name, data_registro, is_active) VALUES (%s, %s, %s, %s, %s, %s)",
                             (user.id, user.username, user.first_name, user.last_name, data_registro, True)) # Novo: is_active=True
                conn.commit()
            else: # Se o usuário já existe, garantir que está ativo (se reativou o bot)
                if not db_user['is_active']:
                    cur.execute("UPDATE users SET is_active = TRUE WHERE id = %s", (user.id,))
                    conn.commit()
                    print(f"DEBUG DB: Usuário {user.id} reativado.")
    except Exception as e:
        print(f"ERRO DB: get_or_register_user falhou: {e}")
        traceback.print_exc() # Imprime o stack trace completo
        if conn and not conn.closed: conn.rollback()
    finally:
        if conn: conn.close()


def enviar_produto_telegram(user_id, nome_produto, link_produto):
    url = f"[https://api.telegram.org/bot](https://api.telegram.org/bot){API_TOKEN}/sendMessage"
    texto = (f"🎉 Pagamento Aprovado!\n\nObrigado por comprar *{nome_produto}*.\n\nAqui está o seu link de acesso:\n{link_produto}")
    payload = { 'chat_id': user_id, 'text': texto, 'parse_mode': 'Markdown' }
    try:
        requests.post(url, json=payload)
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar mensagem de entrega: {e}")
        traceback.print_exc() # Imprime o stack trace completo

# --- 4. ROTAS DO PAINEL WEB (FLASK) ---

@app.route(f"/{API_TOKEN}", methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return '!', 200
    else:
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
                        data_venda_dt = datetime.strptime(str(venda['data_venda']), '%Y-%m-%d %H:%M:%S.%f') if isinstance(venda['data_venda'], datetime) else datetime.strptime(venda['data_venda'], '%Y-%m-%d %H:%M:%S')
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
                traceback.print_exc() # Imprime o stack trace completo
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
                if admin_user and check_password_hash(admin_user['password_hash'], password):
                    session['logged_in'] = True
                    session['username'] = admin_user['username']
                    print(f"DEBUG LOGIN: Login bem-sucedido para {session['username']}. session['logged_in'] = {session.get('logged_in')}")
                    return redirect(url_for('index'))
                else:
                    flash('Usuário ou senha inválidos.', 'danger')
                    print("DEBUG LOGIN: Login falhou. Credenciais inválidas.")
        except Exception as e:
            print(f"ERRO LOGIN: Falha no processo de login: {e}")
            traceback.print_exc() # Imprime o stack trace completo
            flash('Erro no servidor ao tentar login.', 'danger')
            if conn and not conn.closed: conn.rollback()
        finally:
            if conn: conn.close()

    print("DEBUG LOGIN: Renderizando login.html.")
    return render_template('login.html')

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
            cur.execute('SELECT COUNT(id) FROM users WHERE is_active = TRUE') # Contar apenas usuários ativos
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

            cur.execute("SELECT v.id, u.username, u.first_name, p.nome, v.preco, v.data_venda, CASE WHEN v.status = 'aprovado' THEN 'aprovado' WHEN v.status = 'pendente' AND EXTRACT(EPOCH FROM (NOW() - v.data_venda)) > 3600 THEN 'expirado' ELSE v.status END AS status FROM vendas v JOIN users u ON v.user_id = u.id JOIN produtos p ON v.produto_id = p.id ORDER BY v.id DESC LIMIT 5")
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
        traceback.print_exc() # Imprime o stack trace completo
        flash('Erro ao carregar o dashboard.', 'danger')
        return redirect(url_for('login'))
    finally:
        if conn: conn.close()

@app.route('/produtos', methods=['GET', 'POST'])
def produtos():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            if request.method == 'POST':
                nome = request.form.get('nome')
                preco = request.form.get('preco')
                link = request.form.get('link')
                cur.execute('INSERT INTO produtos (nome, preco, link) VALUES (%s, %s, %s)', (nome, preco, link))
                conn.commit()
                flash('Produto adicionado com sucesso!', 'success')
                return redirect(url_for('produtos'))

            cur.execute('SELECT * FROM produtos ORDER BY id DESC')
            lista_produtos = cur.fetchall()
            return render_template('produtos.html', produtos=lista_produtos)
    except Exception as e:
        print(f"ERRO PRODUTOS: Falha ao gerenciar produtos: {e}")
        traceback.print_exc() # Imprime o stack trace completo
        flash('Erro ao carregar ou adicionar produtos.', 'danger')
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('index'))
    finally:
        if conn: conn.close()

@app.route('/edit_product/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM produtos WHERE id = %s', (id,))
            produto = cur.fetchone()
            if request.method == 'POST':
                nome = request.form.get('nome')
                preco = request.form.get('preco')
                link = request.form.get('link')
                cur.execute('UPDATE produtos SET nome = %s, preco = %s, link = %s WHERE id = %s', (nome, preco, link, id))
                conn.commit()
                flash('Produto atualizado com sucesso!', 'success')
                return redirect(url_for('produtos'))
            return render_template('edit_product.html', produto=produto)
    except Exception as e:
        print(f"ERRO EDIT PRODUTO: Falha ao editar produto: {e}")
        traceback.print_exc() # Imprime o stack trace completo
        flash('Erro ao carregar ou editar produto.', 'danger')
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('produtos'))
    finally:
        if conn: conn.close()

@app.route('/remove_product/<int:id>')
def remove_product(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('DELETE FROM produtos WHERE id = %s', (id,))
            conn.commit()
            flash('Produto removido com sucesso!', 'danger')
            return redirect(url_for('produtos'))
    except Exception as e:
        print(f"ERRO REMOVE PRODUTO: Falha ao remover produto: {e}")
        traceback.print_exc() # Imprime o stack trace completo
        flash('Erro ao remover produto.', 'danger')
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('produtos'))
    finally:
        if conn: conn.close()

@app.route('/vendas')
def vendas():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('SELECT id, nome FROM produtos ORDER BY nome')
            produtos_disponiveis = cur.fetchall()

            query_base = "SELECT v.id, u.username, u.first_name, p.nome, v.preco, v.data_venda, p.id as produto_id, CASE WHEN v.status = 'aprovado' THEN 'aprovado' WHEN v.status = 'pendente' AND EXTRACT(EPOCH FROM (NOW() - v.data_venda)) > 3600 THEN 'expirado' ELSE v.status END AS status FROM vendas v JOIN users u ON v.user_id = u.id JOIN produtos p ON v.produto_id = p.id"
            conditions, params = [], []
            data_inicio_str, data_fim_str, pesquisa_str, produto_id_str, status_str = (request.args.get('data_inicio'), request.args.get('data_fim'), request.args.get('pesquisa'), request.args.get('produto_id'), request.args.get('status'))

            if data_inicio_str: conditions.append("DATE(v.data_venda) >= %s"); params.append(data_inicio_str)
            if data_fim_str: conditions.append("DATE(v.data_venda) <= %s"); params.append(data_fim_str)
            if pesquisa_str: conditions.append("(u.username ILIKE %s OR p.nome ILIKE %s OR u.first_name ILIKE %s)"); params.extend([f'%{pesquisa_str}%'] * 3)
            if produto_id_str: conditions.append("p.id = %s"); params.append(produto_id_str)
            if status_str: conditions.append("v.status = %s"); params.append(status_str)

            if conditions: query_base += " WHERE " + " AND ".join(conditions)
            query_base += " ORDER BY v.id DESC"

            cur.execute(query_base, tuple(params))
            lista_vendas = cur.fetchall()
            return render_template('vendas.html', vendas=lista_vendas, produtos_disponiveis=produtos_disponiveis)
    except Exception as e:
        print(f"ERRO VENDAS: Falha ao carregar vendas: {e}")
        traceback.print_exc() # Imprime o stack trace completo
        flash('Erro ao carregar vendas.', 'danger')
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('index'))
    finally:
        if conn: conn.close()

@app.route('/venda_detalhes/<int:id>')
def venda_detalhes(id):
    if not session.get('logged_in'): return jsonify({'error': 'Unauthorized'}), 401
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM vendas WHERE id = %s', (id,))
            venda = cur.fetchone()
            if venda: return jsonify(dict(venda))
            return jsonify({'error': 'Not Found'}), 404
    except Exception as e:
        print(f"ERRO VENDA DETALHES: Falha ao obter detalhes da venda: {e}")
        traceback.print_exc() # Imprime o stack trace completo
        return jsonify({'error': 'Internal Server Error'}), 500
    finally:
        if conn: conn.close()

@app.route('/usuarios')
def usuarios():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Seleciona apenas usuários ativos para o painel de usuários
            cur.execute('SELECT * FROM users ORDER BY id DESC')
            lista_usuarios = cur.fetchall()
            return render_template('usuarios.html', usuarios=lista_usuarios)
    except Exception as e:
        print(f"ERRO USUARIOS: Falha ao carregar usuários: {e}")
        traceback.print_exc() # Imprime o stack trace completo
        flash('Erro ao carregar usuários.', 'danger')
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('index'))
    finally:
        if conn: conn.close()

@app.route('/remove_user/<int:id>')
def remove_user(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Remove usuário e suas vendas relacionadas
            cur.execute('DELETE FROM vendas WHERE user_id = %s', (id,))
            cur.execute('DELETE FROM users WHERE id = %s', (id,))
            conn.commit()
            flash('Usuário e vendas associadas removidos com sucesso!', 'danger')
            return redirect(url_for('usuarios'))
    except Exception as e:
        print(f"ERRO REMOVE USUARIO: Falha ao remover usuário: {e}")
        traceback.print_exc() # Imprime o stack trace completo
        flash('Erro ao remover usuário.', 'danger')
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('usuarios'))
    finally:
        if conn: conn.close()

@app.route('/pagamento/<status>')
def pagamento_retorno(status):
    mensagem = "Status do Pagamento: "
    if status == 'sucesso': mensagem += "Aprovado com sucesso!"
    elif status == 'falha': mensagem += "Pagamento falhou."
    elif status == 'pendente': mensagem += "Pagamento pendente."
    return f"<div style='font-family: sans-serif; text-align: center; padding-top: 50px;'><h1>{mensagem}</h1><p>Você pode fechar esta janela e voltar para o Telegram.</p></div>"

# --- ROTA PARA MENSAGENS DE BOAS-VINDAS (AGORA CONFIGURA BOT E COMUNIDADE) ---
@app.route('/config_messages', methods=['GET', 'POST'])
def config_messages():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Busca a mensagem de boas-vindas do bot
            cur.execute("SELECT value FROM config WHERE key = %s", ('welcome_message_bot',))
            current_welcome_message_bot_row = cur.fetchone()
            current_welcome_message_bot = current_welcome_message_bot_row['value'] if current_welcome_message_bot_row else ''

            # Busca a mensagem de boas-vindas da comunidade
            cur.execute("SELECT value FROM config WHERE key = %s", ('welcome_message_community',))
            current_welcome_message_community_row = cur.fetchone()
            current_welcome_message_community = current_welcome_message_community_row['value'] if current_welcome_message_community_row else ''

            if request.method == 'POST':
                new_message_bot = request.form.get('welcome_message_bot')
                new_message_community = request.form.get('welcome_message_community')

                # Atualiza a mensagem do bot
                cur.execute("UPDATE config SET value = %s WHERE key = %s", (new_message_bot, 'welcome_message_bot'))

                # Atualiza a mensagem da comunidade
                cur.execute("UPDATE config SET value = %s WHERE key = %s", (new_message_community, 'welcome_message_community'))

                conn.commit()
                flash('Mensagens de boas-vindas atualizadas com sucesso!', 'success')
                return redirect(url_for('config_messages'))

            return render_template(
                'config_messages.html',
                welcome_message_bot=current_welcome_message_bot,
                welcome_message_community=current_welcome_message_community
            )
    except Exception as e:
        print(f"ERRO CONFIG MENSAGENS: Falha ao configurar mensagens: {e}")
        traceback.print_exc() # Imprime o stack trace completo
        flash('Erro ao carregar ou atualizar mensagens.', 'danger')
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('index'))
    finally:
        if conn: conn.close()

# --- ROTAS PARA MENSAGENS AGENDADAS ---
@app.route('/scheduled_messages')
def scheduled_messages():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Seleciona todas as mensagens agendadas, ordenadas pela data de agendamento
            cur.execute('SELECT * FROM scheduled_messages ORDER BY schedule_time DESC')
            messages = cur.fetchall()
            return render_template('scheduled_messages.html', messages=messages)
    except Exception as e:
        print(f"ERRO SCHEDULED MESSAGES: Falha ao carregar mensagens agendadas: {e}")
        traceback.print_exc() # Imprime o stack trace completo
        flash('Erro ao carregar mensagens agendadas.', 'danger')
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('index'))
    finally:
        if conn: conn.close()

@app.route('/add_scheduled_message', methods=['GET', 'POST'])
def add_scheduled_message():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            if request.method == 'POST':
                message_text = request.form.get('message_text')
                target_chat_id = request.form.get('target_chat_id')
                # Adicionado para capturar a image_url
                image_url = request.form.get('image_url')
                schedule_time_str = request.form.get('schedule_time')

                if not message_text or not schedule_time_str:
                    flash('Texto da mensagem e horário de agendamento são obrigatórios.', 'danger')
                    return render_template('add_scheduled_message.html')

                try:
                    schedule_time = datetime.strptime(schedule_time_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    flash('Formato de data/hora inválido. Use AAAA-MM-DDTHH:MM.', 'danger')
                    return render_template('add_scheduled_message.html')

                final_target_chat_id = int(target_chat_id) if target_chat_id else None
                final_image_url = image_url if image_url else None # Armazena None se vazio

                cur.execute(
                    'INSERT INTO scheduled_messages (message_text, target_chat_id, image_url, schedule_time, status) VALUES (%s, %s, %s, %s, %s)',
                    (message_text, final_target_chat_id, final_image_url, schedule_time, 'pending')
                )
                conn.commit()
                flash('Mensagem agendada com sucesso!', 'success')
                return redirect(url_for('scheduled_messages'))

            return render_template('add_scheduled_message.html')
    except Exception as e:
        print(f"ERRO ADD SCHEDULED MESSAGE: Falha ao adicionar mensagem agendada: {e}")
        traceback.print_exc() # Imprime o stack trace completo
        flash('Erro ao adicionar mensagem agendada.', 'danger')
        if conn and not conn.closed: conn.rollback()
        return redirect(url_for('scheduled_messages'))
    finally:
        if conn: conn.close()

    @app.route('/edit_scheduled_message/<int:id>', methods=['GET', 'POST'])
    def edit_scheduled_message(id):
        if not session.get('logged_in'):
            return redirect(url_for('login'))

        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM scheduled_messages WHERE id = %s', (id,))
                message = cur.fetchone()

                if not message:
                    flash('Mensagem agendada não encontrada.', 'danger')
                    return redirect(url_for('scheduled_messages'))

                if request.method == 'POST':
                    message_text = request.form.get('message_text')
                    target_chat_id = request.form.get('target_chat_id')
                    # Adicionado para capturar a image_url
                    image_url = request.form.get('image_url')
                    schedule_time_str = request.form.get('schedule_time')
                    status = request.form.get('status')

                    if not message_text or not schedule_time_str or not status:
                        flash('Texto da mensagem, horário e status são obrigatórios.', 'danger')
                        return render_template('edit_scheduled_message.html', message=message)

                    try:
                        schedule_time = datetime.strptime(schedule_time_str, '%Y-%m-%dT%H:%M')
                    except ValueError:
                        flash('Formato de data/hora inválido. Use AAAA-MM-DDTHH:MM.', 'danger')
                        return render_template('edit_scheduled_message.html', message=message)

                    final_target_chat_id = int(target_chat_id) if target_chat_id else None
                    final_image_url = image_url if image_url else None # Armazena None se vazio

                    cur.execute(
                        'UPDATE scheduled_messages SET message_text = %s, target_chat_id = %s, image_url = %s, schedule_time = %s, status = %s WHERE id = %s',
                        (message_text, final_target_chat_id, final_image_url, schedule_time, status, id)
                    )
                    conn.commit()
                    flash('Mensagem agendada atualizada com sucesso!', 'success')
                    return redirect(url_for('scheduled_messages'))

                message_data = dict(message)
                if message_data['schedule_time']:
                    message_data['schedule_time_formatted'] = message_data['schedule_time'].strftime('%Y-%m-%dT%H:%M')

                return render_template('edit_scheduled_message.html', message=message_data)
        except Exception as e:
            print(f"ERRO EDIT SCHEDULED MESSAGE: Falha ao editar mensagem agendada: {e}")
            traceback.print_exc() # Imprime o stack trace completo
            flash('Erro ao editar mensagem agendada.', 'danger')
            if conn and not conn.closed: conn.rollback()
            return redirect(url_for('scheduled_messages'))
        finally:
            if conn: conn.close()

    @app.route('/remove_scheduled_message/<int:id>')
    def remove_scheduled_message(id):
        if not session.get('logged_in'):
            return redirect(url_for('login'))

        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute('DELETE FROM scheduled_messages WHERE id = %s', (id,))
                conn.commit()
                flash('Mensagem agendada removida com sucesso!', 'danger')
                return redirect(url_for('scheduled_messages'))
        except Exception as e:
            print(f"ERRO REMOVE SCHEDULED MESSAGE: Falha ao remover mensagem agendada: {e}")
            traceback.print_exc() # Imprime o stack trace completo
            flash('Erro ao remover mensagem agendada.', 'danger')
            if conn and not conn.closed: conn.rollback()
            return redirect(url_for('scheduled_messages'))
        finally:
            if conn: conn.close()

    # --- COMANDOS DO BOT ---
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        get_or_register_user(message.from_user)

        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM config WHERE key = %s", ('welcome_message_bot',))
                welcome_message = cur.fetchone()
                final_message = "Olá! Bem-vindo(a)."
                if welcome_message:
                    final_message = welcome_message['value'].replace('{first_name}', message.from_user.first_name or 'usuário')
                else:
                    final_message = f"Olá, {message.from_user.first_name or 'usuário'}! Bem-vindo(a)."

                markup = types.InlineKeyboardMarkup()
                btn_produtos = types.InlineKeyboardButton("🛍️ Ver Produtos", callback_data='ver_produtos')
                markup.add(btn_produtos)
                bot.reply_to(message, final_message, reply_markup=markup)
        except Exception as e:
            print(f"ERRO START: Falha ao enviar mensagem de boas-vindas: {e}")
            traceback.print_exc() # Imprime o stack trace completo
            bot.reply_to(message, "Ocorreu um erro ao iniciar o bot. Tente novamente mais tarde.")
        finally:
            if conn: conn.close()

    # --- NOVO: Handler para novos membros em grupos ---
    @bot.message_handler(content_types=['new_chat_members'])
    def handle_new_chat_members(message):
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM config WHERE key = %s", ('welcome_message_community',))
                welcome_community_message_row = cur.fetchone()
                welcome_community_message = welcome_community_message_row['value'] if welcome_community_message_row else 'Bem-vindo(a) à nossa comunidade!'

                for user in message.new_chat_members:
                    # O Telegram pode enviar o próprio bot como new_chat_member
                    if user.id == bot.get_me().id:
                        continue # Não enviar mensagem de boas-vindas para o próprio bot

                    # Registra o novo membro no seu banco de dados se ainda não estiver lá
                    get_or_register_user(user)

                    final_message = welcome_community_message.replace('{first_name}', user.first_name or 'novo membro')
                    bot.send_message(message.chat.id, final_message)
        except Exception as e:
            print(f"ERRO NEW MEMBERS: Falha ao enviar mensagem de boas-vindas para novos membros: {e}")
            traceback.print_exc() # Imprime o stack trace completo
        finally:
            if conn: conn.close()

    @bot.callback_query_handler(func=lambda call: True)
    def callback_query(call):
        get_or_register_user(call.from_user)
        if call.data == 'ver_produtos':
            mostrar_produtos(call.message.chat.id)
        elif call.data.startswith('comprar_'):
            produto_id = int(call.data.split('_')[1])
            gerar_cobranca(call, produto_id)

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
                    bot.send_message(chat_id, f"💎 *{produto['nome']}*\n\nPreço: R${produto['preco']:.2f}", parse_mode='Markdown', reply_markup=markup)
        except Exception as e:
            print(f"ERRO MOSTRAR PRODUTOS: Falha ao mostrar produtos: {e}")
            traceback.print_exc() # Imprime o stack trace completo
            bot.send_message(chat_id, "Ocorreu um erro ao carregar os produtos.")
        finally:
            if conn: conn.close()

    def gerar_cobranca(call: types.CallbackQuery, produto_id: int):
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
            traceback.print_exc() # Imprime o stack trace completo
            bot.send_message(chat_id, "Ocorreu um erro interno ao gerar sua cobrança. Tente novamente.")
            if conn and not conn.closed: conn.rollback()
        finally:
            if conn: conn.close()

    # --- WORKER PARA ENVIO DE MENSAGENS AGENDADAS ---
    # (Esta função é definida aqui para ser acessível antes da inicialização)
    def scheduled_message_worker():
        print("DEBUG WORKER: Iniciando worker de mensagens agendadas...")
        while True:
            conn = None
            try:
                conn = get_db_connection()
                with conn.cursor() as cur:
                    # Busca mensagens pendentes cujo horário de agendamento já passou
                    cur.execute(
                        "SELECT id, message_text, target_chat_id, image_url FROM scheduled_messages WHERE status = 'pending' AND schedule_time <= NOW() ORDER BY schedule_time ASC"
                    )
                    messages_to_send = cur.fetchall()

                    if not messages_to_send:
                        print("DEBUG WORKER: Nenhuma mensagem agendada para enviar no momento.")

                    for msg in messages_to_send:
                        print(f"DEBUG WORKER: Processando mensagem agendada ID: {msg['id']}")
                        send_successful = False
                        
                        target_chats = []
                        if msg['target_chat_id']:
                            target_chats.append(msg['target_chat_id'])
                            print(f"DEBUG WORKER: Enviando para chat específico: {msg['target_chat_id']}")
                        else: # Enviar para todos os usuários (broadcast)
                            print("DEBUG WORKER: Enviando para todos os usuários registrados.")
                            # Seleciona apenas usuários ATIVOS
                            cur.execute("SELECT id FROM users WHERE is_active = TRUE")
                            all_user_ids = cur.fetchall()
                            target_chats = [user['id'] for user in all_user_ids]
                            
                            if not target_chats:
                                print("DEBUG WORKER: Nenhum usuário ATIVO registrado para enviar mensagem de broadcast.")
                                cur.execute("UPDATE scheduled_messages SET status = 'failed', sent_at = NOW() WHERE id = %s", (msg['id'],))
                                conn.commit()
                                continue # Pula para a próxima mensagem agendada

                        for chat_id in target_chats:
                            try:
                                # Tentar enviar foto/vídeo, se houver URL
                                if msg['image_url']:
                                    print(f"DEBUG WORKER: Tentando enviar foto/vídeo para {chat_id} com URL: {msg['image_url']}")
                                    # send_photo pode lidar com URLs de vídeo se o Telegram as aceitar como foto para preview
                                    bot.send_photo(chat_id, msg['image_url'], caption=msg['message_text'], parse_mode='Markdown')
                                else:
                                    print(f"DEBUG WORKER: Enviando texto para {chat_id}")
                                    bot.send_message(chat_id, msg['message_text'], parse_mode='Markdown')
                                send_successful = True # Pelo menos um envio bem-sucedido
                                print(f"DEBUG WORKER: Mensagem agendada ID {msg['id']} enviada com sucesso para {chat_id}.")
                            except telebot.apihelper.ApiTelegramException as e:
                                print(f"ERRO WORKER: Falha ao enviar mensagem para chat {chat_id} (ID Msg Agendada: {msg['id']}): {e}")
                                traceback.print_exc() # Imprime o stack trace completo do erro do Telegram
                                # Se o erro for "chat not found" ou "bot was blocked", marcar usuário como inativo
                                if "chat not found" in str(e).lower() or "bot was blocked by the user" in str(e).lower() or "user is deactivated" in str(e).lower():
                                    print(f"AVISO WORKER: Chat {chat_id} pode ter bloqueado o bot ou não existe. Marcando usuário como inativo.")
                                    # Marcar usuário como inativo na tabela users
                                    temp_conn = None
                                    try:
                                        temp_conn = get_db_connection()
                                        with temp_conn.cursor() as temp_cur:
                                            temp_cur.execute("UPDATE users SET is_active = FALSE WHERE id = %s", (chat_id,))
                                            temp_cur.commit()
                                            print(f"DEBUG WORKER: Usuário {chat_id} marcado como inativo.")
                                    except Exception as db_e:
                                        print(f"ERRO WORKER: Falha ao marcar usuário {chat_id} como inativo: {db_e}")
                                        traceback.print_exc()
                                    finally:
                                        if temp_conn: temp_conn.close()
                                else: # Outros erros da API do Telegram
                                    send_successful = False
                                    print(f"ERRO WORKER: Erro crítico para mensagem agendada ID {msg['id']}. Interrompendo envio para os demais alvos.")
                                    break # Interrompe o envio para outros chats se for um erro crítico

                            except Exception as e: # Erros inesperados
                                print(f"ERRO WORKER: Erro inesperado ao enviar mensagem para chat {chat_id} (ID Msg Agendada: {msg['id']}): {e}")
                                traceback.print_exc() # Imprime o stack trace completo
                                send_successful = False
                                break # Interrompe o envio para outros chats

                        # Atualiza o status no banco de dados com base no resultado dos envios
                        if send_successful:
                            cur.execute("UPDATE scheduled_messages SET status = 'sent', sent_at = NOW() WHERE id = %s", (msg['id'],))
                            print(f"DEBUG WORKER: Mensagem agendada ID {msg['id']} marcada como 'sent'.")
                        else:
                            cur.execute("UPDATE scheduled_messages SET status = 'failed', sent_at = NOW() WHERE id = %s", (msg['id'],))
                            print(f"DEBUG WORKER: Mensagem agendada ID {msg['id']} marcada como 'failed'.")
                        conn.commit()

            except Exception as e:
                print(f"ERRO WORKER PRINCIPAL: Erro no loop principal do worker de mensagens agendadas: {e}")
                traceback.print_exc() # Imprime o stack trace completo
                if conn and not conn.closed: conn.rollback()
            finally:
                if conn: conn.close() # Garante que a conexão é fechada

            time_module.sleep(60) # Verifica a cada 60 segundos (pode ajustar)
    # --- FIM DO WORKER ---

    # --- ROTA PARA ENVIO DE MENSAGENS EM MASSA (BROADCAST) ---
    @app.route('/send_broadcast', methods=['GET', 'POST'])
    def send_broadcast():
        if not session.get('logged_in'):
            return redirect(url_for('login'))

        if request.method == 'POST':
            message_text = request.form.get('message_text')
            image_url = request.form.get('image_url') # URL da imagem/vídeo para broadcast

            if not message_text:
                flash('O texto da mensagem é obrigatório para o broadcast.', 'danger')
                return render_template('send_broadcast.html')

            conn = None
            try:
                conn = get_db_connection()
                with conn.cursor() as cur:
                    # Seleciona apenas usuários ATIVOS para broadcast
                    cur.execute("SELECT id FROM users WHERE is_active = TRUE")
                    all_user_ids_rows = cur.fetchall()
                    target_user_ids = [user['id'] for user in all_user_ids_rows]

                    if not target_user_ids:
                        flash('Nenhum usuário ativo registrado para enviar o broadcast.', 'warning')
                        return render_template('send_broadcast.html')

                    successful_sends = 0
                    failed_sends = 0

                    for user_id in target_user_ids:
                        try:
                            if image_url:
                                print(f"DEBUG BROADCAST: Enviando foto/vídeo em broadcast para {user_id} com URL: {image_url}")
                                bot.send_photo(user_id, image_url, caption=message_text, parse_mode='Markdown')
                            else:
                                print(f"DEBUG BROADCAST: Enviando texto em broadcast para {user_id}")
                                bot.send_message(user_id, message_text, parse_mode='Markdown')
                            successful_sends += 1
                        except telebot.apihelper.ApiTelegramException as e:
                            print(f"ERRO BROADCAST: Falha ao enviar broadcast para {user_id}: {e}")
                            traceback.print_exc() # Imprime o stack trace completo
                            # Se o erro for "chat not found" ou "bot was blocked", marcar usuário como inativo
                            if "chat not found" in str(e).lower() or "bot was blocked by the user" in str(e).lower() or "user is deactivated" in str(e).lower():
                                print(f"AVISO BROADCAST: Usuário {user_id} pode ter bloqueado o bot ou não existe. Marcando usuário como inativo.")
                                # Marcar usuário como inativo na tabela users
                                temp_conn = None
                                try:
                                    temp_conn = get_db_connection()
                                    with temp_conn.cursor() as temp_cur:
                                        temp_cur.execute("UPDATE users SET is_active = FALSE WHERE id = %s", (user_id,))
                                        temp_cur.commit()
                                        print(f"DEBUG BROADCAST: Usuário {user_id} marcado como inativo.")
                                except Exception as db_e:
                                    print(f"ERRO BROADCAST: Falha ao marcar usuário {user_id} como inativo: {db_e}")
                                    traceback.print_exc()
                                finally:
                                    if temp_conn: temp_conn.close()
                            else: # Outros erros da API do Telegram
                                failed_sends += 1
                        except Exception as e:
                            print(f"ERRO BROADCAST: Erro inesperado ao enviar broadcast para {user_id}: {e}")
                            traceback.print_exc() # Imprime o stack trace completo
                            failed_sends += 1
                    
                    flash(f'Broadcast enviado! Sucesso: {successful_sends}, Falhas: {failed_sends}.', 'success')
                    return redirect(url_for('send_broadcast'))

            except Exception as e:
                print(f"ERRO BROADCAST: Falha ao processar envio de broadcast: {e}")
                traceback.print_exc() # Imprime o stack trace completo
                flash('Erro ao tentar enviar broadcast.', 'danger')
                if conn and not conn.closed: conn.rollback()
                return render_template('send_broadcast.html')
            finally:
                if conn: conn.close()

        return render_template('send_broadcast.html')

    # --- FIM DAS ROTAS ---

    # --- INICIALIZAÇÃO FINAL ---
    if __name__ != '__main__':
        try:
            init_db()

            pagamentos.init_mercadopago_sdk()

            if API_TOKEN and BASE_URL:
                bot.set_webhook(url=f"{BASE_URL}/{API_TOKEN}")
                print("Webhook do Telegram configurado com sucesso!")
            else:
                print("ERRO: Variáveis de ambiente API_TOKEN ou BASE_URL não definidas.")
            
            # Inicia o worker de mensagens agendadas em uma thread separada
            worker_thread = Thread(target=scheduled_message_worker)
            worker_thread.daemon = True # Permite que a thread seja encerrada quando o programa principal sai
            worker_thread.start()
            print("DEBUG: Worker de mensagens agendadas iniciado em segundo plano.")

        except Exception as e:
            print(f"Erro ao configurar o webhook do Telegram ou iniciar worker: {e}")
            traceback.print_exc() # Imprime o stack trace completo
