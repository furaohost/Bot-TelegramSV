import telebot
from telebot import types
from telebot.types import Message
import traceback
import base64
import sqlite3
from datetime import datetime
import pagamentos

def register_produtos_handlers(bot: telebot.TeleBot, get_db_connection):

    def mostrar_produtos_bot(chat_id):
        conn = None
        try:
            conn = get_db_connection()
            if conn is None:
                bot.send_message(chat_id, "Erro ao conectar ao banco de dados.")
                return

            is_sqlite = isinstance(conn, sqlite3.Connection)
            with conn:
                cur = conn.cursor()
                cur.execute('SELECT * FROM produtos ORDER BY nome')
                produtos = cur.fetchall()

                if not produtos:
                    bot.send_message(chat_id, "Nenhum produto disponível.")
                    return

                for produto in produtos:
                    markup = types.InlineKeyboardMarkup()
                    try:
                        preco_formatado = f"R${float(produto['preco']):.2f}"
                    except:
                        preco_formatado = "R$?.??"

                    btn_comprar = types.InlineKeyboardButton(
                        f"Comprar por {preco_formatado}",
                        callback_data=f"comprar_{produto['id']}"
                    )
                    markup.add(btn_comprar)

                    nome_produto = produto.get('nome', 'Sem nome')
                    descricao = produto.get('descricao', '')
                    texto = f"🛍 *{nome_produto}*\n\nPreço: {preco_formatado}"
                    if descricao:
                        texto += f"\n\n_{descricao}_"

                    bot.send_message(chat_id, texto, parse_mode='Markdown', reply_markup=markup)

        except Exception as e:
            traceback.print_exc()
            bot.send_message(chat_id, "Erro ao carregar os produtos.")
        finally:
            if conn: conn.close()

    def generar_cobranca(call: types.CallbackQuery, produto_id: int):
        user_id, chat_id = call.from_user.id, call.message.chat.id
        conn = None
        venda_id = None
        try:
            conn = get_db_connection()
            if conn is None:
                bot.send_message(chat_id, "Erro ao conectar ao banco de dados.")
                return

            is_sqlite = isinstance(conn, sqlite3.Connection)
            with conn:
                cur = conn.cursor()
                placeholder = "%s" if not is_sqlite else "?"
                cur.execute(f'SELECT * FROM produtos WHERE id = {placeholder}', (produto_id,))
                produto = cur.fetchone()

                if not produto:
                    bot.send_message(chat_id, "Produto não encontrado.")
                    return

                data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if is_sqlite:
                    cur.execute(
                        "INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (?, ?, ?, ?, ?)",
                        (user_id, produto['id'], produto['preco'], 'pendente', data_venda)
                    )
                    cur.execute("SELECT last_insert_rowid()")
                    venda_id = cur.fetchone()[0]
                else:
                    cur.execute(
                        "INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                        (user_id, produto['id'], produto['preco'], 'pendente', data_venda)
                    )
                    venda_id = cur.fetchone()[0]

                pagamento = pagamentos.criar_pagamento_pix(produto=produto, user=call.from_user, venda_id=venda_id)

                if pagamento and 'point_of_interaction' in pagamento:
                    qr_base64 = pagamento['point_of_interaction']['transaction_data']['qr_code_base64']
                    qr_code = pagamento['point_of_interaction']['transaction_data']['qr_code']
                    qr_img = base64.b64decode(qr_base64)

                    caption = (
                        f"✅ PIX gerado para *{produto['nome']}*!\n\n"
                        "Escaneie o QR Code ou copie o código abaixo:"
                    )
                    bot.send_photo(chat_id, qr_img, caption=caption, parse_mode='Markdown')
                    bot.send_message(chat_id, f"```{qr_code}```", parse_mode='Markdown')
                    bot.send_message(chat_id, "Você receberá o conteúdo assim que o pagamento for confirmado.")
                else:
                    bot.send_message(chat_id, "Erro ao gerar o pagamento.")
        except Exception as e:
            traceback.print_exc()
            bot.send_message(chat_id, "Erro ao gerar cobrança.")
        finally:
            if conn: conn.close()

    @bot.message_handler(func=lambda message: message.text and message.text.lower() == "produtos")
    def handle_show_products(message: Message):
        print(f"[DEBUG] Usuário pediu produtos: {message.chat.id}")
        mostrar_produtos_bot(message.chat.id)

    @bot.callback_query_handler(func=lambda call: call.data == "produtos")
    def handle_callback_produtos(call: types.CallbackQuery):
        print(f"[DEBUG] Callback produtos: {call.message.chat.id}")
        mostrar_produtos_bot(call.message.chat.id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("comprar_"))
    def handle_buy(call: types.CallbackQuery):
        try:
            produto_id = int(call.data.split("_")[1])
            generar_cobranca(call, produto_id)
        except Exception as e:
            traceback.print_exc()
            bot.answer_callback_query(call.id, "Erro ao processar sua compra.")
