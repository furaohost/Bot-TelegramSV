import telebot
from telebot import types
import sqlite3 
import traceback 
import logging
from bot.services.comunidades import ComunidadeService 

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

user_states = {} 

# AQUI ESTÃO OS HANDLERS DE COMANDO, eles são definidos dentro de register_comunidades_handlers
# e não serão movidos para fora porque dependem de 'bot_instance' e 'comunidade_svc' serem passados.

# No entanto, o handler de new_chat_members pode ter um tratamento ligeiramente diferente
# para garantir que ele seja sempre registrado.

# A função handle_new_chat_members será definida *fora* do register_comunidades_handlers
# para que possa ser registrada diretamente no bot_instance.
# Para isso, ela precisará de acesso a 'comunidade_svc' e 'get_db_connection_func'
# que são criados *dentro* de 'register_comunidades_handlers'.

# A MELHOR FORMA (e mais limpa) é fazer com que `register_comunidades_handlers`
# receba apenas o `bot_instance` e o `get_db_connection_func`,
# e use o `comunidade_svc` E DEPOIS DEFINA OS HANDLERS.
# Parece que você já tem isso.

# O problema é a visibilidade do `sqlite3` dentro do handler aninhado, e a forma como o `telebot` registra.
# A solução mais robusta é usar o `telebot.TeleBot` para registrar os handlers.

# Vamos garantir que os módulos necessários (como `sqlite3`) estejam importados onde são usados.
# O `sqlite3` já está importado no topo deste arquivo, então o `NameError` anterior era estranho.
# Isso sugere um problema de deploy/cache ou uma versão antiga do arquivo em produção.

# Vamos forçar a definição do handler de new_chat_members para ser bem explícita.

# Funções que serão registradas como handlers. Elas recebem 'comunidade_svc' e 'get_db_connection_func'
# como argumentos para que possam ser testadas isoladamente ou usadas de forma flexível.

# Essa é a função que será decorada e atuará como o handler para new_chat_members
def _handle_new_chat_members(message: types.Message, bot_instance: telebot.TeleBot, comunidade_service: ComunidadeService, get_db_connection_func):
    chat_id = message.chat.id
    
    if message.new_chat_members and bot_instance.get_me().id in [user.id for user in message.new_chat_members]:
        logger.debug(f"Bot foi adicionado ao chat {chat_id}. Ignorando mensagem de boas-vindas para o bot.")
        return

    if message.chat.type not in ['group', 'supergroup']:
        logger.debug(f"Nova entrada de membro em chat {message.chat.type}. Ignorando pois não é grupo/supergrupo.")
        return

    logger.debug(f"Novo(s) membro(s) detectado(s) no chat ID: {chat_id}")

    welcome_message_community = "Bem-vindo(a) à nossa comunidade, {first_name}!" 

    conn = None
    try:
        conn = get_db_connection_func() 
        if conn:
            is_sqlite_conn = isinstance(conn, sqlite3.Connection) # sqlite3 já está importado no topo
            
            with conn:
                cur = conn.cursor() 

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

    comunidade = comunidade_service.obter_por_chat_id(chat_id) 
    
    if not comunidade: 
        logger.debug(f"Chat ID {chat_id} não é uma comunidade registrada. Não enviando mensagem de boas-vindas.")
        return 

    for user in message.new_chat_members:
        if user.is_bot: 
            logger.debug(f"Ignorando bot '{user.first_name}' (ID: {user.id}) adicionado ao grupo.")
            continue

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


