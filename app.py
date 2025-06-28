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
# Assegure que estes ficheiros estão na pasta 'database/'
from database.database import get_db_connection
from database.db_init import init_db # Importa a função de inicialização do DB

# Importa o módulo de pagamentos do Mercado Pago
import pagamentos

# Importa os módulos de handlers e blueprints da Sprint 1 (Funcionalidades de Comunidades)
# Assegure que estes ficheiros existem nas pastas especificadas
from bot.handlers.comunidades import register_comunidades_handlers
from web.routes.comunidades import create_comunidades_blueprint

# Se tiver outros handlers/blueprints de futuras Sprints, importe-os aqui:
# from bot.handlers.chamadas import register_chamadas_handlers
# from bot.handlers.ofertas import register_ofertas_handlers
# from bot.handlers.conteudos import register_conteudos_handlers


# ────────────────────────────────────────────────────────────────────
# 1. CONFIGURAÇÃO INICIAL (Leitura de Variáveis de Ambiente)
# ────────────────────────────────────────────────────────────────────
# Carrega variáveis de ambiente do ficheiro .env (apenas para desenvolvimento local)
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
# 2. INICIALIZAÇÃO DO FLASK E DO BOT
# ────────────────────────────────────────────────────────────────────
# Inicializa a aplicação Flask, especificando os diretórios de templates e estáticos
app = Flask(__name__, template_folder='web/templates', static_folder='web/static')
app.secret_key = FLASK_SECRET_KEY # Chave secreta para sessões Flask
# Inicializa o bot TeleBot. threaded=False é necessário para o uso com webhooks.
bot = telebot.TeleBot(API_TOKEN, threaded=False, parse_mode='Markdown')


