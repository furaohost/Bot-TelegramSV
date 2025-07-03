from telebot import types

def menu_principal():
    """
    Cria o teclado de menu principal para o bot.
    Este teclado agora será opcional e pode ser vazio se não houver outros itens de menu.
    O botão "Melhores Vips e Novinhas" será inline.
    """
    # Se não houver outros botões de ReplyKeyboard, você pode até remover este markup
    # e simplesmente não passar reply_markup no bot.send_message.
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1) 
    
    # EXEMPLO: Se quiser manter outros botões de menu aqui
    # btn_outra_opcao = types.KeyboardButton("Outra Opção do Menu")
    # markup.add(btn_outra_opcao)
    
    # Se você não tem mais nenhum botão ReplyKeyboard, você pode retornar None ou um Markup vazio.
    # Por simplicidade, se não houver mais botões, vamos retornar None.
    # Se você tiver mais botões além de "Melhores Vips", adicione-os aqui.
    
    # Por enquanto, se não houver outros botões de ReplyKeyboardMarkup além do de produtos,
    # podemos fazer esta função retornar None.
    return None # Nenhuma ReplyKeyboardMarkup será enviada por padrão.

def inline_ver_produtos_keyboard():
    """
    Cria um teclado inline com o botão "Ver Produtos".
    """
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_ver_produtos = types.InlineKeyboardButton("🎁 Melhores Vips e Novinhas", callback_data="ver_produtos_inline")
    markup.add(btn_ver_produtos)
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