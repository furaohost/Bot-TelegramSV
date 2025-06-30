import telebot
from telebot import types
from bot.services.comunidades import ComunidadeService # Importa o serviço de comunidades

# Dicionário temporário para armazenar o estado das conversas
# Em um sistema real, isso seria persistido em cache (Redis, memcached) ou DB.
user_states = {} # Ex: {chat_id: {"step": "awaiting_community_name", "data": {}}}

def register_comunidades_handlers(bot_instance: telebot.TeleBot, get_db_connection_func):
    """
    Registra os manipuladores (handlers) de comandos relacionados a comunidades no bot.
    Args:
        bot_instance (telebot.TeleBot): A instância do bot.
        get_db_connection_func (function): Função para obter a conexão do DB.
    """
    comunidade_svc = ComunidadeService(get_db_connection_func)

    # ------------------------------------------------------------------
    # COMANDO /nova_comunidade
    # ------------------------------------------------------------------
    @bot_instance.message_handler(commands=['nova_comunidade'])
    def handle_nova_comunidade(message):
        chat_id = message.chat.id
        # Verifica se o comando foi enviado em um grupo ou canal, onde ele pode ser útil
        if message.chat.type in ['group', 'supergroup', 'channel']:
            # Pede o nome da comunidade
            msg = bot_instance.send_message(chat_id, "Por favor, digite o *nome* da nova comunidade (ex: 'Comunidade VIP'):", parse_mode='Markdown')
            # Armazena o estado do usuário para o próximo passo
            user_states[chat_id] = {"step": "awaiting_new_community_name", "chat_type": message.chat.type, "chat_title": message.chat.title}
        else:
            bot_instance.send_message(chat_id, "Este comando `/nova_comunidade` deve ser usado dentro de um grupo ou canal que você deseja gerenciar.", parse_mode='Markdown')


    @bot_instance.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("step") == "awaiting_new_community_name")
    def handle_new_community_name(message):
        chat_id = message.chat.id
        nome_comunidade = message.text.strip()

        if not nome_comunidade:
            bot_instance.send_message(chat_id, "O nome da comunidade não pode ser vazio. Por favor, digite o nome:", parse_mode='Markdown')
            return

        # Pede a descrição da comunidade
        msg = bot_instance.send_message(chat_id, f"Nome da comunidade: *{nome_comunidade}*\nAgora, digite uma *descrição* para esta comunidade (opcional, ou 'pular' para deixar em branco):", parse_mode='Markdown')
        
        # Armazena o nome e avança para o próximo passo
        user_states[chat_id]["step"] = "awaiting_new_community_description"
        user_states[chat_id]["data"] = {"nome": nome_comunidade}


    @bot_instance.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("step") == "awaiting_new_community_description")
    def handle_new_community_description(message):
        chat_id = message.chat.id
        descricao_comunidade = message.text.strip()
        
        # Se o usuário digitou "pular", a descrição fica vazia
        if descricao_comunidade.lower() == 'pular':
            descricao_comunidade = None

        # Recupera os dados armazenados
        data = user_states[chat_id]["data"]
        nome_comunidade = data["nome"]
        
        try:
            # Cria a comunidade no DB, usando o chat_id do grupo/canal
            # Se o comando foi iniciado em um grupo, o chat_id é o ID do grupo.
            target_chat_id = chat_id if user_states[chat_id]["chat_type"] in ['group', 'supergroup', 'channel'] else None

            nova_comunidade = comunidade_svc.criar(
                nome=nome_comunidade, 
                descricao=descricao_comunidade, 
                chat_id=target_chat_id
            )

            if nova_comunidade:
                bot_instance.send_message(
                    chat_id, 
                    f"Comunidade *'{nova_comunidade['nome']}'* criada com sucesso!\n"
                    f"ID: `{nova_comunidade['id']}`\n"
                    f"Descrição: {nova_comunidade['descricao'] or 'N/A'}\n"
                    f"Chat ID: `{nova_comunidade['chat_id'] or 'N/A'}`",
                    parse_mode='Markdown'
                )
            else:
                bot_instance.send_message(chat_id, "Ocorreu um erro ao criar a comunidade. Tente novamente mais tarde.", parse_mode='Markdown')
        except Exception as e:
            print(f"Erro ao finalizar criação de comunidade: {e}")
            bot_instance.send_message(chat_id, "Houve um erro inesperado. Por favor, tente novamente.", parse_mode='Markdown')
        finally:
            # Limpa o estado do usuário
            if chat_id in user_states:
                del user_states[chat_id]

    # ------------------------------------------------------------------
    # COMANDO /listar_comunidades
    # ------------------------------------------------------------------
    @bot_instance.message_handler(commands=['listar_comunidades'])
    def handle_listar_comunidades(message):
        chat_id = message.chat.id
        comunidades = comunidade_svc.listar()

        if not comunidades:
            bot_instance.send_message(chat_id, "Nenhuma comunidade encontrada.")
            return

        response_text = "*Comunidades Ativas:*\n\n"
        for idx, com in enumerate(comunidades):
            response_text += (
                f"*{idx+1}. {com['nome']}*\n"
                f"   ID: `{com['id']}`\n"
                f"   Descrição: {com['descricao'] or 'N/A'}\n"
                f"   Chat ID: `{com['chat_id'] or 'N/A'}`\n\n"
            )
        
        bot_instance.send_message(chat_id, response_text, parse_mode="Markdown")

    # ------------------------------------------------------------------
    # COMANDO /editar_comunidade
    # ------------------------------------------------------------------
    @bot_instance.message_handler(commands=['editar_comunidade'])
    def handle_editar_comunidade(message):
        chat_id = message.chat.id
        comunidades = comunidade_svc.listar()

        if not comunidades:
            bot_instance.send_message(chat_id, "Nenhuma comunidade para editar. Crie uma primeiro!")
            return

        markup = types.ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True, resize_keyboard=True)
        for com in comunidades:
            markup.add(types.KeyboardButton(f"{com['nome']} (ID: {com['id']})"))
        
        msg = bot_instance.send_message(
            chat_id, 
            "Qual comunidade você deseja editar? Selecione ou digite o ID/Nome:", 
            reply_markup=markup,
            parse_mode='Markdown'
        )
        user_states[chat_id] = {"step": "awaiting_community_to_edit"}

    @bot_instance.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("step") == "awaiting_community_to_edit")
    def handle_select_community_to_edit(message):
        chat_id = message.chat.id
        input_text = message.text.strip()
        
        selected_com = None
        try:
            # Tenta encontrar por ID numérico
            com_id = int(input_text)
            selected_com = comunidade_svc.obter(com_id)
        except ValueError:
            # Tenta encontrar por nome ou parte da string do teclado
            comunidades = comunidade_svc.listar()
            for com in comunidades:
                if input_text.lower() in com['nome'].lower() or f"(ID: {com['id']})" in input_text:
                    selected_com = com
                    break

        if not selected_com:
            bot_instance.send_message(chat_id, "Comunidade não encontrada. Por favor, digite o ID ou nome exato, ou tente selecionar novamente.", parse_mode='Markdown')
            if chat_id in user_states:
                del user_states[chat_id] # Limpa o estado para evitar loop
            return

        # Armazena a comunidade selecionada e pede o novo nome
        user_states[chat_id] = {
            "step": "awaiting_edited_community_name",
            "data": {"comunidade_id": selected_com['id'], "current_nome": selected_com['nome'], "current_descricao": selected_com['descricao']}
        }
        bot_instance.send_message(
            chat_id, 
            f"Você selecionou a comunidade *'{selected_com['nome']}'* (ID: `{selected_com['id']}`).\n"
            f"Digite o *novo nome* para esta comunidade (nome atual: {selected_com['nome']}):",
            parse_mode='Markdown'
        )
    
    @bot_instance.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("step") == "awaiting_edited_community_name")
    def handle_edited_community_name(message):
        chat_id = message.chat.id
        novo_nome = message.text.strip()

        if not novo_nome:
            bot_instance.send_message(chat_id, "O novo nome da comunidade não pode ser vazio. Por favor, digite o nome:", parse_mode='Markdown')
            return
        
        # Armazena o novo nome e pede a nova descrição
        user_states[chat_id]["step"] = "awaiting_edited_community_description"
        user_states[chat_id]["data"]["novo_nome"] = novo_nome

        bot_instance.send_message(
            chat_id, 
            f"Nome atualizado para: *{novo_nome}*\n"
            f"Agora, digite a *nova descrição* (opcional, descrição atual: {user_states[chat_id]['data']['current_descricao'] or 'N/A'}, ou 'pular' para deixar igual):",
            parse_mode='Markdown'
        )

    @bot_instance.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("step") == "awaiting_edited_community_description")
    def handle_edited_community_description(message):
        chat_id = message.chat.id
        nova_descricao = message.text.strip()
        
        # Recupera os dados armazenados
        data = user_states[chat_id]["data"]
        comunidade_id = data["comunidade_id"]
        novo_nome = data["novo_nome"]
        current_descricao = data["current_descricao"]

        # Se o usuário digitou "pular", mantém a descrição atual
        if nova_descricao.lower() == 'pular':
            nova_descricao = current_descricao

        try:
            sucesso = comunidade_svc.editar(comunidade_id, novo_nome, nova_descricao)

            if sucesso:
                bot_instance.send_message(
                    chat_id, 
                    f"Comunidade com ID `{comunidade_id}` editada com sucesso!\n"
                    f"Novo Nome: *{novo_nome}*\n"
                    f"Nova Descrição: {nova_descricao or 'N/A'}",
                    parse_mode='Markdown'
                )
            else:
                bot_instance.send_message(chat_id, "Ocorreu um erro ao editar a comunidade. Certifique-se de que o ID está correto e tente novamente.", parse_mode='Markdown')
        except Exception as e:
            print(f"Erro ao finalizar edição de comunidade: {e}")
            bot_instance.send_message(chat_id, "Houve um erro inesperado. Por favor, tente novamente.", parse_mode='Markdown')
        finally:
            # Limpa o estado do usuário
            if chat_id in user_states:
                del user_states[chat_id]