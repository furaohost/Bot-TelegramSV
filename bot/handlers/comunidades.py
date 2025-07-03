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
            bot_instance.send_message(chat_id, "Por favor, digite o *nome* da nova comunidade (ex: 'Comunidade VIP'):", parse_mode='Markdown')
            # Armazena o estado do usuário para o próximo passo, incluindo o chat_id do grupo/canal
            user_states[chat_id] = {
                "step": "awaiting_new_community_name",
                "chat_type": message.chat.type,
                "target_chat_id": message.chat.id, # O ID do grupo/canal
                "chat_title": message.chat.title # Título do grupo/canal
            }
        else:
            bot_instance.send_message(chat_id, "Este comando `/nova_comunidade` deve ser usado dentro de um grupo ou canal que você deseja gerenciar. Por favor, adicione-me a um grupo e use o comando lá.", parse_mode='Markdown')


    @bot_instance.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("step") == "awaiting_new_community_name")
    def handle_new_community_name(message):
        chat_id = message.chat.id
        nome_comunidade = message.text.strip()

        if not nome_comunidade:
            bot_instance.send_message(chat_id, "O nome da comunidade não pode ser vazio. Por favor, digite o nome:", parse_mode='Markdown')
            return

        # Pede a descrição da comunidade
        bot_instance.send_message(chat_id, f"Nome da comunidade: *{nome_comunidade}*\nAgora, digite uma *descrição* para esta comunidade (opcional, ou 'pular' para deixar em branco):", parse_mode='Markdown')
        
        # Armazena o nome e avança para o próximo passo, mantendo os dados anteriores
        user_states[chat_id]["step"] = "awaiting_new_community_description"
        user_states[chat_id]["data"] = {"nome": nome_comunidade}


    @bot_instance.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("step") == "awaiting_new_community_description")
    def handle_new_community_description(message):
        chat_id = message.chat.id
        descricao_comunidade = message.text.strip()
        
        # Se o usuário digitou "pular", a descrição fica vazia
        if descricao_comunidade.lower() == 'pular':
            descricao_comunidade = None

        # Recupera os dados armazenados, incluindo o target_chat_id
        state_data = user_states.get(chat_id, {})
        comunidade_data = state_data.get("data", {})
        
        nome_comunidade = comunidade_data.get("nome")
        target_chat_id = state_data.get("target_chat_id") # O ID do chat/grupo

        if not nome_comunidade:
            bot_instance.send_message(chat_id, "Erro interno: Nome da comunidade não encontrado no estado. Por favor, reinicie o processo com /nova_comunidade.", parse_mode='Markdown')
            if chat_id in user_states:
                del user_states[chat_id]
            return

        try:
            nova_comunidade = comunidade_svc.criar(
                nome=nome_comunidade, 
                descricao=descricao_comunidade, 
                chat_id=target_chat_id # Passa o chat_id do grupo/canal
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
    # HANDLER PARA O COMANDO /listar_comunidades (captura @nomedobot)
    # ------------------------------------------------------------------
    @bot_instance.message_handler(commands=['listar_comunidades'])
    def handle_command_listar_comunidades(message):
        chat_id = message.chat.id
        print(f"DEBUG: Handler de comando /listar_comunidades acionado. Mensagem: {message.text}") # Log de depuração
        _send_comunidades_list(bot_instance, comunidade_svc, chat_id)

    # ------------------------------------------------------------------
    # HANDLER PARA O TEXTO "Comunidades" (captura o clique do botão)
    # ------------------------------------------------------------------
    @bot_instance.message_handler(func=lambda message: message.text == "Comunidades")
    def handle_button_comunidades(message):
        chat_id = message.chat.id
        print(f"DEBUG: Handler do botão 'Comunidades' acionado. Mensagem: {message.text}") # Log de depuração
        _send_comunidades_list(bot_instance, comunidade_svc, chat_id)

    # ------------------------------------------------------------------
    # FUNÇÃO AUXILIAR PARA ENVIAR A LISTA DE COMUNIDADES (REUTILIZÁVEL)
    # ------------------------------------------------------------------
    def _send_comunidades_list(bot_instance, comunidade_service, chat_id):
        comunidades = comunidade_service.listar()

        if not comunidades:
            bot_instance.send_message(chat_id, "Nenhuma comunidade encontrada.")
            print("DEBUG: Nenhuma comunidade encontrada no DB.") # Log de depuração
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
        print(f"DEBUG: Comunidades enviadas para {chat_id}.") # Log de depuração

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
        
        bot_instance.send_message(
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
            bot_instance.send_message(chat_id, "Comunidade não encontrada. Por favor, digite o *ID ou nome exato*, ou *reinicie* o processo de edição com /editar_comunidade.", parse_mode='Markdown')
            # Limpa o estado se não encontrar para evitar que o usuário fique preso
            if chat_id in user_states:
                del user_states[chat_id]
            return

        # Armazena a comunidade selecionada e pede o novo nome
        user_states[chat_id] = {
            "step": "awaiting_edited_community_name",
            "data": {
                "comunidade_id": selected_com['id'],
                "current_nome": selected_com['nome'],
                "current_descricao": selected_com['descricao'],
                "current_chat_id": selected_com['chat_id'] # Armazena também o chat_id atual do grupo
            }
        }
        bot_instance.send_message(
            chat_id, 
            f"Você selecionou a comunidade *'{selected_com['nome']}'* (ID: `{selected_com['id']}`).\n"
            f"Digite o *novo nome* para esta comunidade (nome atual: {selected_com['nome']}).\n"
            f"Ou digite `pular` para manter o nome atual:", # Adicionado opção de pular
            parse_mode='Markdown'
        )
    
    @bot_instance.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("step") == "awaiting_edited_community_name")
    def handle_edited_community_name(message):
        chat_id = message.chat.id
        novo_nome = message.text.strip()
        
        state_data = user_states.get(chat_id, {})
        data = state_data.get("data", {})
        current_nome = data.get("current_nome")

        if novo_nome.lower() == 'pular':
            novo_nome = current_nome # Mantém o nome atual

        if not novo_nome: # Se o usuário digitou pular e o nome atual é vazio, ou digitou algo inválido
            bot_instance.send_message(chat_id, "O novo nome da comunidade não pode ser vazio. Por favor, digite o nome novamente ou `pular`.", parse_mode='Markdown')
            return
        
        # Armazena o novo nome e pede a nova descrição
        user_states[chat_id]["step"] = "awaiting_edited_community_description"
        user_states[chat_id]["data"]["novo_nome"] = novo_nome

        bot_instance.send_message(
            chat_id, 
            f"Nome da comunidade será: *{novo_nome}*\n"
            f"Agora, digite a *nova descrição* (descrição atual: {user_states[chat_id]['data']['current_descricao'] or 'N/A'}).\n"
            f"Ou digite `pular` para manter a descrição atual:",
            parse_mode='Markdown'
        )

    @bot_instance.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("step") == "awaiting_edited_community_description")
    def handle_edited_community_description(message):
        chat_id = message.chat.id
        nova_descricao = message.text.strip()
        
        # Recupera os dados armazenados
        state_data = user_states.get(chat_id, {})
        data = state_data.get("data", {})

        comunidade_id = data.get("comunidade_id")
        novo_nome = data.get("novo_nome")
        current_descricao = data.get("current_descricao")
        current_chat_id = data.get("current_chat_id") # O chat_id atual do grupo/canal

        # Se o usuário digitou "pular", mantém a descrição atual
        if nova_descricao.lower() == 'pular':
            nova_descricao = current_descricao
        
        if not novo_nome: # Sanidade caso algum estado anterior tenha sido perdido
            bot_instance.send_message(chat_id, "Erro interno: Dados da comunidade para edição não encontrados. Por favor, reinicie o processo com /editar_comunidade.", parse_mode='Markdown')
            if chat_id in user_states:
                del user_states[chat_id]
            return

        # Agora, o bot pergunta se deseja atualizar o Chat ID (opcional)
        user_states[chat_id]["step"] = "awaiting_edited_community_chat_id"
        user_states[chat_id]["data"]["nova_descricao"] = nova_descricao # Armazena a nova descrição
        
        bot_instance.send_message(
            chat_id,
            f"Nome: *{novo_nome}*\nDescrição: *{nova_descricao or 'N/A'}*\n\n"
            f"Agora, digite o *novo Chat ID* para esta comunidade (ID atual: `{current_chat_id or 'N/A'}`).\n"
            f"Ou digite `pular` para manter o ID atual.\n"
            f"Se você quiser remover o Chat ID, digite `remover`.",
            parse_mode='Markdown'
        )


    @bot_instance.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("step") == "awaiting_edited_community_chat_id")
    def handle_edited_community_chat_id(message):
        chat_id = message.chat.id
        novo_chat_id_input = message.text.strip()

        state_data = user_states.get(chat_id, {})
        data = state_data.get("data", {})

        comunidade_id = data.get("comunidade_id")
        novo_nome = data.get("novo_nome")
        nova_descricao = data.get("nova_descricao")
        current_chat_id = data.get("current_chat_id")

        final_chat_id = None # Padrão para None, para permitir remover ou manter N/A

        if novo_chat_id_input.lower() == 'pular':
            final_chat_id = current_chat_id # Mantém o chat ID atual
        elif novo_chat_id_input.lower() == 'remover':
            final_chat_id = None # Define como None para remover
        else:
            try:
                # Tenta converter para int, pois Chat IDs são numéricos
                final_chat_id = int(novo_chat_id_input)
            except ValueError:
                bot_instance.send_message(chat_id, "O Chat ID deve ser um número inteiro, 'pular' ou 'remover'. Por favor, digite um valor válido.", parse_mode='Markdown')
                return # Permanece no mesmo passo para tentar novamente

        try:
            sucesso = comunidade_svc.editar(
                comunidade_id=comunidade_id,
                nome=novo_nome,
                descricao=nova_descricao,
                chat_id=final_chat_id # Passa o chat_id final
            )

            if sucesso:
                bot_instance.send_message(
                    chat_id, 
                    f"Comunidade com ID `{comunidade_id}` editada com sucesso!\n"
                    f"Nome: *{novo_nome}*\n"
                    f"Descrição: {nova_descricao or 'N/A'}\n"
                    f"Chat ID: `{final_chat_id or 'N/A'}`", # Exibe o chat ID final
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

    # ------------------------------------------------------------------
    # COMANDO /desativar_comunidade (ou deletar)
    # ------------------------------------------------------------------
    @bot_instance.message_handler(commands=['desativar_comunidade', 'deletar_comunidade'])
    def handle_desativar_comunidade(message):
        chat_id = message.chat.id
        comunidades = comunidade_svc.listar(ativos_apenas=True) # Lista apenas comunidades ativas para desativar

        if not comunidades:
            bot_instance.send_message(chat_id, "Nenhuma comunidade ativa para desativar.")
            return

        markup = types.ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True, resize_keyboard=True)
        for com in comunidades:
            markup.add(types.KeyboardButton(f"{com['nome']} (ID: {com['id']})"))
        
        bot_instance.send_message(
            chat_id, 
            "Qual comunidade você deseja desativar? Selecione ou digite o ID/Nome:", 
            reply_markup=markup,
            parse_mode='Markdown'
        )
        user_states[chat_id] = {"step": "awaiting_community_to_deactivate"}

    @bot_instance.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("step") == "awaiting_community_to_deactivate")
    def handle_select_community_to_deactivate(message):
        chat_id = message.chat.id
        input_text = message.text.strip()
        
        selected_com = None
        try:
            com_id = int(input_text)
            selected_com = comunidade_svc.obter(com_id)
        except ValueError:
            comunidades = comunidade_svc.listar(ativos_apenas=True)
            for com in comunidades:
                if input_text.lower() in com['nome'].lower() or f"(ID: {com['id']})" in input_text:
                    selected_com = com
                    break

        if not selected_com:
            bot_instance.send_message(chat_id, "Comunidade não encontrada. Por favor, digite o *ID ou nome exato*, ou *reinicie* o processo com /desativar_comunidade.", parse_mode='Markdown')
            if chat_id in user_states:
                del user_states[chat_id]
            return

        try:
            # A função de "deletar" no serviço deve na verdade "desativar" (mudar o status, não remover do DB)
            sucesso = comunidade_svc.desativar(selected_com['id'])

            if sucesso:
                bot_instance.send_message(
                    chat_id, 
                    f"Comunidade *'{selected_com['nome']}'* (ID: `{selected_com['id']}`) desativada com sucesso.",
                    parse_mode='Markdown'
                )
            else:
                bot_instance.send_message(chat_id, "Ocorreu um erro ao desativar a comunidade. Tente novamente.", parse_mode='Markdown')
        except Exception as e:
            print(f"Erro ao desativar comunidade: {e}")
            bot_instance.send_message(chat_id, "Houve um erro inesperado. Por favor, tente novamente.", parse_mode='Markdown')
        finally:
            if chat_id in user_states:
                del user_states[chat_id]