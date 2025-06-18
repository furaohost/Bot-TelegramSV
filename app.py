import os
import sqlite3
import json
import requests
import telebot
from telebot import types
import base64
import pagamentos # Importar o módulo pagamentos
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import check_password_hash
from datetime import datetime, timedelta, time

# --- 1. CONFIGURAÇÃO INICIAL (Leitura de Variáveis de Ambiente) ---
API_TOKEN = os.getenv('API_TOKEN')
BASE_URL = os.getenv('BASE_URL') # A URL base do seu serviço Render

# Adicione essas linhas para depuração (mantenha durante o troubleshoot)
print(f"DEBUG: API_TOKEN lido: {API_TOKEN}")
print(f"DEBUG: BASE_URL lida: {BASE_URL}")

# --- 2. INICIALIZAÇÃO DO FLASK E DO BOT ---
# O 'app' (Flask) e 'bot' (Telebot) devem ser inicializados APÓS
# a leitura das variáveis de ambiente essenciais.
app = Flask(__name__)
# Garante que FLASK_SECRET_KEY é lida e tem um fallback seguro para local
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'uma_chave_padrao_muito_segura_e_longa_para_dev_local_1234567890')
bot = telebot.TeleBot(API_TOKEN, threaded=False) # Agora API_TOKEN já deve ter valor

DB_NAME = 'dashboard.db'

# --- 3. FUNÇÕES AUXILIARES DE BANCO DE DADOS ---
def get_db_connection():
    # Caminho do banco de dados para Render e local
    db_path = os.path.join('/var/data/sqlite', DB_NAME) if os.path.exists('/var/data/sqlite') else DB_NAME
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.execute('''
        INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)
    ''', ('welcome_message_bot', 'Olá, {first_name}! Bem-vindo(a) ao bot!'))
    conn.commit()
    conn.close()
    print("Tabelas do banco de dados verificadas/criadas.")


def get_or_register_user(user: types.User):
    conn = get_db_connection()
    db_user = conn.execute("SELECT * FROM users WHERE id = ?", (user.id,)).fetchone()
    if db_user is None:
        data_registro = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn.execute("INSERT INTO users (id, username, first_name, last_name, data_registro) VALUES (?, ?, ?, ?, ?)",
                         (user.id, user.username, user.first_name, user.last_name, data_registro))
        conn.commit()
    conn.close()

def enviar_produto_telegram(user_id, nome_produto, link_produto):
    url = f"https://api.telegram.org/bot{API_TOKEN}/sendMessage"
    texto = (f"🎉 Pagamento Aprovado!\n\nObrigado por comprar *{nome_produto}*.\n\nAqui está o seu link de acesso:\n{link_produto}")
    payload = { 'chat_id': user_id, 'text': texto, 'parse_mode': 'Markdown' }
    try:
        requests.post(url, json=payload)
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar mensagem de entrega: {e}")

# --- 4. ROTAS DO PAINEL WEB (FLASK) ---
# O webhook do Telegram deve ser uma das primeiras rotas a serem definidas para garantir o registro.

