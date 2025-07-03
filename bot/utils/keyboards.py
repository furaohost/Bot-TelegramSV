from telebot import types

def menu_principal():
    """
    Cria o teclado de menu principal para o bot.
    Agora apenas com "Melhores vips".
    """
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Botão "Melhores vips"
    btn_melhores_vips = types.KeyboardButton("🎁 Melhores vips") 
    
    # Botão "Comunidades" - REMOVIDO DA ADIÇÃO
    # btn_comunidades = types.KeyboardButton("👥 Comunidades") 
    
    # Adiciona apenas o botão "Melhores vips"
    markup.add(btn_melhores_vips) # Apenas um botão agora
    
    return markup

def confirm_18_keyboard():
    """
    Cria um teclado inline para confirmar idade maior de 18 anos.
    """
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_yes = types.InlineKeyboardButton("Sim, tenho 18+", callback_data="confirm_18_yes")
    btn_no = types.InlineKeyboardButton("Não, sou menor", callback_data="confirm_18_no")
    markup.add(btn_yes, btn_no)
    return markup