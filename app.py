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
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'uma_chave_padrao_muito_segura')
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

@app.route('/webhook/mercado-pago', methods=['POST'])
def webhook_mercado_pago():
    notification = request.json
    if notification and notification.get('type') == 'payment':
        payment_id = notification['data']['id']
        payment_info = pagamentos.verificar_status_pagamento(payment_id)
        if payment_info and payment_info['status'] == 'approved':
            venda_id = payment_info.get('external_reference')
            if not venda_id: return jsonify({'status': 'ignored'}), 200
            
            conn = get_db_connection()
            venda = conn.execute('SELECT * FROM vendas WHERE id = ? AND status = ?', (venda_id, 'pendente')).fetchone()

            if venda:
                data_venda_dt = datetime.strptime(venda['data_venda'], '%Y-%m-%d %H:%M:%S')
                if datetime.now() > data_venda_dt + timedelta(hours=1):
                    print(f"Pagamento recebido para venda expirada (ID: {venda_id}). Ignorando entrega.")
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
                    enviar_produto_telegram(venda['user_id'], produto['nome'], produto['link'])
                return jsonify({'status': 'success'}), 200
            else:
                conn.close()
                return jsonify({'status': 'already_processed'}), 200
    return jsonify({'status': 'ignored'}), 200


@app.route('/login', methods=['GET', 'POST'])
def login():
    if not session.get('logged_in'): return redirect(url_for('index'))
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        conn = get_db_connection()
        admin_user = conn.execute('SELECT * FROM admin WHERE username = ?', (username,)).fetchone()
        conn.close()
        if admin_user and check_password_hash(admin_user['password_hash'], password):
            session['logged_in'], session['username'] = True, admin_user['username']
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha inválidos.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

@app.route('/')
def index():
    if not session.get('logged_in'): return redirect(url_for('login'))
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
    if conditions: query_base += " WHERE " + " AND ".join(conditions)
    query_base += " ORDER BY T.id DESC"
    lista_vendas = conn.execute(query_base, tuple(params)).fetchall()
    conn.close()
    return render_template('vendas.html', vendas=lista_vendas, produtos_disponiveis=produtos_disponiveis)

@app.route('/venda_detalhes/<int:id>')
def venda_detalhes(id):
    if not session.get('logged_in'): return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db_connection()
    venda = conn.execute('SELECT * FROM vendas WHERE id = ?', (id,)).fetchone()
    conn.close()
    if venda: return jsonify(dict(venda))
    return jsonify({'error': 'Not Found'}), 404

