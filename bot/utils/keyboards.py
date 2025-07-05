from telebot import types

def menu_principal():
    """
    Cria o teclado de menu principal para o bot.
    Retorna None, pois o botão de produtos agora é inline e não faz parte do ReplyKeyboard.
    """
    # Se não houver outros botões de ReplyKeyboard que você queira exibir,
    # esta função pode simplesmente retornar None.
    # Se houver outros botões de menu fixos, adicione-os aqui.
    # Ex: markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    #     markup.add(types.KeyboardButton("Outra Opção"))
    #     return markup
    return None 

def inline_ver_produtos_keyboard():
    """
    Cria um teclado inline com o botão "Melhores Vips e Novinhas".
    Este é o botão que você quer que apareça diretamente na mensagem.
    """
    markup = types.InlineKeyboardMarkup(row_width=1)
    # O callback_data "ver_produtos_inline" será usado em bot/handlers/produtos.py
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