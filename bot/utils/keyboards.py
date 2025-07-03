from telebot import types

def menu_principal():
    """
    Cria o teclado de menu principal para o bot.
    Agora apenas com "Melhores vips".
    Corrigido para melhor compatibilidade com iOS (row_width=1).
    """
    # MUDANÇA AQUI: row_width=1 pois você só tem um botão nesta linha
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1) 
    
    # Botão "Melhores vips"
    btn_melhores_vips = types.KeyboardButton("🎁 Melhores Vips e Novinhas") 
    
    # Adiciona o botão
    markup.add(btn_melhores_vips) 
    
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