@app.route('/usuarios')
def usuarios():
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    lista_usuarios = conn.execute('SELECT * FROM users ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('usuarios.html', usuarios=lista_usuarios)

@app.route('/remove_user/<int:id>')
def remove_user(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Usuário removido com sucesso!', 'danger')
    return redirect(url_for('usuarios'))

@app.route('/pagamento/<status>')
def pagamento_retorno(status):
    mensagem = "Status do Pagamento: "
    if status == 'sucesso': mensagem += "Aprovado com sucesso!"
    elif status == 'falha': mensagem += "Pagamento falhou."
    elif status == 'pendente': mensagem += "Pagamento pendente."
    return f"<div style='font-family: sans-serif; text-align: center; padding-top: 50px;'><h1>{mensagem}</h1><p>Você pode fechar esta janela e voltar para o Telegram.</p></div>"

# --- ROTA PARA MENSAGENS DE BOAS-VINDAS (NOVA) ---
@app.route('/config_messages', methods=['GET', 'POST'])
def config_messages():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    # Obter a mensagem atual de boas-vindas do bot
    current_welcome_message_bot = conn.execute("SELECT value FROM config WHERE key = ?", ('welcome_message_bot',)).fetchone()
    current_welcome_message_bot = current_welcome_message_bot[0] if current_welcome_message_bot else ''

    if request.method == 'POST':
        new_message = request.form['welcome_message_bot']
        # Atualizar a mensagem no banco de dados
        conn.execute("UPDATE config SET value = ? WHERE key = ?", (new_message, 'welcome_message_bot'))
        conn.commit()
        flash('Mensagem de boas-vindas do bot atualizada com sucesso!', 'success')
        conn.close()
        return redirect(url_for('config_messages'))

    conn.close()
    return render_template('config_messages.html', welcome_message_bot=current_welcome_message_bot)

# --- COMANDOS DO BOT ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    get_or_register_user(message.from_user)
    
    conn = get_db_connection()
    # Obter a mensagem de boas-vindas do banco de dados
    welcome_message = conn.execute("SELECT value FROM config WHERE key = ?", ('welcome_message_bot',)).fetchone()
    conn.close()

    # Usar a mensagem do DB ou um padrão
    # Substituir {first_name} pelo nome real do usuário
    final_message = "Olá! Bem-vindo(a)." # Mensagem padrão de fallback
    if welcome_message:
        final_message = welcome_message[0].replace('{first_name}', message.from_user.first_name or 'usuário')
    else:
        final_message = f"Olá, {message.from_user.first_name or 'usuário'}! Bem-vindo(a)." # Fallback se não encontrar no DB

    markup = types.InlineKeyboardMarkup()
    btn_produtos = types.InlineKeyboardButton("🛍️ Ver Produtos", callback_data='ver_produtos')
    markup.add(btn_produtos)
    # Usar final_message aqui
    bot.reply_to(message, final_message, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    get_or_register_user(call.from_user)
    if call.data == 'ver_produtos':
        mostrar_produtos(call.message.chat.id)
    elif call.data.startswith('comprar_'):
        produto_id = int(call.data.split('_')[1])
        gerar_cobranca(call, produto_id)

def mostrar_produtos(chat_id):
    conn = get_db_connection()
    produtos = conn.execute('SELECT * FROM produtos').fetchall()
    conn.close()
    if not produtos:
        bot.send_message(chat_id, "Nenhum produto disponível.")
        return
    for produto in produtos:
        markup = types.InlineKeyboardMarkup()
        btn_comprar = types.InlineKeyboardButton(f"Comprar por R${produto['preco']:.2f}", callback_data=f"comprar_{produto['id']}")
        markup.add(btn_comprar)
        bot.send_message(chat_id, f"💎 *{produto['nome']}*\n\nPreço: R${produto['preco']:.2f}", parse_mode='Markdown', reply_markup=markup)

def gerar_cobranca(call: types.CallbackQuery, produto_id: int):
    user_id, chat_id = call.from_user.id, call.message.chat.id
    conn = get_db_connection()
    produto = conn.execute('SELECT * FROM produtos WHERE id = ?', (produto_id,)).fetchone()
    if not produto:
        bot.send_message(chat_id, "Produto não encontrado.")
        conn.close()
        return
    data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (?, ?, ?, ?, ?)",
                     (user.id, produto_id, produto['preco'], 'pendente', data_venda))
    conn.commit()
    venda_id = cursor.lastrowid 
    pagamento = pagamentos.criar_pagamento_pix(produto=produto, user=call.from_user, venda_id=venda_id)
    conn.close()
    if pagamento and 'point_of_interaction' in pagamento:
        qr_code_base64 = pagamento['point_of_interaction']['transaction_data']['qr_code_base64']
        qr_code_data = pagamento['point_of_interaction']['transaction_data']['qr_code']
        qr_code_image = base64.b64decode(qr_code_base64)
        
        # --- LÓGICA DE MENSAGEM ATUALIZADA ---
        caption_text = (
            f"✅ PIX gerado para *{produto['nome']}*!\n\n"
            "Escaneie o QR Code acima ou copie o código completo na próxima mensagem."
        )
        bot.send_photo(chat_id, qr_code_image, caption=caption_text, parse_mode='Markdown')
        
        # Envia o código em uma mensagem separada e sem formatação para garantir a cópia
        bot.send_message(chat_id, qr_code_data)
        
        bot.send_message(chat_id, "Você receberá o produto aqui assim que o pagamento for confirmado.")
    else:
        bot.send_message(chat_id, "Ocorreu um erro ao gerar o PIX. Tente novamente.")
        print(f"[ERRO] Falha ao gerar PIX. Resposta do MP: {pagamento}")

# --- INICIALIZAÇÃO FINAL ---
if __name__ != '__main__':
    # Esta parte só é executada quando rodando na Render (produção)
    try:
        # Inicializar o banco de dados ANTES de qualquer operação que o use
        init_db() # <--- CHAMAR A NOVA FUNÇÃO AQUI

        pagamentos.init_mercadopago_sdk() # Inicializa o SDK do Mercado Pago

        if API_TOKEN and BASE_URL:
            bot.set_webhook(url=f"{BASE_URL}/{API_TOKEN}")
            print("Webhook do Telegram configurado com sucesso!")
        else:
            print("ERRO: Variáveis de ambiente API_TOKEN ou BASE_URL não definidas.")
    except Exception as e:
        print(f"Erro ao configurar o webhook do Telegram ou inicializar Mercado Pago: {e}")