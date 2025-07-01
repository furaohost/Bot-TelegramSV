from telebot import types

def menu_principal():
    """
    Cria o teclado de menu principal para o bot.
    Agora apenas com "Melhores vips" e "Comunidades".
    """
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Botão "Melhores vips" (anteriormente "Produtos")
    btn_melhores_vips = types.KeyboardButton("🎁 Melhores vips") 
    
    # Botão "Comunidades"
    btn_comunidades = types.KeyboardButton("👥 Comunidades")
    
    # Adiciona apenas os botões desejados: "Melhores vips" e "Comunidades"
    markup.add(btn_melhores_vips, btn_comunidades)
    
    return markup

def confirm_18_keyboard():
    """
    Cria um teclado inline para confirmar idade maior de 18 anos.
    O botão "Produtos" foi renomeado para "Melhores vips".
    """
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_yes = types.InlineKeyboardButton("Sim, tenho 18+", callback_data="confirm_18_yes")
    btn_no = types.InlineKeyboardButton("Não, sou menor", callback_data="confirm_18_no")
    markup.add(btn_yes, btn_no)
    
    # Adicionando o botão "Melhores vips" no teclado inline, conforme a lógica anterior
    # Se este botão deve aparecer APÓS a confirmação de idade, esta lógica deve ser no handler.
    # Se ele deve aparecer junto com a confirmação, ele precisa de um callback_data diferente.
    # Pelo contexto da imagem anterior, o menu principal aparece APÓS o /start.
    # O confirm_18_keyboard é para a validação inicial.
    # Vou manter apenas os botões de confirmação de idade aqui, e o menu principal será o ReplyKeyboardMarkup.
    # Se o botão "Produtos" / "Melhores vips" deve aparecer AQUI, ele precisa de um callback_data específico para ser um inline button.
    # Assumindo que o "Produtos" original no confirm_18_keyboard era um exemplo e não o menu final.
    # Se o intuito era ter um botão "Melhores vips" AQUI, me avise o callback_data que ele deve ter.
    # Por enquanto, removi o botão "Produtos" daqui para evitar confusão com o menu principal.
    return markup