# A função principal de registro de handlers
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
        if message.chat.type in ['group', 'supergroup', 'channel']:
            bot_instance.send_message(chat_id, "Por favor, digite o *nome* da nova comunidade (ex: 'Comunidade VIP'):", parse_mode='Markdown')
            user_states[chat_id] = {
                "step": "awaiting_new_community_name",
                "chat_type": message.chat.type,
                "target_chat_id": message.chat.id, 
                "chat_title": message.chat.title 
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

        bot_instance.send_message(chat_id, f"Nome da comunidade: *{nome_comunidade}*\nAgora, digite uma *descrição* para esta comunidade (opcional, ou 'pular' para deixar em branco):", parse_mode='Markdown')
        
        user_states[chat_id]["step"] = "awaiting_new_community_description"
        user_states[chat_id]["data"] = {"nome": nome_comunidade}


    @bot_instance.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("step") == "awaiting_new_community_description")
    def handle_new_community_description(message):
        chat_id = message.chat.id
        descricao_comunidade = message.text.strip()
        
        if descricao_comunidade.lower() == 'pular':
            descricao_comunidade = None

        state_data = user_states.get(chat_id, {})
        comunidade_data = state_data.get("data", {})
        
        nome_comunidade = comunidade_data.get("nome")
        target_chat_id = state_data.get("target_chat_id") 

        if not nome_comunidade:
            bot_instance.send_message(chat_id, "Erro interno: Nome da comunidade não encontrado no estado. Por favor, reinicie o processo com /nova_comunidade.", parse_mode='Markdown')
            if chat_id in user_states:
                del user_states[chat_id]
            return

        try:
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
            logger.error(f"Erro ao finalizar criação de comunidade: {e}", exc_info=True)
            bot_instance.send_message(chat_id, "Houve um erro inesperado. Por favor, tente novamente.", parse_mode='Markdown')
        finally:
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
        comunidades = comunidade_service.listar() 

        if not comunidades:
            bot_instance.send_message(chat_id, "Nenhuma comunidade encontrada.")
            logger.info("Nenhuma comunidade encontrada no DB.")
            return

        response_text = "*Comunidades Cadastradas:*\n\n" 
        for idx, com in enumerate(comunidades):
            response_text += (
                f"*{idx+1}. {com['nome']}*\n"
                f"   ID: `{com['id']}`\n"
                f"   Descrição: {com['descricao'] or 'N/A'}\n"
                f"   Chat ID: `{com['chat_id'] or 'N/A'}`\n\n" # Confere se com['chat_id'] tem o valor
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
            com_id = int(input_text)
            selected_com = comunidade_svc.obter(com_id)
        except ValueError:
            comunidades = comunidade_svc.listar()
            for com in comunidades:
                if input_text.lower() in com['nome'].lower() or f"(ID: {com['id']})" in input_text:
                    selected_com = com
                    break

        if not selected_com:
            bot_instance.send_message(chat_id, "Comunidade não encontrada. Por favor, digite o *ID ou nome exato*, ou *reinicie* o processo com /editar_comunidade.", parse_mode='Markdown')
            if chat_id in user_states:
                del user_states[chat_id]
            return

        user_states[chat_id] = {
            "step": "awaiting_edited_community_name",
            "data": {
                "comunidade_id": selected_com['id'],
                "current_nome": selected_com['nome'],
                "current_descricao": selected_com['descricao'],
                "current_chat_id": selected_com['chat_id'] 
            }
        }
        bot_instance.send_message(
            chat_id, 
            f"Você selecionou a comunidade *'{selected_com['nome']}'* (ID: `{selected_com['id']}`).\n"
            f"Digite o *novo nome* para esta comunidade (nome atual: {selected_com['nome']}).\n"
            f"Ou digite `pular` para manter o nome atual:", 
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
            novo_nome = current_nome 

        if not novo_nome: 
            bot_instance.send_message(chat_id, "O novo nome da comunidade não pode ser vazio. Por favor, digite o nome novamente ou `pular`.", parse_mode='Markdown')
            return
        
        user_states[chat_id]["step"] = "awaiting_edited_community_description"
        user_states[chat_id]["data"]["novo_nome"] = novo_nome

        bot_instance.send_message(
            chat_id, 
            f"Nome da comunidade será: *{novo_nome}*\n"
            f"Now, digite a *nova descrição* (descrição atual: {user_states[chat_id]['data']['current_descricao'] or 'N/A'}).\n"
            f"Ou digite `pular` para manter a descrição atual:",
            parse_mode='Markdown'
        )

    @bot_instance.message_handler(func=lambda message: user_states.get(message.chat.id, {}).get("step") == "awaiting_edited_community_description")
    def handle_edited_community_description(message):
        chat_id = message.chat.id
        nova_descricao = message.text.strip() 
        
        state_data = user_states.get(chat_id, {})
        data = state_data.get("data", {})

        comunidade_id = data.get("comunidade_id")
        novo_nome = data.get("novo_nome")
        current_descricao = data.get("current_descricao") 
        current_chat_id = data.get("current_chat_id") 

        if nova_descricao.lower() == 'pular':
            nova_descricao = current_descricao
        
        if not novo_nome: 
            bot_instance.send_message(chat_id, "Erro interno: Dados da comunidade para edição não encontrados. Por favor, reinicie o processo com /editar_comunidade.", parse_mode='Markdown')
            if chat_id in user_states:
                del user_states[chat_id]
            return

        user_states[chat_id]["step"] = "awaiting_edited_community_chat_id"
        user_states[chat_id]["data"]["nova_descricao"] = nova_descricao 
        
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

        final_chat_id = None 

        if novo_chat_id_input.lower() == 'pular':
            final_chat_id = current_chat_id 
        elif novo_chat_id_input.lower() == 'remover':
            final_chat_id = None 
        else:
            try:
                final_chat_id = int(novo_chat_id_input)
            except ValueError:
                bot_instance.send_message(chat_id, "O Chat ID deve ser um número inteiro, 'pular' ou 'remover'. Por favor, digite um valor válido.", parse_mode='Markdown')
                return 

        try:
            sucesso = comunidade_svc.editar(
                comunidade_id=comunidade_id,
                nome=novo_nome,
                descricao=nova_descricao,
                chat_id=final_chat_id 
            )

            if sucesso:
                bot_instance.send_message(
                    chat_id, 
                    f"Comunidade com ID `{comunidade_id}` editada com sucesso!\n"
                    f"Nome: *{novo_nome}*\n"
                    f"Descrição: {nova_descricao or 'N/A'}\n"
                    f"Chat ID: `{final_chat_id or 'N/A'}`", 
                    parse_mode='Markdown'
                )
            else:
                bot_instance.send_message(chat_id, "Ocorreu um erro ao editar a comunidade. Certifique-se de que o ID está correto e tente novamente.", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Erro ao finalizar edição de comunidade: {e}", exc_info=True)
            bot_instance.send_message(chat_id, "Houve um erro inesperado. Por favor, tente novamente.", parse_mode='Markdown')
        finally:
            if chat_id in user_states:
                del user_states[chat_id]

    # ------------------------------------------------------------------
    # COMANDO /deletar_comunidade (mantendo como DELETE para consistência com serviço)
    # ------------------------------------------------------------------
    @bot_instance.message_handler(commands=['deletar_comunidade']) 
    def handle_deletar_comunidade(message):
        chat_id = message.chat.id
        comunidades = comunidade_svc.listar() 

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
            sucesso = comunidade_svc.deletar(selected_com['id']) 

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
    # AQUI DEFINIMOS O HANDLER DE FATO, usando uma função anônima (lambda)
    # que chama nossa função auxiliar _handle_new_chat_members com os argumentos necessários.
    @bot_instance.message_handler(content_types=['new_chat_members'])
    def handle_new_chat_members_wrapper(message: types.Message):
        _handle_new_chat_members(message, bot_instance, comunidade_svc, get_db_connection_func)