import telebot
from telebot import types
from telebot.types import Message
import traceback
import base64
import psycopg2
from psycopg2.extras import RealDictCursor # Importar RealDictCursor para PostgreSQL
import sqlite3 # Importar sqlite3 para verificar tipo de conexão
from datetime import datetime
import pagamentos
import logging # Importar logging

# Configuração de logging para este módulo
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG) # Nível de debug para ver logs detalhados

def register_produtos_handlers(bot_instance: telebot.TeleBot, get_db_connection_func):
    """
    Registra os manipuladores (handlers) de comandos relacionados a produtos no bot.
    Args:
        bot_instance (telebot.TeleBot): A instância do bot.
        get_db_connection_func (function): Função para obter a conexão do DB.
    """

    def mostrar_produtos_bot(chat_id):
        logger.debug(f"Chamado mostrar_produtos_bot para chat_id: {chat_id}")
        conn = None
        try:
            conn = get_db_connection_func() # Usar a função passada como argumento
            if conn is None:
                bot_instance.send_message(chat_id, "Erro interno: banco de dados indisponível.")
                logger.error("Erro: Conexão com o banco de dados é None em mostrar_produtos_bot.")
                return

            is_postgres = isinstance(conn, psycopg2.extensions.connection)
            if is_postgres:
                # Se for PostgreSQL, garantir que o cursor retorne dicionários
                cur = conn.cursor(cursor_factory=RealDictCursor)
            else:
                # Para SQLite, usar a função dict_factory se não estiver globalmente configurado
                # Assumindo que get_db_connection_func já configura row_factory para SQLite no app.py
                cur = conn.cursor() 

            with conn: # Gerencia a transação
                cur.execute('SELECT id, nome, preco, descricao FROM produtos ORDER BY nome')
                produtos = cur.fetchall()

                if not produtos:
                    bot_instance.send_message(chat_id, "Nenhum produto disponível no momento.")
                    logger.info("Nenhum produto encontrado na tabela 'produtos'.")
                    return

                for produto in produtos:
                    markup = types.InlineKeyboardMarkup()
                    preco_formatado = f"R${float(produto['preco']):.2f}".replace('.', ',') # Formatar para BR
                    btn_comprar = types.InlineKeyboardButton(f"Comprar por {preco_formatado}", callback_data=f"comprar_{produto['id']}")
                    markup.add(btn_comprar)

                    nome = produto.get("nome", "Sem nome")
                    descricao = produto.get("descricao", "")
                    texto = f"🛍 *{nome}*\n\nPreço: {preco_formatado}"
                    if descricao:
                        texto += f"\n\n_{descricao}_"

                    bot_instance.send_message(chat_id, texto, parse_mode='Markdown', reply_markup=markup)
                    logger.debug(f"Produto '{nome}' enviado para {chat_id}.")

        except Exception as e:
            bot_instance.send_message(chat_id, "Erro ao listar produtos. Tente novamente.")
            logger.error(f"Erro em mostrar_produtos_bot: {e}", exc_info=True)
        finally:
            if conn:
                conn.close()

    # ------------------------------------------------------------------
    # HANDLER para o botão "🔥 Melhores vips"
    # ------------------------------------------------------------------
    @bot_instance.message_handler(func=lambda message: message.text and "🔥 melhores vips" in message.text.lower())
    def handle_show_melhores_vips(message: Message):
        logger.debug(f"HANDLER ACIONADO: 'handle_show_melhores_vips' acionado pelo texto: '{message.text}'") # NOVO LOG
        mostrar_produtos_bot(message.chat.id)

    # ------------------------------------------------------------------
    # HANDLER para callbacks de compra (botões inline)
    # ------------------------------------------------------------------
    @bot_instance.callback_query_handler(func=lambda call: call.data.startswith('comprar_'))
    def handle_buy_callback(call: types.CallbackQuery):
        logger.debug(f"Callback de compra acionado: {call.data}")
        try:
            produto_id = int(call.data.split('_')[1])
            generar_cobranca(call, produto_id)
        except Exception as e:
            bot_instance.answer_callback_query(call.id, "Erro ao processar a compra.")
            logger.error(f"Erro em handle_buy_callback: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # FUNÇÃO para gerar cobrança (PIX)
    # ------------------------------------------------------------------
    def generar_cobranca(call: types.CallbackQuery, produto_id: int):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        conn = None
        venda_id = None

        logger.debug(f"Gerando cobrança para produto_id: {produto_id}, user_id: {user_id}")

        try:
            conn = get_db_connection_func() # Usar a função passada como argumento
            if conn is None:
                bot_instance.send_message(chat_id, "Erro interno ao acessar o banco de dados para gerar cobrança.")
                logger.error("Erro: Conexão com o banco de dados é None em generar_cobranca.")
                return

            is_postgres = isinstance(conn, psycopg2.extensions.connection)
            with conn:
                # Garante que o cursor retorne dicionários para produtos e vendas
                cur = conn.cursor(cursor_factory=RealDictCursor if is_postgres else None)
                
                cur.execute("SELECT id, nome, preco FROM produtos WHERE id = %s" if is_postgres else "SELECT id, nome, preco FROM produtos WHERE id = ?", (produto_id,))
                produto = cur.fetchone()

                if not produto:
                    bot_instance.send_message(chat_id, "Produto não encontrado.")
                    logger.warning(f"Produto com ID {produto_id} não encontrado para gerar cobrança.")
                    return

                data_venda = datetime.now()
                insert_query = """
                    INSERT INTO vendas (user_id, produto_id, preco, status, data_venda)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id
                """ if is_postgres else """
                    INSERT INTO vendas (user_id, produto_id, preco, status, data_venda)
                    VALUES (?, ?, ?, ?, ?)
                """
                insert_params = (user_id, produto['id'], produto['preco'], 'pendente', data_venda)

                cur.execute(insert_query, insert_params)
                if is_postgres:
                    venda_id = cur.fetchone()['id']
                else: # SQLite
                    cur.execute("SELECT last_insert_rowid()")
                    venda_id = cur.fetchone()[0]
                
                logger.debug(f"Venda {venda_id} registrada como 'pendente'.")

                pagamento = pagamentos.criar_pagamento_pix(produto=produto, user=call.from_user, venda_id=venda_id)

                if pagamento and 'point_of_interaction' in pagamento:
                    qr_code_base64 = pagamento['point_of_interaction']['transaction_data']['qr_code_base64']
                    qr_code_data = pagamento['point_of_interaction']['transaction_data']['qr_code']
                    qr_code_image = base64.b64decode(qr_code_base64)

                    caption_text = (
                        f"✅ PIX gerado para *{produto['nome']}*!\n\n"
                        "Escaneie o QR Code acima ou copie o código completo na próxima mensagem."
                    )
                    bot_instance.send_photo(chat_id, qr_code_image, caption=caption_text, parse_mode='Markdown')
                    bot_instance.send_message(chat_id, f"```{qr_code_data}```", parse_mode='Markdown')
                    bot_instance.send_message(chat_id, "Você receberá o produto aqui assim que o pagamento for confirmado.")
                    logger.info(f"PIX gerado e enviado para {chat_id} para venda {venda_id}.")
                else:
                    bot_instance.send_message(chat_id, "Ocorreu um erro ao gerar o PIX. Tente novamente.")
                    logger.error(f"Falha ao gerar PIX para venda {venda_id}. Resposta do MP: {pagamento}")

        except Exception as e:
            bot_instance.send_message(chat_id, "Erro ao gerar cobrança.")
            logger.error(f"Erro em generar_cobranca para produto_id {produto_id}: {e}", exc_info=True)
        finally:
            if conn:
                conn.close()