@app.route(f"/{API_TOKEN}", methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return '!', 200
    else:
        return "Unsupported Media Type", 415

@app.route('/webhook/mercado-pago', methods=['GET', 'POST']) # <--- ALTERADO: AGORA ACEITA GET E POST
def webhook_mercado_pago():
    print(f"DEBUG WEBHOOK MP: Recebida requisição para /webhook/mercado-pago. Method: {request.method}")

    # Se for GET (geralmente teste do Mercado Pago)
    if request.method == 'GET':
        print("DEBUG WEBHOOK MP: Requisição GET de teste do Mercado Pago recebida. Respondendo 200 OK.")
        # O Mercado Pago testa com GET, precisamos responder 200 para ele considerar o webhook configurado
        return jsonify({'status': 'ok_test_webhook'}), 200
    
    # Se for POST (notificação real do Mercado Pago)
    notification = request.json
    print(f"DEBUG WEBHOOK MP: Corpo da notificação POST: {notification}")

    if notification and notification.get('type') == 'payment':
        print(f"DEBUG WEBHOOK MP: Notificação de pagamento detectada. ID: {notification.get('data', {}).get('id')}")
        payment_id = notification['data']['id']
        payment_info = pagamentos.verificar_status_pagamento(payment_id)
        
        print(f"DEBUG WEBHOOK MP: Status do pagamento verificado: {payment_info.get('status') if payment_info else 'N/A'}")

        if payment_info and payment_info['status'] == 'approved':
            venda_id = payment_info.get('external_reference')
            print(f"DEBUG WEBHOOK MP: Pagamento aprovado. Venda ID (external_reference): {venda_id}")

            if not venda_id:
                print("DEBUG WEBHOOK MP: external_reference não encontrado na notificação. Ignorando.")
                return jsonify({'status': 'ignored_no_external_ref'}), 200
            
            conn = get_db_connection()
            venda = conn.execute('SELECT * FROM vendas WHERE id = ? AND status = ?', (venda_id, 'pendente')).fetchone()

            if venda:
                print(f"DEBUG WEBHOOK MP: Venda {venda_id} encontrada no DB com status 'pendente'.")
                data_venda_dt = datetime.strptime(venda['data_venda'], '%Y-%m-%d %H:%M:%S')
                if datetime.now() > data_venda_dt + timedelta(hours=1):
                    print(f"DEBUG WEBHOOK MP: Pagamento recebido para venda expirada (ID: {venda_id}). Ignorando entrega.")
                    conn.execute('UPDATE vendas SET status = ? WHERE id = ?', ('expirado', venda_id))
                    conn.commit()
                    conn.close()
                    return jsonify({'status': 'expired_and_ignored'}), 200

                payer_info = payment_info.get('payer', {})
                payer_name = f"{payer_info.get('first_name', '')} {payer_info.get('last_name', '')}".strip()
                payer_email = payer_info.get('email')
                conn.execute('UPDATE vendas SET status = ?, payment_id = ?, payer_name = ?, payer_email = ? WHERE id = ?', 
                                 ('aprovado', payment_id, payer_name, payer_email, venda_id))
                conn.commit()
                produto = conn.execute('SELECT * FROM produtos WHERE id = ?', (venda['produto_id'],)).fetchone()
                conn.close()
                if produto:
                    print(f"DEBUG WEBHOOK MP: Enviando produto {produto['nome']} para user {venda['user_id']}.")
                    enviar_produto_telegram(venda['user_id'], produto['nome'], produto['link'])
                print(f"DEBUG WEBHOOK MP: Venda {venda_id} aprovada e entregue com sucesso.")
                return jsonify({'status': 'success'}), 200
            else:
                conn.close()
                print(f"DEBUG WEBHOOK MP: Venda {venda_id} já processada ou não encontrada no DB como 'pendente'.")
                return jsonify({'status': 'already_processed_or_not_pending'}), 200
        else:
            print(f"DEBUG WEBHOOK MP: Pagamento {payment_id} não aprovado ou info inválida. Status: {payment_info.get('status') if payment_info else 'N/A'}")
            return jsonify({'status': 'payment_not_approved'}), 200 # Retorna 200 para o MP
    
    print("DEBUG WEBHOOK MP: Notificação ignorada (não é tipo 'payment' ou JSON inválido).")
    return jsonify({'status': 'ignored_general'}), 200


@app.route('/login', methods=['GET', 'POST'])
def login():
    # Adicione esses prints para depuração de sessão/redirecionamento
    print(f"DEBUG LOGIN: Requisição para /login. Method: {request.method}")
    print(f"DEBUG LOGIN: session.get('logged_in'): {session.get('logged_in')}")

    if session.get('logged_in'): # Se já estiver logado, redireciona para o dashboard
        print("DEBUG LOGIN: Usuário já logado. Redirecionando para index.")
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = get_db_connection()
        admin_user = conn.execute('SELECT * FROM admin WHERE username = ?', (username,)).fetchone()
        conn.close()
        if admin_user and check_password_hash(admin_user['password_hash'], password):
            session['logged_in'] = True
            session['username'] = admin_user['username']
            print(f"DEBUG LOGIN: Login bem-sucedido para {session['username']}. session['logged_in'] = {session.get('logged_in')}")
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha inválidos.', 'danger')
            print("DEBUG LOGIN: Login falhou. Credenciais inválidas.")
    
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
    # Adicione esses prints para depuração de sessão/redirecionamento
    print(f"DEBUG INDEX: Requisição para /. session.get('logged_in'): {session.get('logged_in')}")

    if not session.get('logged_in'):
        print("DEBUG INDEX: Usuário não logado. Redirecionando para login.")
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    total_usuarios = conn.execute('SELECT COUNT(id) FROM users').fetchone()[0]
    total_produtos = conn.execute('SELECT COUNT(id) FROM produtos').fetchone()[0]
    vendas_data = conn.execute("SELECT COUNT(id), SUM(preco) FROM vendas WHERE status = ?", ('aprovado',)).fetchone()
    total_vendas_aprovadas = vendas_data[0] or 0
    receita_total = vendas_data[1] or 0.0
    vendas_recentes = conn.execute("SELECT v.id, u.username, u.first_name, p.nome, v.preco, v.data_venda, CASE WHEN v.status = 'aprovado' THEN 'aprovado' WHEN v.status = 'pendente' AND DATETIME('now', 'localtime', '-1 hour') > DATETIME(v.data_venda) THEN 'expirado' ELSE v.status END AS status FROM vendas v JOIN users u ON v.user_id = u.id JOIN produtos p ON v.produto_id = p.id ORDER BY v.id DESC LIMIT 5").fetchall()
    chart_labels, chart_data = [], []
    today = datetime.now()
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        start_of_day, end_of_day = datetime.combine(day.date(), time.min), datetime.combine(day.date(), time.max)
        chart_labels.append(day.strftime('%d/%m'))
        daily_revenue = conn.execute("SELECT SUM(preco) FROM vendas WHERE status = 'aprovado' AND data_venda BETWEEN ? AND ?", (start_of_day, end_of_day)).fetchone()[0]
        chart_data.append(daily_revenue or 0)
    conn.close()
    print("DEBUG INDEX: Renderizando index.html.")
    return render_template('index.html', total_vendas=total_vendas_aprovadas, total_usuarios=total_usuarios, total_produtos=total_produtos, receita_total=receita_total, vendas_recentes=vendas_recentes, chart_labels=json.dumps(chart_labels), chart_data=json.dumps(chart_data))

@app.route('/produtos', methods=['GET', 'POST'])
def produtos():
    if not session.get('logged_in'): return redirect(url_for('login'))
    if request.method == 'POST':
        nome, preco, link = request.form['nome'], request.form['preco'], request.form['link']
        conn = get_db_connection()
        conn.execute('INSERT INTO produtos (nome, preco, link) VALUES (?, ?, ?)', (nome, preco, link))
        conn.commit()
        conn.close()
        flash('Produto adicionado com sucesso!', 'success')
        return redirect(url_for('produtos'))
    conn = get_db_connection()
    lista_produtos = conn.execute('SELECT * FROM produtos ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('produtos.html', produtos=lista_produtos)

@app.route('/edit_product/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    produto = conn.execute('SELECT * FROM produtos WHERE id = ?', (id,)).fetchone()
    if request.method == 'POST':
        nome, preco, link = request.form['nome'], request.form['preco'], request.form['link']
        conn.execute('UPDATE produtos SET nome = ?, preco = ?, link = ? WHERE id = ?', (nome, preco, link, id))
        conn.commit()
        conn.close()
        flash('Produto atualizado com sucesso!', 'success')
        return redirect(url_for('produtos'))
    conn.close()
    return render_template('edit_product.html', produto=produto)

@app.route('/remove_product/<int:id>')
def remove_product(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM produtos WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Produto removido com sucesso!', 'danger')
    return redirect(url_for('produtos'))

@app.route('/vendas')
def vendas():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    produtos_disponiveis = conn.execute('SELECT id, nome FROM produtos ORDER BY nome').fetchall()
    query_base = "SELECT T.* FROM (SELECT v.id, u.username, u.first_name, p.nome, v.preco, v.data_venda, p.id as produto_id, CASE WHEN v.status = 'aprovado' THEN 'aprovado' WHEN v.status = 'pendente' AND DATETIME('now', 'localtime', '-1 hour') > DATETIME(v.data_venda) THEN 'expirado' ELSE v.status END AS status FROM vendas v JOIN users u ON v.user_id = u.id JOIN produtos p ON v.produto_id = p.id) AS T"
    conditions, params = [], []
    data_inicio_str, data_fim_str, pesquisa_str, produto_id_str, status_str = (request.args.get('data_inicio'), request.args.get('data_fim'), request.args.get('pesquisa'), request.args.get('produto_id'), request.args.get('status'))
    if data_inicio_str: conditions.append("DATE(T.data_venda) >= ?"); params.append(data_inicio_str)
    if data_fim_str: conditions.append("DATE(T.data_venda) <= ?"); params.append(data_fim_str)
    if pesquisa_str: conditions.append("(T.username LIKE ? OR T.nome LIKE ? OR T.first_name LIKE ?)"); params.extend([f'%{pesquisa_str}%'] * 3)
    if produto_id_str: conditions.append("T.produto_id = ?"); params.append(produto_id_str)
    if status_str: conditions.append("T.status = ?"); params.append(status_str)