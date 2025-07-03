import telebot
from telebot import types
from bot.services.comunidades import ComunidadeService # Importa o serviço de comunidades
import sqlite3 # <--- ADICIONADO: Importar sqlite3 para verificar tipo de conexão
import traceback # Adicionado para logs de erro
import logging # Para logs de depuração

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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
            traceback.print_exc()
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
        logger.debug(f"Handler de comando /listar_comunidades acionado. Mensagem: {message.text}")
        _send_comunidades_list(bot_instance, comunidade_svc, chat_id)

    # ------------------------------------------------------------------
    # HANDLER PARA O TEXTO "Comunidades" (captura o clique do botão)
    # ------------------------------------------------------------------
    @bot_instance.message_handler(func=lambda message: message.text and message.text.lower() == "comunidades")
    def handle_button_comunidades(message):
        chat_id = message.chat.id
        logger.debug(f"Handler do botão 'Comunidades' acionado. Mensagem: {message.text}")
        _send_comunidades_list(bot_instance, comunidade_svc, chat_id)

    # ------------------------------------------------------------------
    # FUNÇÃO AUXILIAR PARA ENVIAR A LISTA DE COMUNIDADES (REUTILIZÁVEL)
    # ------------------------------------------------------------------
    def _send_comunidades_list(bot_instance, comunidade_service, chat_id):
        comunidades = comunidade_service.listar() # Não precisa de ativos_apenas se não houver is_active

        if not comunidades:
            bot_instance.send_message(chat_id, "Nenhuma comunidade encontrada.")
            logger.info("Nenhuma comunidade encontrada no DB.")
            return

        response_text = "*Comunidades Cadastradas:*\n\n" # Ajustado para refletir que não há 'ativa'
        for idx, com in enumerate(comunidades):
            response_text += (
                f"*{idx+1}. {com['nome']}*\n"
                f"   ID: `{com['id']}`\n"
                f"   Descrição: {com['descricao'] or 'N/A'}\n"
                f"   Chat ID: `{com['chat_id'] or 'N/A'}`\n\n"
            )
        
        bot_instance.send_message(chat_id, response_text, parse_mode="Markdown")
        logger.debug(f"Comunidades enviadas para {chat_id}.")

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
        # Correção aqui: a nova_descricao deve vir do message.text, não do data
        nova_descricao = message.text.strip() 
        
        # Recupera os dados armazenados
        state_data = user_states.get(chat_id, {})
        data = state_data.get("data", {})

        comunidade_id = data.get("comunidade_id")
        novo_nome = data.get("novo_nome")
        current_descricao = data.get("current_descricao") # Pegar a descrição atual para o "pular"
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
            traceback.print_exc()
            bot_instance.send_message(chat_id, "Houve um erro inesperado. Por favor, tente novamente.", parse_mode='Markdown')
        finally:
            # Limpa o estado do usuário
            if chat_id in user_states:
                del user_states[chat_id]

    # ------------------------------------------------------------------
    # COMANDO /deletar_comunidade (mantendo como DELETE para consistência com serviço)
    # ------------------------------------------------------------------
    @bot_instance.message_handler(commands=['deletar_comunidade']) 
    def handle_deletar_comunidade(message):
        chat_id = message.chat.id
        comunidades = comunidade_svc.listar() # Listar todas para deletar

        if not comunidades:
            bot_instance.send_message(chat_id, "Nenhuma comunidade para deletar.")
            return

        markup = types.ReplyKeyboardMarkup(row_width=1, one_time_keyboard=True, resize_keyboard=True)
        for com in comunidades:
            markup.add(types.KeyboardButton(f"{com['nome']} (ID: {com['id']})"))
        
        bot_instance.send_message(
            chat_id, 
            "Qual comunidade você deseja *deletar*? Selecione ou digite o ID/Nome:", 
            reply_markup=markup,
            parse_mode='Markdown'
        )
        user_states[chat_id] = {"step": "awaiting_community_to_delete"}

    @bot_instance.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("step") == "awaiting_community_to_delete")
    def handle_select_community_to_delete(message):
        chat_id = message.chat.id
        input_text = message.text.strip()
        
        selected_com = None
        try:
            com_id = int(input_text)
            selected_com = comunidade_svc.obter(com_id)
        except ValueError:
            comunidades = comunidade_svc.listar()
            for com in comunidades:
                if input_text.lower() in com['nome'].lower() or f"(ID: {com['id']})" in input_text:
                    selected_com = com
                    break

        if not selected_com:
            bot_instance.send_message(chat_id, "Comunidade não encontrada. Por favor, digite o *ID ou nome exato*, ou *reinicie* o processo com /deletar_comunidade.", parse_mode='Markdown')
            if chat_id in user_states:
                del user_states[chat_id]
            return

        try:
            sucesso = comunidade_svc.deletar(selected_com['id']) # Chama o método deletar

            if sucesso:
                bot_instance.send_message(
                    chat_id, 
                    f"Comunidade *'{selected_com['nome']}'* (ID: `{selected_com['id']}`) *deletada* com sucesso.",
                    parse_mode='Markdown'
                )
            else:
                bot_instance.send_message(chat_id, "Ocorreu um erro ao *deletar* a comunidade. Tente novamente.", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Erro ao deletar comunidade: {e}", exc_info=True)
            bot_instance.send_message(chat_id, "Houve um erro inesperado. Por favor, tente novamente.", parse_mode='Markdown')
        finally:
            if chat_id in user_states:
                del user_states[chat_id]

    # ------------------------------------------------------------------
    # NOVO HANDLER: Entrada de novos membros em grupos
    # ------------------------------------------------------------------
    @bot_instance.message_handler(content_types=['new_chat_members'])
    def handle_new_chat_members(message):
        chat_id = message.chat.id
        
        # Ignora mensagens de entrada do próprio bot se ele for adicionado
        if message.new_chat_members and bot_instance.get_me().id in [user.id for user in message.new_chat_members]:
            logger.debug(f"Bot foi adicionado ao chat {chat_id}. Ignorando mensagem de boas-vindas para o bot.")
            return

        # Ignora se não for um grupo ou supergrupo
        if message.chat.type not in ['group', 'supergroup']:
            logger.debug(f"Nova entrada de membro em chat {message.chat.type}. Ignorando pois não é grupo/supergrupo.")
            return

        logger.debug(f"Novo(s) membro(s) detectado(s) no chat ID: {chat_id}")

        # 1. Obter a mensagem de boas-vindas da comunidade do banco de dados
        welcome_message_community = "Bem-vindo(a) à nossa comunidade, {first_name}!" # Valor padrão

        conn = None
        try:
            conn = get_db_connection_func() # Usar a função passada como argumento
            if conn:
                # É crucial verificar se a conexão é PostgreSQL ou SQLite aqui
                # para usar os placeholders corretos.
                # No `app.py`, `get_db_connection` já retorna um cursor que lida com isso,
                # mas `isinstance(conn, sqlite3.Connection)` ainda precisa do import.
                is_sqlite_conn = isinstance(conn, sqlite3.Connection)
                
                with conn:
                    cur = conn.cursor() # Assumindo que o cursor já está configurado para DictCursor no get_db_connection

                    if is_sqlite_conn:
                        cur.execute("SELECT value FROM config WHERE key = ?", ('welcome_message_community',))
                    else:
                        cur.execute("SELECT value FROM config WHERE key = %s", ('welcome_message_community',))
                    row = cur.fetchone()
                    if row and row['value']:
                        welcome_message_community = row['value']
                        logger.debug(f"Mensagem de boas-vindas do DB carregada: '{welcome_message_community}'")
                    else:
                        logger.info(f"'welcome_message_community' não encontrada ou vazia no DB. Usando padrão.")
            else:
                logger.error(f"Não foi possível obter conexão com o DB para carregar welcome_message_community.")
        except Exception as e:
            logger.error(f"Falha ao carregar welcome_message_community do DB: {e}", exc_info=True)
        finally:
            if conn:
                conn.close()

        # 2. Verificar se o grupo está registrado como uma comunidade
        comunidade = comunidade_svc.obter_por_chat_id(chat_id) 
        
        if not comunidade: 
            logger.debug(f"Chat ID {chat_id} não é uma comunidade registrada. Não enviando mensagem de boas-vindas.")
            return # Não envia mensagem se o grupo não for uma comunidade registrada

        # 3. Enviar a mensagem para cada novo membro
        for user in message.new_chat_members:
            # O bot não deve saudar outros bots (a menos que explicitamente desejado)
            if user.is_bot: 
                logger.debug(f"Ignorando bot '{user.first_name}' (ID: {user.id}) adicionado ao grupo.")
                continue

            # A função get_or_register_user para registrar usuários que entram no grupo
            # Se você a tem em app.py e quer que usuários adicionados a grupos sejam registrados/ativados:
            # from app import get_or_register_user # Você precisaria importar isso de app.py
            # get_or_register_user(user) # Chame esta função para registrar/atualizar o usuário

            # Formata a mensagem com o nome do novo membro
            formatted_message = welcome_message_community.format(
                first_name=user.first_name,
                last_name=user.last_name or '',
                username=user.username or 'usuário'
            )
            
            try:
                bot_instance.send_message(chat_id, formatted_message, parse_mode='Markdown')
                logger.debug(f"Mensagem de boas-vindas enviada para {user.first_name} (ID: {user.id}) no chat {chat_id}.")
            except Exception as e:
                logger.error(f"Falha ao enviar mensagem de boas-vindas para {user.first_name} (ID: {user.id}) no chat {chat_id}: {e}", exc_info=True)