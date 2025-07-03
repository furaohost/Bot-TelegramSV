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

# É crucial que `generar_cobranca` seja importada de `app` se ela estiver definida lá globalmente
# conforme o seu `app.py` mais recente.
from app import generar_cobranca as app_generar_cobranca 

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
                # CORREÇÃO AQUI: Incluído 'link' e 'descricao' na query SELECT
                cur.execute('SELECT id, nome, preco, link, descricao FROM produtos ORDER BY nome') 
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
                    # Agora a descrição será sempre selecionada, então pode acessar diretamente
                    descricao = produto.get("descricao", "") # Use .get() para segurança caso a coluna seja NULL
                    
                    texto = f"🛍 *{nome}*\n\nPreço: {preco_formatado}"
                    if descricao: # Adiciona descrição se existir
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
    # HANDLER para o botão "🎁 Melhores Vips e Novinhas"
    # ------------------------------------------------------------------
    @bot_instance.message_handler(func=lambda message: message.text and message.text.lower() == "🎁 melhores vips e novinhas".lower())
    def handle_show_melhores_vips(message: Message):
        logger.debug(f"HANDLER ACIONADO: 'handle_show_melhores_vips' acionado pelo texto: '{message.text}'")
        mostrar_produtos_bot(message.chat.id)

    # ------------------------------------------------------------------
    # HANDLER para callbacks de compra (botões inline)
    # ------------------------------------------------------------------
    @bot_instance.callback_query_handler(func=lambda call: call.data.startswith('comprar_'))
    def handle_buy_callback(call: types.CallbackQuery):
        logger.debug(f"Callback de compra acionado: {call.data}")
        try:
            produto_id = int(call.data.split('_')[1])
            # Chama a função generar_cobranca definida no app.py
            app_generar_cobranca(call, produto_id) 
        except Exception as e:
            bot_instance.answer_callback_query(call.id, "Erro ao processar a compra.")
            logger.error(f"Erro em handle_buy_callback: {e}", exc_info=True)