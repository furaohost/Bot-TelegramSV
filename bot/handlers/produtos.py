@bot.message_handler(func=lambda message: message.text == "Ofertas")
def handle_ofertas(message: Message):
    chat_id = message.chat.id
    mostrar_produtos_bot(chat_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("comprar_"))
def processar_compra(call):
    produto_id = call.data.split("_")[1]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,))
    produto = cur.fetchone()

    if not produto:
        bot.send_message(call.message.chat.id, "Produto não encontrado.")
        return

    preco = float(produto["preco"])
    nome = produto["nome"]

    # Criar pagamento Mercado Pago
    link_pagamento, qr_code, copia_cola = pagamentos.gerar_pagamento(
        user_id=call.from_user.id,
        produto_id=produto_id,
        nome_produto=nome,
        valor=preco
    )

    texto = f"💸 *{nome}*\nValor: R${preco:.2f}\n\nClique no botão abaixo para pagar:"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔗 Pagar", url=link_pagamento))
    bot.send_message(call.message.chat.id, texto, parse_mode="Markdown", reply_markup=markup)