# ────────────────────────────────────────────────────────────────────
# 3. FUNÇÕES DE UTILIDADE DE BANCO DE DADOS
# ────────────────────────────────────────────────────────────────────
def get_or_register_user(user: types.User):
    """
    Verifica se um utilizador do Telegram existe na base de dados e o regista se não existir.
    Usa a conexão da DB centralizada (get_db_connection).
    Args:
        user (telebot.types.User): Objeto de utilizador do Telegram.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            print("ERRO DB: get_or_register_user - Não foi possível obter conexão com a base de dados.")
            return

        with conn.cursor() as cur:
            is_sqlite = isinstance(conn, sqlite3.Connection)
            # Verifica se o utilizador já existe
            cur.execute("SELECT id, is_active FROM users WHERE id = %s" if not is_sqlite else "SELECT id, is_active FROM users WHERE id = ?", (user.id,))
            db_user = cur.fetchone()

            if db_user is None:
                # O utilizador não existe, então o regista. data_registro é DEFAULT CURRENT_TIMESTAMP na DB.
                cur.execute("INSERT INTO users (id, username, first_name, last_name, is_active) VALUES (%s, %s, %s, %s, %s)" if not is_sqlite else "INSERT INTO users (id, username, first_name, last_name, is_active) VALUES (?, ?, ?, ?, ?)",
                            (user.id, user.username, user.first_name, user.last_name, True))
                conn.commit()
                print(f"DEBUG DB: Novo utilizador registado: {user.username or user.first_name} (ID: {user.id})")
            else:
                # Se o utilizador existe mas estava inativo, reativa-o
                if not db_user['is_active']:
                    cur.execute("UPDATE users SET is_active = %s WHERE id = %s" if not is_sqlite else "UPDATE users SET is_active = ? WHERE id = ?", (True, user.id))
                    conn.commit()
                    print(f"DEBUG DB: Utilizador reativado: {user.username or user.first_name} (ID: {user.id})")

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
        user_id (int): O ID do utilizador do Telegram.
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
# 4. FILTROS JINJA2 (para templates HTML)
# ────────────────────────────────────────────────────────────────────
@app.template_filter('datetimeformat')
def format_datetime(value, format="%d/%m/%Y %H:%M:%S"):
    """
    Filtro Jinja2 para formatar objetos datetime.
    Deteta se o valor é string (SQLite) ou datetime (PostgreSQL/Python) e formata.
    """
    if isinstance(value, str):
        try:
            # Tenta analisar do formato ISO (usado por SQLite ou PostgreSQL TEXT)
            # ou de outros formatos comummente usados
            if 'T' in value and ('+' in value or '-' == value[-6:]): # Ex: 2023-10-26T10:00:00.000000+00:00
                dt_obj = datetime.fromisoformat(value)
            elif ' ' in value and '.' in value: # Ex: 2023-10-26 10:00:00.123456
                dt_obj = datetime.strptime(value.split('.')[0], "%Y-%m-%d %H:%M:%S")
            else: # Formato simples ISO 8601 sem milissegundos ou fuso horário
                dt_obj = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return value # Retorna o valor original se não conseguir formatar
    elif isinstance(value, datetime):
        dt_obj = value
    else:
        return value # Retorna o valor original para outros tipos
    
    return dt_obj.strftime(format)

# Adiciona o filtro ao ambiente Jinja2 do Flask
app.jinja_env.filters['datetimeformat'] = format_datetime


# ────────────────────────────────────────────────────────────────────
# 5. ROTAS DO PAINEL WEB (FLASK)
# ────────────────────────────────────────────────────────────────────

@app.route(f"/{API_TOKEN}", methods=['POST'])
def telegram_webhook():
    """
    Endpoint para o webhook do Telegram. Recebe as atualizações do bot.
    O caminho da rota é o API_TOKEN para maior segurança.
    """
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_str)
        bot.process_new_updates([update]) # Envia a atualização para o bot TeleBot processar
        return '!', 200 # Responde OK para o Telegram
    else:
        return "Unsupported Media Type", 415 # Retorna erro se o tipo de conteúdo não for JSON

@app.route('/webhook/mercado-pago', methods=['GET', 'POST'])
def webhook_mercado_pago():
    """
    Endpoint para o webhook do Mercado Pago. Processa notificações de pagamento.
    Lida com testes GET e notificações POST de pagamentos aprovados.
    """
    print(f"DEBUG WEBHOOK MP: Recebida requisição para /webhook/mercado-pago. Method: {request.method}")

    if request.method == 'GET':
        # Responde a requisições GET (geralmente usadas pelo Mercado Pago para testar o webhook)
        print("DEBUG WEBHOOK MP: Requisição GET de teste do Mercado Pago recebida. Respondendo 200 OK.")
        return jsonify({'status': 'ok_test_webhook'}), 200

    notification = request.json # Pega o corpo da requisição JSON
    print(f"DEBUG WEBHOOK MP: Corpo da notificação POST: {notification}")

    if notification and notification.get('type') == 'payment':
        print(f"DEBUG WEBHOOK MP: Notificação de pagamento detetada. ID: {notification.get('data', {}).get('id')}")
        payment_id = notification['data']['id']
        # Verifica o estado do pagamento diretamente com a API do Mercado Pago
        payment_info = pagamentos.verificar_status_pagamento(payment_id)

        print(f"DEBUG WEBHOOK MP: Estado do pagamento verificado: {payment_info.get('status') if payment_info else 'N/A'}")

        if payment_info and payment_info['status'] == 'approved':
            conn = None
            try:
                conn = get_db_connection()
                if conn is None:
                    print("ERRO WEBHOOK MP: Não foi possível obter conexão com a base de dados.")
                    return jsonify({'status': 'db_connection_error'}), 500

                with conn.cursor() as cur:
                    is_sqlite = isinstance(conn, sqlite3.Connection)
                    venda_id = payment_info.get('external_reference') # 'external_reference' deve conter o ID da venda
                    print(f"DEBUG WEBHOOK MP: Pagamento aprovado. Venda ID (external_reference): {venda_id}")

                    if not venda_id:
                        print("DEBUG WEBHOOK MP: external_reference não encontrado na notificação. Ignorando.")
                        return jsonify({'status': 'ignored_no_external_ref'}), 200

                    # Verifica se a venda está pendente na DB
                    cur.execute('SELECT * FROM vendas WHERE id = %s AND status = %s' if not is_sqlite else 'SELECT * FROM vendas WHERE id = ? AND status = ?', (venda_id, 'pendente'))
                    venda = cur.fetchone()

                    if venda:
                        print(f"DEBUG WEBHOOK MP: Venda {venda_id} encontrada na DB com estado 'pendente'.")
                        
                        # Converte data_venda para datetime para comparação (compatível com SQLite e PostgreSQL)
                        if isinstance(venda['data_venda'], str): # SQLite retorna string
                            data_venda_dt = datetime.fromisoformat(venda['data_venda'])
                        elif isinstance(venda['data_venda'], datetime): # PostgreSQL retorna datetime
                            data_venda_dt = venda['data_venda']
                        else: # Fallback
                            data_venda_dt = datetime.min # Valor mínimo para evitar erro

                        # Verifica se a venda não expirou (ex: limite de 1 hora para pagamento PIX)
                        # Assumindo que a data_venda está em UTC ou no mesmo fuso horário do servidor
                        if datetime.now() > data_venda_dt + timedelta(hours=1):
                            print(f"DEBUG WEBHOOK MP: Pagamento recebido para venda expirada (ID: {venda_id}). Ignorando entrega.")
                            cur.execute('UPDATE vendas SET status = %s WHERE id = %s' if not is_sqlite else 'UPDATE vendas SET status = ? WHERE id = ?', ('expirado', venda_id))
                            conn.commit()
                            return jsonify({'status': 'expired_and_ignored'}), 200

                        # Atualiza o estado da venda para 'aprovado' e armazena dados do pagador
                        payer_info = payment_info.get('payer', {})
                        payer_name = f"{payer_info.get('first_name', '')} {payer_info.get('last_name', '')}".strip()
                        payer_email = payer_info.get('email')

                        cur.execute('UPDATE vendas SET status = %s, payment_id = %s, payer_name = %s, payer_email = %s WHERE id = %s' if not is_sqlite else 'UPDATE vendas SET status = ?, payment_id = ?, payer_name = ?, payer_email = ? WHERE id = ?',
                                         ('aprovado', payment_id, payer_name, payer_email, venda_id))
                        conn.commit()

                        # Busca o produto associado para enviar ao utilizador
                        cur.execute('SELECT * FROM produtos WHERE id = %s' if not is_sqlite else 'SELECT * FROM produtos WHERE id = ?', (venda['produto_id'],))
                        produto = cur.fetchone()

                        if produto:
                            print(f"DEBUG WEBHOOK MP: Enviando produto '{produto['nome']}' para user {venda['user_id']}.")
                            enviar_produto_telegram(venda['user_id'], produto['nome'], produto['link'])
                        
                        print(f"DEBUG WEBHOOK MP: Venda {venda_id} aprovada e entregue com sucesso.")
                        return jsonify({'status': 'success'}), 200
                    else:
                        print(f"DEBUG WEBHOOK MP: Venda {venda_id} já processada ou não encontrada na DB como 'pendente'.")
                        return jsonify({'status': 'already_processed_or_not_pending'}), 200
            except Exception as e:
                print(f"ERRO WEBHOOK MP: Erro no processamento da notificação de pagamento: {e}")
                traceback.print_exc()
                if conn and not conn.closed:
                    conn.rollback() # Reverte a transação em caso de erro
                return jsonify({'status': 'error_processing_webhook'}), 500
            finally:
                if conn:
                    conn.close()
        else:
            print(f"DEBUG WEBHOOK MP: Pagamento {payment_id} não aprovado ou info inválida. Estado: {payment_info.get('status') if payment_info else 'N/A'}")
            return jsonify({'status': 'payment_not_approved'}), 200

    print("DEBUG WEBHOOK MP: Notificação ignorada (não é tipo 'payment' ou JSON inválido).")
    return jsonify({'status': 'ignored_general'}), 200


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Rota de login para o painel administrativo.
    Lida com a exibição do formulário (GET) e o processamento do login (POST).
    """
    print(f"DEBUG LOGIN: Requisição para /login. Method: {request.method}")
    
    # Se o utilizador já estiver logado, redireciona para a página principal
    if session.get('logged_in'):
        print("DEBUG LOGIN: Utilizador já logado. Redirecionando para index.")
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = None
        try:
            conn = get_db_connection()
            if conn is None:
                flash('Erro de conexão com a base de dados.', 'error') # Usar 'error' para estilização com Tailwind
                return render_template('login.html')

            with conn.cursor() as cur:
                is_sqlite = isinstance(conn, sqlite3.Connection)
                cur.execute('SELECT * FROM admin WHERE username = %s' if not is_sqlite else 'SELECT * FROM admin WHERE username = ?', (username,))
                admin_user = cur.fetchone()

                if admin_user and check_password_hash(admin_user['password_hash'], password):
                    session['logged_in'] = True
                    session['username'] = admin_user['username']
                    print(f"DEBUG LOGIN: Login bem-sucedido para {session['username']}.")
                    flash("Login realizado com sucesso!", "success")
                    return redirect(url_for('index')) # Redireciona para a página principal
                else:
                    flash('Utilizador ou senha inválidos.', 'error') # Usar 'error' para estilização com Tailwind
                    print("DEBUG LOGIN: Login falhou. Credenciais inválidas.")
        except Exception as e:
            print(f"ERRO LOGIN: Falha no processo de login: {e}")
            traceback.print_exc()
            flash('Erro no servidor ao tentar login.', 'error')
            if conn and not conn.closed:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    print("DEBUG LOGIN: Renderizando login.html.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    """
    Rota para deslogar o utilizador do painel administrativo.
    Limpa a sessão e redireciona para a página de login.
    """
    print(f"DEBUG LOGOUT: Desconectando utilizador {session.get('username')}.")
    session.clear() # Limpa todos os dados da sessão
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('login'))

@app.before_request
def require_login():
    """
    Middleware que verifica se o utilizador está logado antes de aceder a certas rotas.
    Redireciona para a página de login se não estiver autenticado.
    """
    # Lista de endpoints que NÃO exigem login
    # 'static' para ficheiros estáticos, 'telegram_webhook' para o bot, 'login' para a própria página de login.
    # 'None' pode acontecer para favicon.ico e outras requisições sem endpoint definido.
    if request.endpoint in ['login', 'static', 'telegram_webhook', None]:
        return # Permite acesso

    if not session.get('logged_in'):
        print(f"DEBUG AUTH: Acesso não autorizado para '{request.path}'. Redirecionando para login.")
        return redirect(url_for('login'))

@app.route('/')
def index():
    """
    Página inicial do painel administrativo (dashboard).
    Exibe estatísticas e vendas recentes.
    """
    print(f"DEBUG INDEX: Requisição para /. session.get('logged_in'): {session.get('logged_in')}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com a base de dados.', 'error')
            return redirect(url_for('login'))

        with conn.cursor() as cur:
            is_sqlite = isinstance(conn, sqlite3.Connection)
            # Total de utilizadores
            cur.execute('SELECT COUNT(id) AS count FROM users')
            total_usuarios_row = cur.fetchone()
            total_usuarios = total_usuarios_row['count'] if total_usuarios_row and total_usuarios_row['count'] is not None else 0

            # Total de produtos
            cur.execute('SELECT COUNT(id) AS count FROM produtos')
            total_produtos_row = cur.fetchone()
            total_produtos = total_produtos_row['count'] if total_produtos_row and total_produtos_row['count'] is not None else 0

            # Vendas aprovadas e receita total
            cur.execute("SELECT COUNT(id) AS count, SUM(preco) AS sum FROM vendas WHERE status = %s" if not is_sqlite else "SELECT COUNT(id) AS count, SUM(preco) AS sum FROM vendas WHERE status = ?", ('aprovado',))
            vendas_data_row = cur.fetchone()
            total_vendas_aprovadas = vendas_data_row['count'] if vendas_data_row and vendas_data_row['count'] is not None else 0
            receita_total = float(vendas_data_row['sum']) if vendas_data_row and vendas_data_row['sum'] is not None else 0.0

            # Vendas recentes (LIMIT 5)
            # A lógica CASE WHEN para estado 'expirado' é adaptada para SQLite e PostgreSQL
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

            # Dados para o gráfico de receita diária (últimos 7 dias)
            chart_labels, chart_data = [], []
            today = datetime.now().date() # Apenas a data
            for i in range(6, -1, -1): # Ciclo de 7 dias (hoje até 6 dias atrás)
                day = today - timedelta(days=i)
                # Define o início e fim do dia para a consulta
                start_of_day = datetime.combine(day, time.min)
                end_of_day = datetime.combine(day, time.max)
                chart_labels.append(day.strftime('%d/%m')) # Formato da *label* (dia/mês)

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
                daily_revenue = float(daily_revenue_row['sum']) if daily_revenue_row and daily_revenue_row['sum'] is not None else 0
                chart_data.append(daily_revenue)

            print("DEBUG INDEX: Renderizando index.html com dados do dashboard.")
            return render_template(
                'index.html', 
                total_vendas=total_vendas_aprovadas, 
                total_usuarios=total_usuarios, 
                total_produtos=total_produtos, 
                receita_total=receita_total, 
                vendas_recentes=vendas_recentes, 
                chart_labels=json.dumps(chart_labels), # JSON.dumps para passar para JS
                chart_data=json.dumps(chart_data)      # JSON.dumps para passar para JS
            )
    except Exception as e:
        print(f"ERRO INDEX: Falha ao renderizar o dashboard: {e}")
        traceback.print_exc()
        flash('Erro ao carregar o dashboard.', 'error')
        return redirect(url_for('login')) # Redireciona para o login em caso de erro grave
    finally:
        if conn:
            conn.close()

@app.route('/produtos', methods=['GET', 'POST'])
def produtos():
    """
    Rota para gerenciar produtos (adicionar, listar).
    Apenas acessível para utilizadores logados.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com a base de dados.', 'error')
            return redirect(url_for('index'))

        with conn.cursor() as cur:
            is_sqlite = isinstance(conn, sqlite3.Connection)
            if request.method == 'POST':
                nome = request.form.get('nome').strip()
                preco_str = request.form.get('preco')
                link = request.form.get('link').strip()

                if not nome or not preco_str or not link:
                    flash('Todos os campos (Nome, Preço, Link) são obrigatórios.', 'error')
                    cur.execute('SELECT * FROM produtos ORDER BY id DESC')
                    lista_produtos = cur.fetchall()
                    # Passa os valores de volta para o template para pré-preencher o formulário
                    return render_template('produtos.html', produtos=lista_produtos, 
                                           nome_input=nome, preco_input=preco_str, link_input=link)
                
                try:
                    preco = float(preco_str)
                    if preco <= 0:
                        flash('O preço deve ser um valor positivo.', 'error')
                        cur.execute('SELECT * FROM produtos ORDER BY id DESC')
                        lista_produtos = cur.fetchall()
                        return render_template('produtos.html', produtos=lista_produtos, 
                                               nome_input=nome, preco_input=preco_str, link_input=link)
                except ValueError:
                    flash('Preço inválido. Use um número (ex: 19.99).', 'error')
                    cur.execute('SELECT * FROM produtos ORDER BY id DESC')
                    lista_produtos = cur.fetchall()
                    return render_template('produtos.html', produtos=lista_produtos, 
                                           nome_input=nome, preco_input=preco_str, link_input=link)

                cur.execute('INSERT INTO produtos (nome, preco, link) VALUES (%s, %s, %s)' if not is_sqlite else 'INSERT INTO produtos (nome, preco, link) VALUES (?, ?, ?)', (nome, preco, link))
                conn.commit()
                flash('Produto adicionado com sucesso!', 'success')
                return redirect(url_for('produtos'))

            cur.execute('SELECT * FROM produtos ORDER BY id DESC')
            lista_produtos = cur.fetchall()
            return render_template('produtos.html', produtos=lista_produtos)
    except Exception as e:
        print(f"ERRO PRODUTOS: Falha ao gerenciar produtos: {e}")
        traceback.print_exc()
        flash('Erro ao carregar ou adicionar produtos.', 'error')
        if conn and not conn.closed:
            conn.rollback()
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()

@app.route('/edit_product/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    """
    Rota para editar um produto existente.
    Apenas acessível para utilizadores logados.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com a base de dados.', 'error')
            return redirect(url_for('produtos'))

        with conn.cursor() as cur:
            is_sqlite = isinstance(conn, sqlite3.Connection)
            cur.execute('SELECT * FROM produtos WHERE id = %s' if not is_sqlite else 'SELECT * FROM produtos WHERE id = ?', (id,))
            produto = cur.fetchone()

            if not produto:
                flash('Produto não encontrado.', 'error')
                return redirect(url_for('produtos'))

            if request.method == 'POST':
                nome = request.form.get('nome').strip()
                preco_str = request.form.get('preco')
                link = request.form.get('link').strip()

                if not nome or not preco_str or not link:
                    flash('Todos os campos (Nome, Preço, Link) são obrigatórios.', 'error')
                    return render_template('edit_product.html', produto=produto) # Volta para o form com erro
                
                try:
                    preco = float(preco_str)
                    if preco <= 0:
                        flash('O preço deve ser um valor positivo.', 'error')
                        return render_template('edit_product.html', produto=produto)
                except ValueError:
                    flash('Preço inválido. Use um número (ex: 19.99).', 'error')
                    return render_template('edit_product.html', produto=produto)

                cur.execute('UPDATE produtos SET nome = %s, preco = %s, link = %s WHERE id = %s' if not is_sqlite else 'UPDATE produtos SET nome = ?, preco = ?, link = ? WHERE id = ?', (nome, preco, link, id))
                conn.commit()
                flash('Produto atualizado com sucesso!', 'success')
                return redirect(url_for('produtos'))
            
            # Para GET request, apenas renderiza o formulário com os dados do produto
            return render_template('edit_product.html', produto=produto)
    except Exception as e:
        print(f"ERRO EDIT PRODUTO: Falha ao editar produto: {e}")
        traceback.print_exc()
        flash('Erro ao carregar ou editar produto.', 'error')
        if conn and not conn.closed:
            conn.rollback()
        return redirect(url_for('produtos'))
    finally:
        if conn:
            conn.close()

@app.route('/remove_product/<int:id>')
def remove_product(id):
    """
    Rota para remover um produto da base de dados.
    Apenas acessível para utilizadores logados.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com a base de dados.', 'error')
            return redirect(url_for('produtos'))

        with conn.cursor() as cur:
            is_sqlite = isinstance(conn, sqlite3.Connection)
            cur.execute('DELETE FROM produtos WHERE id = %s' if not is_sqlite else 'DELETE FROM produtos WHERE id = ?', (id,))
            conn.commit()
            flash('Produto removido com sucesso!', 'success') # Mudei para 'success' pois foi uma ação bem-sucedida
            return redirect(url_for('produtos'))
    except Exception as e:
        print(f"ERRO REMOVE PRODUTO: Falha ao remover produto: {e}")
        traceback.print_exc()
        flash('Erro ao remover produto.', 'error')
        if conn and not conn.closed:
            conn.rollback()
        return redirect(url_for('produtos'))
    finally:
        if conn:
            conn.close()

@app.route('/vendas')
def vendas():
    """
    Rota para visualizar e filtrar a lista de vendas.
    Apenas acessível para utilizadores logados.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com a base de dados.', 'error')
            return redirect(url_for('index'))

        with conn.cursor() as cur:
            is_sqlite = isinstance(conn, sqlite3.Connection)
            # Busca produtos disponíveis para o filtro
            cur.execute('SELECT id, nome FROM produtos ORDER BY nome')
            produtos_disponiveis = cur.fetchall()

            # Base da query SQL para vendas
            query_base = """
                SELECT
                    v.id,
                    u.username,
                    u.first_name,
                    p.nome,
                    v.preco,
                    v.data_venda,
                    p.id AS produto_id,
                    CASE
                        WHEN v.status = 'aprovado' THEN 'aprovado'
                        WHEN v.status = 'pendente' """
            
            if is_sqlite:
                query_base += " AND (strftime('%s', 'now') - strftime('%s', v.data_venda)) > 3600 THEN 'expirado'"
            else: # PostgreSQL
                query_base += " AND EXTRACT(EPOCH FROM (NOW() AT TIME ZONE 'UTC' - v.data_venda)) > 3600 THEN 'expirado'" # NOW() AT TIME ZONE 'UTC' para consistência
            
            query_base += """
                        ELSE v.status
                    END AS status
                FROM vendas v
                JOIN users u ON v.user_id = u.id
                JOIN produtos p ON v.produto_id = p.id
            """
            conditions = []
            params = []
            
            # Parâmetros de filtro da requisição GET
            data_inicio_str = request.args.get('data_inicio')
            data_fim_str = request.args.get('data_fim')
            pesquisa_str = request.args.get('pesquisa')
            produto_id_str = request.args.get('produto_id')
            status_str = request.args.get('status')

            # Adiciona condições à query base com base nos filtros
            if data_inicio_str:
                conditions.append("DATE(v.data_venda) >= %s" if not is_sqlite else "DATE(v.data_venda) >= ?")
                params.append(data_inicio_str)
            if data_fim_str:
                conditions.append("DATE(v.data_venda) <= %s" if not is_sqlite else "DATE(v.data_venda) <= ?")
                params.append(data_fim_str)
            if pesquisa_str:
                # ILIKE para case-insensitive no PostgreSQL, LIKE para SQLite (case-insensitive por padrão)
                conditions.append("(u.username {} %s OR p.nome {} %s OR u.first_name {} %s)".format("ILIKE" if not is_sqlite else "LIKE"))
                params.extend([f'%{pesquisa_str}%'] * 3)
            if produto_id_str:
                conditions.append("p.id = %s" if not is_sqlite else "p.id = ?")
                params.append(int(produto_id_str)) # Converte para int para comparação
            if status_str:
                conditions.append("v.status = %s" if not is_sqlite else "v.status = ?")
                params.append(status_str)

            if conditions:
                query_base += " WHERE " + " AND ".join(conditions)
            
            # Ordenação
            query_base += " ORDER BY v.id DESC"

            cur.execute(query_base, tuple(params))
            
            lista_vendas = cur.fetchall()
            return render_template('vendas.html', vendas=lista_vendas, produtos_disponiveis=produtos_disponiveis)
    except Exception as e:
        print(f"ERRO VENDAS: Falha ao carregar vendas: {e}")
        traceback.print_exc()
        flash('Erro ao carregar vendas.', 'error')
        if conn and not conn.closed:
            conn.rollback()
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()

@app.route('/venda_detalhes/<int:id>')
def venda_detalhes(id):
    """
    Rota para obter detalhes de uma venda específica via API (JSON).
    Apenas acessível para utilizadores logados.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({'error': 'Erro de conexão com a base de dados'}), 500

        with conn.cursor() as cur:
            is_sqlite = isinstance(conn, sqlite3.Connection)
            cur.execute('SELECT * FROM vendas WHERE id = %s' if not is_sqlite else 'SELECT * FROM vendas WHERE id = ?', (id,))
            
            venda = cur.fetchone()
            if venda:
                # Converte o objeto Row/RealDictRow para um dicionário para jsonify
                # Garante que campos como data_venda são serializáveis para JSON
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
    """
    Rota para listar todos os utilizadores do bot.
    Apenas acessível para utilizadores logados.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com a base de dados.', 'error')
            return redirect(url_for('index'))

        with conn.cursor() as cur:
            is_sqlite = isinstance(conn, sqlite3.Connection)
            cur.execute('SELECT * FROM users ORDER BY id DESC')
            
            lista_usuarios = cur.fetchall()
            return render_template('usuarios.html', usuarios=lista_usuarios)
    except Exception as e:
        print(f"ERRO UTILIZADORES: Falha ao carregar utilizadores: {e}")
        traceback.print_exc()
        flash('Erro ao carregar utilizadores.', 'error')
        if conn and not conn.closed:
            conn.rollback()
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()

@app.route('/remove_user/<int:id>')
def remove_user(id):
    """
    Rota para remover um utilizador da base de dados.
    Apenas acessível para utilizadores logados.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com a base de dados.', 'error')
            return redirect(url_for('usuarios'))

        with conn.cursor() as cur:
            is_sqlite = isinstance(conn, sqlite3.Connection)
            # Remova vendas e outros dados relacionados ao utilizador para manter a integridade referencial
            if is_sqlite:
                cur.execute('DELETE FROM vendas WHERE user_id = ?', (id,))
                cur.execute('DELETE FROM users WHERE id = ?', (id,))
            else: # PostgreSQL
                cur.execute('DELETE FROM vendas WHERE user_id = %s', (id,))
                cur.execute('DELETE FROM users WHERE id = %s', (id,))
            conn.commit()
            flash('Utilizador e dados relacionados removidos com sucesso!', 'success')
            return redirect(url_for('usuarios'))
    except Exception as e:
        print(f"ERRO REMOVER UTILIZADOR: Falha ao remover utilizador: {e}")
        traceback.print_exc()
        flash('Erro ao remover utilizador.', 'error')
        if conn and not conn.closed:
            conn.rollback()
        return redirect(url_for('usuarios'))
    finally:
        if conn:
            conn.close()

@app.route('/pagamento/<status>')
def pagamento_retorno(status):
    """
    Rota para exibir o estado de retorno de pagamento (pós-redirecionamento do Mercado Pago).
    """
    mensagem = "Estado do Pagamento: "
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
        <title>Estado do Pagamento</title>
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
    Apenas acessível para utilizadores logados.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com a base de dados.', 'error')
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

                # Atualiza a mensagem na base de dados
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
# 6. COMANDOS DO BOT TELEGRAM
# ────────────────────────────────────────────────────────────────────

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """
    Handler para o comando /start. Regista o utilizador e envia uma mensagem de boas-vindas.
    """
    get_or_register_user(message.from_user) # Garante que o utilizador está na DB

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            bot.reply_to(message, "Ocorreu um erro ao iniciar o bot. Tente novamente mais tarde.")
            return

        with conn.cursor() as cur:
            is_sqlite = isinstance(conn, sqlite3.Connection)
            # Obtém a mensagem de boas-vindas configurada na DB
            cur.execute("SELECT value FROM config WHERE key = %s" if not is_sqlite else "SELECT value FROM config WHERE key = ?", ('welcome_message_bot',))
            
            welcome_message_row = cur.fetchone()
            final_message = "Olá! Bem-vindo(a)." # *Fallback* padrão

            if welcome_message_row:
                # Substitui o *placeholder* {first_name} pelo nome do utilizador
                final_message = welcome_message_row['value'].replace(
                    '{first_name}', message.from_user.first_name or 'utilizador'
                )
            else:
                final_message = f"Olá, {message.from_user.first_name or 'utilizador'}! Bem-vindo(a)."

            # Cria botões *inline* para interação
            markup = types.InlineKeyboardMarkup()
            btn_produtos = types.InlineKeyboardButton("🛍️ Ver Produtos", callback_data='ver_produtos')
            markup.add(btn_produtos)
            bot.reply_to(message, final_message, reply_markup=markup, parse_mode='Markdown')
    except Exception as e:
        print(f"ERRO START: Falha ao enviar mensagem de boas-vindas: {e}")
        traceback.print_exc()
        bot.reply_to(message, "Ocorreu um erro ao iniciar o bot. Tente novamente mais tarde.")
    finally:
        if conn:
            conn.close()

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    """
    Handler para processar *callback queries* de botões *inline*.
    """
    get_or_register_user(call.from_user) # Garante que o utilizador está na DB

    if call.data == 'ver_produtos':
        mostrar_produtos(call.message.chat.id)
    elif call.data.startswith('comprar_'):
        try:
            produto_id = int(call.data.split('_')[1])
            gerar_cobranca(call, produto_id)
        except ValueError:
            print(f"ERRO CALLBACK: ID de produto inválido na callback_data: {call.data}")
            bot.answer_callback_query(call.id, "Erro ao processar sua requisição. Tente novamente.")


def mostrar_produtos(chat_id):
    """
    Envia uma mensagem ao utilizador com a lista de produtos disponíveis para compra.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            bot.send_message(chat_id, "Ocorreu um erro ao carregar os produtos.")
            return

        with conn.cursor() as cur:
            is_sqlite = isinstance(conn, sqlite3.Connection)
            cur.execute('SELECT * FROM produtos')
            
            produtos = cur.fetchall()

            if not produtos:
                bot.send_message(chat_id, "Nenhum produto disponível no momento.")
                return

            for produto in produtos:
                markup = types.InlineKeyboardMarkup()
                # Formata o preço para 2 casas decimais
                btn_comprar = types.InlineKeyboardButton(f"Comprar por R${produto['preco']:.2f}", callback_data=f"comprar_{produto['id']}")
                markup.add(btn_comprar)
                bot.send_message(
                    chat_id, 
                    f"💎 *{produto['nome']}*\n\nPreço: R${produto['preco']:.2f}", 
                    parse_mode='Markdown', 
                    reply_markup=markup
                )
    except Exception as e:
        print(f"ERRO MOSTRAR PRODUTOS: Falha ao mostrar produtos: {e}")
        traceback.print_exc()
        bot.send_message(chat_id, "Ocorreu um erro ao carregar os produtos.")
    finally:
        if conn:
            conn.close()

def gerar_cobranca(call: types.CallbackQuery, produto_id: int):
    """
    Gera uma cobrança PIX via Mercado Pago e envia o QR Code/código PIX ao utilizador.
    Regista a venda na base de dados como 'pendente'.
    """
    user_id, chat_id = call.from_user.id, call.message.chat.id
    conn = None
    venda_id = None # Inicializa venda_id para garantir que esteja definido em caso de erro no meio da função

    # Responde à *callback query* para remover o "relógio" de carregamento do botão
    bot.answer_callback_query(call.id, "Gerando cobrança PIX...")

    try:
        conn = get_db_connection()
        if conn is None:
            bot.send_message(chat_id, "Ocorreu um erro interno ao gerar sua cobrança. Tente novamente.")
            return

        with conn.cursor() as cur:
            is_sqlite = isinstance(conn, sqlite3.Connection)
            # Busca os detalhes do produto
            cur.execute('SELECT * FROM produtos WHERE id = %s' if not is_sqlite else 'SELECT * FROM produtos WHERE id = ?', (produto_id,))
            produto = cur.fetchone()

            if not produto:
                bot.send_message(chat_id, "Produto não encontrado ou indisponível.")
                return

            # Regista a venda como 'pendente'
            data_venda = datetime.now() # Usar objeto datetime
            if not is_sqlite:
                cur.execute("INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                             (user_id, produto['id'], produto['preco'], 'pendente', data_venda))
                venda_id = cur.fetchone()['id'] # No RealDictCursor, é acesso por chave
            else: # SQLite
                cur.execute("INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (?, ?, ?, ?, ?)",
                             (user_id, produto['id'], produto['preco'], 'pendente', data_venda.isoformat()))
                venda_id = cur.lastrowid # Para SQLite, obter o último ID inserido
            
            conn.commit()
            print(f"DEBUG: Venda {venda_id} registada como pendente para o user {user_id}.")

            # Chamar a função do Mercado Pago para criar o pagamento PIX
            pagamento = pagamentos.criar_pagamento_pix(
                produto=dict(produto), # Garante que é um dicionário simples (compatibilidade com pagamentos.py)
                user=call.from_user,
                venda_id=venda_id
            )

            if pagamento and 'point_of_interaction' in pagamento:
                qr_code_base64 = pagamento['point_of_interaction']['transaction_data']['qr_code_base64']
                qr_code_data = pagamento['point_of_interaction']['transaction_data']['qr_code']
                qr_code_image = base64.b64decode(qr_code_base64)

                caption_text = (
                    f"✅ PIX gerado para *{produto['nome']}*!\n\n"
                    "Faça a leitura do QR Code acima ou copie o código completo na próxima mensagem."
                )
                bot.send_photo(chat_id, qr_code_image, caption=caption_text, parse_mode='Markdown')
                bot.send_message(chat_id, f"```\n{qr_code_data}\n```", parse_mode='Markdown') # Formata como bloco de código
                bot.send_message(chat_id, "Você receberá o produto aqui assim que o pagamento for confirmado.")
                print(f"DEBUG: PIX gerado e enviado para {chat_id} (Venda ID: {venda_id}).")
            else:
                bot.send_message(chat_id, "Ocorreu um erro ao gerar o PIX. Tente novamente.")
                print(f"[ERRO] Falha ao gerar PIX para venda {venda_id}. Resposta do MP: {pagamento}")
                # Atualiza a venda para 'falha' se o PIX não pôde ser gerado
                cur.execute("UPDATE vendas SET status = %s WHERE id = %s" if not is_sqlite else "UPDATE vendas SET status = ? WHERE id = ?", ('falha', venda_id))
                conn.commit()

    except Exception as e:
        print(f"ERRO GERAR COBRANCA: Falha ao gerar cobrança/PIX: {e}")
        traceback.print_exc()
        bot.send_message(chat_id, "Ocorreu um erro interno ao gerar sua cobrança. Tente novamente.")
        if conn and not conn.closed:
            conn.rollback() # Reverter apenas se a conexão estiver aberta e erro inesperado
        
        # Se a venda já foi registada, mas o PIX falhou, tenta atualizar o estado para 'falha'
        if venda_id:
            # Reabre a conexão temporariamente para garantir o *commit* do estado de falha
            conn_reopen = None
            try:
                conn_reopen = get_db_connection()
                if isinstance(conn_reopen, sqlite3.Connection):
                    conn_reopen.execute("UPDATE vendas SET status = ? WHERE id = ?", ('falha', venda_id))
                else:
                    conn_reopen.execute("UPDATE vendas SET status = %s WHERE id = %s", ('falha', venda_id))
                conn_reopen.commit()
                print(f"DEBUG: Venda {venda_id} atualizada para 'falha' após erro na geração do PIX.")
            except Exception as e_reopen:
                print(f"ERRO: Falha ao atualizar estado da venda {venda_id} para 'falha' durante tratamento de erro: {e_reopen}")
            finally:
                if conn_reopen: conn_reopen.close()
    finally:
        if conn:
            conn.close()

# ────────────────────────────────────────────────────────────────────
# 7. WORKER de mensagens agendadas (Completo)
# ────────────────────────────────────────────────────────────────────
# Este *worker* será executado numa *thread* separada ou como um processo à parte.
# Para Render, pode precisar de um serviço *worker* separado no Procfile.
def scheduled_message_worker():
    """
    *Worker* que verifica e envia mensagens agendadas para utilizadores.
    É executado numa *thread* separada ou como um processo *worker*.
    """
    print("DEBUG WORKER: Iniciado...")
    while True:
        conn = None
        try:
            conn = get_db_connection()
            if conn is None:
                print("ERRO WORKER: Não foi possível obter conexão com a base de dados. Tentando novamente em 30s...")
                time_module.sleep(30) # Espera antes de tentar novamente
                continue

            with conn.cursor() as cur:
                is_sqlite = isinstance(conn, sqlite3.Connection)
                # Adapta a *query* para SQLite/PostgreSQL
                # Busca mensagens pendentes cuja *schedule_time* já passou
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
                    # Se um *chat_id* específico foi definido na mensagem agendada
                    if row["target_chat_id"]:
                        targets.append(row["target_chat_id"])
                    else:
                        # Caso contrário, envia para todos os utilizadores ativos
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
                                # É crucial que o *image_url* seja um link acessível publicamente
                                bot.send_photo(chat_id, row["image_url"], caption=row["message_text"], parse_mode="Markdown")
                            else:
                                bot.send_message(chat_id, row["message_text"], parse_mode="Markdown")
                            delivered = True # Se chegou aqui, pelo menos uma entrega foi bem-sucedida para o grupo/utilizador
                            print(f"DEBUG WORKER: Mensagem {row['id']} enviada para {chat_id}.")
                        except telebot.apihelper.ApiTelegramException as e:
                            # Lida com erros específicos do Telegram (ex: utilizador bloqueou o bot)
                            print(f"ERRO Telegram API para chat_id {chat_id}: {e}")
                            if "blocked" in str(e).lower() or "not found" in str(e).lower():
                                # Se o utilizador bloqueou o bot, desativa-o
                                if is_sqlite:
                                    cur.execute("UPDATE users SET is_active=0 WHERE id=?", (chat_id,))
                                else: # PostgreSQL
                                    cur.execute("UPDATE users SET is_active=FALSE WHERE id=%s", (chat_id,))
                                conn.commit() # Commita a mudança de estado do utilizador
                        except Exception as e:
                            print(f"ERRO WORKER: Falha ao enviar mensagem {row['id']} para {chat_id}: {e}")
                            traceback.print_exc() # Imprime o *stack trace* completo do erro
                    
                    # Atualiza o estado da mensagem agendada na DB
                    status = "sent" if delivered else "failed"
                    if is_sqlite:
                        cur.execute(
                            "UPDATE scheduled_messages SET status=?, sent_at=? WHERE id=?",
                            (status, datetime.now().isoformat(), row["id"]),
                        )
                    else: # PostgreSQL
                        cur.execute(
                            "UPDATE scheduled_messages SET status=%s, sent_at=NOW() AT TIME ZONE 'UTC' WHERE id=%s",
                            (status, row["id"]),
                        )
                conn.commit() # Confirma todas as atualizações de estado de mensagens agendadas
        except Exception as e:
            print(f"ERRO WORKER Principal: {e}")
            traceback.print_exc()
            if conn:
                conn.rollback() # Reverte em caso de erro no *worker*
        finally:
            if conn:
                conn.close()
        
        # Espera antes da próxima verificação (ajuste conforme a necessidade)
        time_module.sleep(30) # Verifica a cada 30 segundos

# ────────────────────────────────────────────────────────────────────
# 8. INICIALIZAÇÃO FINAL E EXECUÇÃO
# ────────────────────────────────────────────────────────────────────

# Condição para execução em ambiente de produção (Render) ou localmente
if __name__ != '__main__':
    # Esta parte é executada quando a aplicação é importada por um servidor WSGI (ex: gunicorn no Render)
    print("DEBUG: Executando em modo de produção (gunicorn/Render).")
    try:
        init_db() # Inicializa a base de dados (cria tabelas se não existirem)

        # Inicializa o SDK do Mercado Pago
        pagamentos.init_mercadopago_sdk()

        # Configura o *webhook* do Telegram
        if API_TOKEN and BASE_URL:
            webhook_url = f"{BASE_URL}/{API_TOKEN}"
            bot.set_webhook(url=webhook_url)
            print(f"DEBUG: *Webhook* do Telegram configurado para: {webhook_url}")
        else:
            print("ERRO: Variáveis de ambiente API_TOKEN ou BASE_URL não definidas para *webhook*. O bot pode não receber atualizações.")

        # Em um ambiente de produção com *gunicorn*, o *worker* de agendamento
        # geralmente é executado como um processo separado via Procfile.
        # Não inicie uma *thread* aqui se o Render já gere um *worker*.
        print("DEBUG: Aplicação Flask pronta. *Worker* agendado não iniciado embutido.")
    except Exception as e:
        print(f"ERRO NA INICIALIZAÇÃO DO SERVIDOR: {e}")
        traceback.print_exc()
        # Pode ser necessário relançar o erro ou registar para o sistema de registo do Render

else:
    # Esta parte é executada quando o *script* é executado diretamente (desenvolvimento local)
    print("DEBUG: Executando em modo de desenvolvimento local (python app.py).")
    # Inicializa a base de dados (cria tabelas se não existirem)
    init_db()

    # Inicializa o SDK do Mercado Pago (para testes locais)
    pagamentos.init_mercadopago_sdk()

    # Para o desenvolvimento local, geralmente não se usa *webhook*
    # Mas se quiser testar o *webhook* localmente, use *ngrok* ou similar
    # bot.remove_webhook() # Opcional: remover *webhook* para evitar conflitos
    # print("DEBUG: *Webhook* removido para desenvolvimento local.")

    # Inicia o *worker* de mensagens agendadas numa *thread* separada para o desenvolvimento local
    # Em produção, este é um processo separado no Procfile
    worker_thread = Thread(target=scheduled_message_worker)
    worker_thread.daemon = True # Permite que a *thread* seja encerrada quando o programa principal termina
    worker_thread.start()
    print("DEBUG: *Worker* de mensagens agendadas iniciado em *background* (modo local).")

    # Inicia o servidor Flask
    # host='0.0.0.0' para que o Flask seja acessível de fora do *localhost* (se estiver em Docker, por exemplo)
    # port=5000 é a porta padrão, mas pode ser configurada via variável de ambiente 'PORT'
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))

