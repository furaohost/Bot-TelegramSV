import telebot
from telebot import types
from telebot.types import Message
import traceback
import base64
import psycopg2
from psycopg2.extras import RealDictCursor 
import sqlite3 
import logging

# IMPORTANTE: A função `generar_cobranca` será passada como argumento para register_produtos_handlers.
# Portanto, a importação direta de 'app' NÃO é necessária aqui para evitar importação circular.

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG) 

def register_produtos_handlers(bot_instance: telebot.TeleBot, get_db_connection_func, generar_cobranca_func):
    """
    Registra os manipuladores (handlers) de comandos relacionados a produtos no bot.
    Args:
        bot_instance (telebot.TeleBot): A instância do bot.
        get_db_connection_func (function): Função para obter a conexão do DB.
        generar_cobranca_func (function): Função para gerar cobrança (recebida de app.py).
    Returns:
        None: Esta função não precisa retornar nada para o fluxo atual.
    """

    # mostrar_produtos_bot agora é uma função interna usada pelos handlers deste módulo
    def mostrar_produtos_bot(chat_id):
        logger.debug(f"Chamado mostrar_produtos_bot para chat_id: {chat_id}")
        conn = None
        try:
            conn = get_db_connection_func() 
            if conn is None:
                bot_instance.send_message(chat_id, "Erro interno: banco de dados indisponível.")
                logger.error("Erro: Conexão com o banco de dados é None em mostrar_produtos_bot.")
                return

            is_postgres = isinstance(conn, psycopg2.extensions.connection)
            if is_postgres:
                cur = conn.cursor(cursor_factory=RealDictCursor)
            else:
                cur = conn.cursor() 

            with conn: 
                # CORREÇÃO AQUI: Incluído 'link' e 'descricao' na query SELECT
                cur.execute('SELECT id, nome, preco, link, descricao FROM produtos ORDER BY nome') 
                produtos = cur.fetchall()

                if not produtos:
                    bot_instance.send_message(chat_id, "Nenhum produto disponível no momento.")
                    logger.info("Nenhum produto encontrado na tabela 'produtos'.")
                    return

                for produto in produtos:
                    markup = types.InlineKeyboardMarkup()
                    preco_formatado = f"R${float(produto['preco']):.2f}".replace('.', ',')
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
    # NOVO HANDLER PARA O BOTÃO INLINE "Melhores Vips e Novinhas"
    # ------------------------------------------------------------------
    @bot_instance.callback_query_handler(func=lambda call: call.data == "ver_produtos_inline")
    def handle_ver_produtos_inline(call: types.CallbackQuery):
        logger.debug(f"Callback 'ver_produtos_inline' acionado por {call.from_user.first_name}.")
        bot_instance.answer_callback_query(call.id, "Listando produtos...") # Feedback visual para o usuário
        mostrar_produtos_bot(call.message.chat.id)

    # ------------------------------------------------------------------
    # REMOVIDO: HANDLER ANTIGO PARA TEXTO "🎁 Melhores Vips e Novinhas" (ReplyKeyboard)
    # ------------------------------------------------------------------
    # Este handler não é mais necessário porque o botão agora é inline.
    # @bot_instance.message_handler(func=lambda message: message.text and message.text.lower() == "🎁 melhores vips e novinhas".lower())
    # def handle_show_melhores_vips_text_based(message: Message):
    #     logger.debug(f"HANDLER ANTIGO DE TEXTO ACIONADO: 'handle_show_melhores_vips_text_based' acionado pelo texto: '{message.text}'")
    #     mostrar_produtos_bot(message.chat.id)

    # ------------------------------------------------------------------
    # HANDLER para callbacks de compra (botões inline)
    # ------------------------------------------------------------------
    @bot_instance.callback_query_handler(func=lambda call: call.data.startswith('comprar_'))
    def handle_buy_callback(call: types.CallbackQuery):
        logger.debug(f"Callback de compra acionado: {call.data}")
        try:
            produto_id = int(call.data.split('_')[1])
            generar_cobranca_func(call, produto_id) 
        except Exception as e:
            bot_instance.answer_callback_query(call.id, "Erro ao processar a compra.")
            logger.error(f"Erro em handle_buy_callback: {e}", exc_info=True)

    # Não precisa retornar mostrar_produtos_bot para app.py se ele não a chama diretamente
    # return mostrar_produtos_bot