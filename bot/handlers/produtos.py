import telebot
from telebot import types
from telebot.types import Message
import traceback
import base64
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import pagamentos

def register_produtos_handlers(bot: telebot.TeleBot, get_db_connection):

    def mostrar_produtos_bot(chat_id):
        conn = None
        try:
            conn = get_db_connection()
            if conn is None:
                bot.send_message(chat_id, "Erro interno: banco de dados indisponível.")
                return

            is_postgres = isinstance(conn, psycopg2.extensions.connection)
            if is_postgres:
                conn.cursor_factory = RealDictCursor

            with conn:
                cur = conn.cursor()
                cur.execute('SELECT * FROM produtos ORDER BY nome')
                produtos = cur.fetchall()

                if not produtos:
                    bot.send_message(chat_id, "Nenhum produto disponível no momento.")
                    print("[DEBUG] Nenhum produto encontrado na tabela 'produtos'.")
                    return

                for produto in produtos:
                    markup = types.InlineKeyboardMarkup()
                    preco_formatado = f"R${float(produto['preco']):.2f}" if 'preco' in produto else "R$?.??"
                    btn_comprar = types.InlineKeyboardButton(f"Comprar por {preco_formatado}", callback_data=f"comprar_{produto['id']}")
                    markup.add(btn_comprar)

                    nome = produto.get("nome", "Sem nome")
                    descricao = produto.get("descricao", "")
                    texto = f"🛍 *{nome}*\n\nPreço: {preco_formatado}"
                    if descricao:
                        texto += f"\n\n_{descricao}_"

                    bot.send_message(chat_id, texto, parse_mode='Markdown', reply_markup=markup)

        except Exception as e:
            bot.send_message(chat_id, "Erro ao listar produtos. Tente novamente.")
            print("[ERRO mostrar_produtos_bot]", e)
            traceback.print_exc()
        finally:
            if conn:
                conn.close()

    @bot.message_handler(func=lambda message: message.text and 'produtos' in message.text.lower())
    def handle_show_products(message: Message):
        mostrar_produtos_bot(message.chat.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('comprar_'))
    def handle_buy_callback(call: types.CallbackQuery):
        try:
            produto_id = int(call.data.split('_')[1])
            generar_cobranca(call, produto_id)
        except Exception as e:
            bot.answer_callback_query(call.id, "Erro ao processar a compra.")
            print("[ERRO CALLBACK COMPRAR]", e)
            traceback.print_exc()

    def generar_cobranca(call: types.CallbackQuery, produto_id: int):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        conn = None

        try:
            conn = get_db_connection()
            if conn is None:
                bot.send_message(chat_id, "Erro interno ao acessar o banco de dados.")
                return

            is_postgres = isinstance(conn, psycopg2.extensions.connection)
            with conn:
                cur = conn.cursor(cursor_factory=RealDictCursor if is_postgres else None)
                cur.execute("SELECT * FROM produtos WHERE id = %s", (produto_id,))
                produto = cur.fetchone()

                if not produto:
                    bot.send_message(chat_id, "Produto não encontrado.")
                    return

                data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cur.execute("""
                    INSERT INTO vendas (user_id, produto_id, preco, status, data_venda)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id
                """, (user_id, produto['id'], produto['preco'], 'pendente', data_venda))
                venda_id = cur.fetchone()['id']

                pagamento = pagamentos.criar_pagamento_pix(produto=produto, user=call.from_user, venda_id=venda_id)

                if pagamento and 'point_of_interaction' in pagamento:
                    qr_code_base64 = pagamento['point_of_interaction']['transaction_data']['qr_code_base64']
                    qr_code_data = pagamento['point_of_interaction']['transaction_data']['qr_code']
                    qr_code_image = base64.b64decode(qr_code_base64)

                    caption = (
                        f"✅ PIX gerado para *{produto['nome']}*!\n\n"
                        "Escaneie o QR Code ou copie o código abaixo para pagar."
                    )
                    bot.send_photo(chat_id, qr_code_image, caption=caption, parse_mode='Markdown')
                    bot.send_message(chat_id, f"```{qr_code_data}```", parse_mode='Markdown')
                else:
                    bot.send_message(chat_id, "Erro ao gerar o PIX. Tente novamente.")
                    print("[ERRO gerar_cobranca] Pagamento inválido:", pagamento)

        except Exception as e:
            bot.send_message(chat_id, "Erro ao gerar cobrança.")
            print("[ERRO gerar_cobranca]", e)
            traceback.print_exc()
        finally:
            if conn:
                conn.close()
