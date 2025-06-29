# bot/handlers/produtos.py
import telebot
from telebot import types
import traceback
import base64
import sqlite3 # Importar para a verificação de tipo de conexão

# Importa o módulo de pagamentos do Mercado Pago (se ele for usado aqui)
# Certifique-se de que o 'pagamentos' está acessível no sys.path ou mova-o
# para um local acessível, como bot/utils/ ou configure o PYTHONPATH no Render.
# Se pagamentos for um módulo independente no mesmo nível de bot/,
# você precisará garantir que o caminho esteja correto ou que o sistema o encontre.
# Por simplicidade aqui, vou assumir que ele está no diretório raiz do projeto.
import pagamentos

def register_produtos_handlers(bot: telebot.TeleBot, get_db_connection):

    def mostrar_produtos_bot(chat_id):
        conn = None
        try:
            conn = get_db_connection()
            if conn is None:
                bot.send_message(chat_id, "Ocorreu um erro interno ao conectar ao banco de dados para listar produtos.")
                return

            # A função get_db_connection deve retornar uma conexão que suporte
            # o acesso a colunas por nome (Row factory) se você usa `row['nome_coluna']`.
            # Se for psycopg2, ele já faz isso por padrão com DictCursor ou semelhante.
            # Se for sqlite3, você precisa configurar um row_factory:
            # conn.row_factory = sqlite3.Row

            is_sqlite = isinstance(conn, sqlite3.Connection)
            with conn: # Isso gerencia o commit/rollback e close()
                cur = conn.cursor()
                cur.execute('SELECT * FROM produtos ORDER BY nome')
                produtos = cur.fetchall()

                if not produtos:
                    bot.send_message(chat_id, "Nenhum produto disponível no momento.")
                    return

                for produto in produtos:
                    markup = types.InlineKeyboardMarkup()
                    # Certifique-se de que 'preco', 'nome', 'id' existem nos resultados
                    # e que o 'id' é acessível corretamente (produto['id'] ou produto[0] dependendo do fetchall)
                    try:
                        preco_formatado = f"R${float(produto['preco']):.2f}"
                    except (ValueError, KeyError, TypeError):
                        preco_formatado = "R$?.??" # Fallback
                        print(f"AVISO: Preço inválido para o produto {produto.get('nome', 'ID desconhecido')}: {produto.get('preco')}")

                    btn_comprar = types.InlineKeyboardButton(f"Comprar por {preco_formatado}", callback_data=f"comprar_{produto['id']}")
                    markup.add(btn_comprar)

                    # Certifique-se de que 'nome' e 'link' existem
                    nome_produto = produto.get('nome', 'Nome Indisponível')
                    descricao_produto = produto.get('descricao', '') # Assumindo que você pode ter uma coluna de descrição
                    texto_mensagem = f"🛍 *{nome_produto}*\n\nPreço: {preco_formatado}"
                    if descricao_produto:
                        texto_mensagem += f"\n\n_{descricao_produto}_"

                    bot.send_message(chat_id, texto_mensagem, parse_mode='Markdown', reply_markup=markup)

        except Exception as e:
            print(f"ERRO PRODUTOS BOT: Falha ao mostrar produtos: {e}")
            traceback.print_exc()
            bot.send_message(chat_id, "Ocorreu um erro ao carregar os produtos. Tente novamente mais tarde.")
        finally:
            if conn: conn.close()

    # Mova a função generar_cobranca para cá também, se ela for relevante para o bot e produtos
    # Se gerar_cobranca está em app.py e usa mostrar_produtos_bot, reavalie a dependência.
    # Por agora, vou assumir que ela precisa estar aqui.

    def generar_cobranca(call: types.CallbackQuery, produto_id: int):
        user_id, chat_id = call.from_user.id, call.message.chat.id
        conn = None
        venda_id = None
        try:
            conn = get_db_connection()
            if conn is None:
                bot.send_message(chat_id, "Ocorreu um erro interno ao conectar ao banco de dados para gerar cobrança.")
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
                    cur.execute("INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (?, ?, ?, ?, ?)",
                                    (user_id, produto['id'], produto['preco'], 'pendente', data_venda))
                    cur.execute("SELECT last_insert_rowid()")
                    venda_id = cur.fetchone()[0]
                else:
                    cur.execute("INSERT INTO vendas (user_id, produto_id, preco, status, data_venda) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                                    (user_id, produto['id'], produto['preco'], 'pendente', data_venda))
                    venda_id = cur.fetchone()[0]

                # pagamentos.criar_pagamento_pix precisa do MERCADOPAGO_ACCESS_TOKEN.
                # Como essa função está fora de app.py, você precisaria passar o token
                # ou ter pagamentos.py importando-o de os.getenv.
                # Assumindo que pagamentos.py já faz a inicialização correta com o token.
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

                    bot.send_message(chat_id, f"```{qr_code_data}```", parse_mode='Markdown') # Use Markdown para monospaced code

                    bot.send_message(chat_id, "Você receberá o produto aqui assim que o pagamento for confirmado.")
                else:
                    bot.send_message(chat_id, "Ocorreu um erro ao gerar o PIX. Tente novamente.")
                    print(f"[ERRO] Falha ao gerar PIX. Resposta do MP: {pagamento}")
        except Exception as e:
            print(f"ERRO GENERAR COBRANCA: Falha ao gerar cobrança/PIX: {e}")
            traceback.print_exc()
            bot.send_message(chat_id, "Ocorreu um erro interno ao gerar sua cobrança. Tente novamente.")
        finally:
            if conn: conn.close()


    # Handler para o botão "Ofertas" (ou "Produtos", "Comprar") do teclado principal
    @bot.message_handler(func=lambda message: message.text == "Ofertas") # Mantenha "Ofertas" ou mude para o texto exato do seu botão
    def handle_show_products(message: Message):
        mostrar_produtos_bot(message.chat.id)

    # Handler para o callback de "comprar" (botão inline)
    @bot.callback_query_handler(func=lambda call: call.data.startswith('comprar_'))
    def handle_buy_callback(call: types.CallbackQuery):
        try:
            produto_id = int(call.data.split('_')[1])
            generar_cobranca(call, produto_id)
        except ValueError:
            bot.answer_callback_query(call.id, "Erro: ID do produto inválido.")
            print(f"ERRO CALLBACK: ID do produto inválido em {call.data}")
        except Exception as e:
            bot.answer_callback_query(call.id, "Ocorreu um erro ao processar sua compra.")
            print(f"ERRO CALLBACK: Falha ao processar compra para {call.from_user.id}: {e}")
            traceback.print_exc()
        finally:
            bot.answer_callback_query(call.id) # Sempre responda ao callback_query