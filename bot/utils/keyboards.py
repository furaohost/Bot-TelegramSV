from telebot import types

def menu_principal():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("🗓 Agendar")
    btn2 = types.KeyboardButton("🔞 Conteúdo")
    btn3 = types.KeyboardButton("🎁 Produtos")
    btn4 = types.KeyboardButton("👥 Comunidades")
    markup.add(btn1, btn2, btn3, btn4)
    return markup

def confirm_18_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🎁 Produtos", callback_data="produtos")
    )
    return markup

