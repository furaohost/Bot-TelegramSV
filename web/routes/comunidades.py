# web/routes/comunidades.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from database import get_db_connection
from bot.services.comunidades import ComunidadeService
import logging

# Configuração de logging para este módulo
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Cria o Blueprint com o nome 'comunidades'
comunidades_bp = Blueprint('comunidades', __name__, template_folder='../templates')

# Instância do serviço de comunidades (passando a função de conexão com o DB)
# É importante que esta instância seja criada no nível do módulo ou passada via app context,
# mas para simplicidade em exemplos, pode ser criada dentro das rotas se a conexão for leve.
# No entanto, o ideal é que seja injetada ou criada uma vez por requisição.
# Para este exemplo, vamos criar dentro das funções para garantir uma nova conexão por requisição.

@comunidades_bp.route('/comunidades')
def comunidades(): # Endpoint: 'comunidades.comunidades' (para listar)
    logger.debug("Requisição para /comunidades. Método: GET")
    conn = None
    comunidades_list = []
    try:
        # A instância do serviço deve ser criada dentro do contexto da requisição
        comunidade_service = ComunidadeService(get_db_connection)
        comunidades_list = comunidade_service.listar() # Lista todas as comunidades (ativas e inativas)

        if comunidades_list is None: # Se houver um erro no serviço, listar retorna None
            flash('Erro ao carregar comunidades do banco de dados.', 'danger')
            comunidades_list = [] # Garante que a lista não é None para o template

    except Exception as e:
        logger.error(f"ERRO ao carregar comunidades: {e}", exc_info=True)
        flash('Erro inesperado ao carregar comunidades.', 'danger')
        comunidades_list = []
    finally:
        # A conexão é fechada pelo ComunidadeService._execute_query, mas manter aqui para segurança
        if conn:
            conn.close()
    
    # Renderiza o template lista.html, que exibe a tabela de comunidades
    return render_template('lista.html', comunidades=comunidades_list)

@comunidades_bp.route('/comunidades/nova', methods=['GET', 'POST'])
def nova(): # Endpoint: 'comunidades.nova' (para exibir formulário e adicionar)
    logger.debug(f"Requisição para /comunidades/nova. Método: {request.method}")
    comunidade_service = ComunidadeService(get_db_connection)

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        descricao = request.form.get('descricao', '').strip()
        chat_id_str = request.form.get('chat_id', '').strip()

        # Validação básica
        if not nome:
            flash('O nome da comunidade é obrigatório.', 'danger')
            # Retorna para o formulário com os dados preenchidos e a mensagem de erro
            return render_template('nova.html', nome_val=nome, descricao_val=descricao, chat_id_val=chat_id_str)

        chat_id = None
        if chat_id_str:
            try:
                chat_id = int(chat_id_str)
            except ValueError:
                flash('ID do Chat/Grupo inválido. Deve ser um número inteiro.', 'danger')
                return render_template('nova.html', nome_val=nome, descricao_val=descricao, chat_id_val=chat_id_str)

        try:
            nova_comunidade_obj = comunidade_service.criar(nome=nome, descricao=descricao, chat_id=chat_id)
            if nova_comunidade_obj:
                flash(f"Comunidade '{nova_comunidade_obj['nome']}' adicionada com sucesso!", 'success')
                return redirect(url_for('comunidades.comunidades')) # Redireciona para a lista
            else:
                flash('Falha ao adicionar comunidade. Tente novamente.', 'danger')
        except Exception as e:
            logger.error(f"ERRO ao adicionar comunidade: {e}", exc_info=True)
            flash('Erro inesperado ao adicionar comunidade.', 'danger')
        
        # Se houve erro no try/except, re-renderiza o formulário com os dados
        return render_template('nova.html', nome_val=nome, descricao_val=descricao, chat_id_val=chat_id_str)
    
    # Para requisições GET, apenas renderiza o formulário vazio
    return render_template('nova.html')

@comunidades_bp.route('/comunidades/editar/<int:id>', methods=['GET', 'POST'])
def editar(id): # Endpoint: 'comunidades.editar' (para exibir formulário e editar)
    logger.debug(f"Requisição para /comunidades/editar/{id}. Método: {request.method}")
    comunidade_service = ComunidadeService(get_db_connection)
    comunidade = comunidade_service.obter(id)

    if not comunidade:
        flash('Comunidade não encontrada.', 'danger')
        return redirect(url_for('comunidades.comunidades'))

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        descricao = request.form.get('descricao', '').strip()
        chat_id_str = request.form.get('chat_id', '').strip()

        # Validação básica
        if not nome:
            flash('O nome da comunidade é obrigatório.', 'danger')
            return render_template('editar_comunidade.html', comunidade=comunidade, nome_val=nome, descricao_val=descricao, chat_id_val=chat_id_str)

        chat_id = None
        if chat_id_str:
            try:
                chat_id = int(chat_id_str)
            except ValueError:
                flash('ID do Chat/Grupo inválido. Deve ser um número inteiro.', 'danger')
                return render_template('editar_comunidade.html', comunidade=comunidade, nome_val=nome, descricao_val=descricao, chat_id_val=chat_id_str)
        
        try:
            sucesso = comunidade_service.editar(comunidade_id=id, nome=nome, descricao=descricao, chat_id=chat_id)
            if sucesso:
                flash('Comunidade atualizada com sucesso!', 'success')
                return redirect(url_for('comunidades.comunidades')) # Redireciona para a lista
            else:
                flash('Falha ao atualizar comunidade.', 'danger')
        except Exception as e:
            logger.error(f"ERRO ao editar comunidade: {e}", exc_info=True)
            flash('Erro inesperado ao editar comunidade.', 'danger')
        
        # Se houve erro no try/except, re-renderiza o formulário com os dados
        return render_template('editar_comunidade.html', comunidade=comunidade, nome_val=nome, descricao_val=descricao, chat_id_val=chat_id_str)
    
    # Para requisições GET, renderiza o formulário com os dados atuais da comunidade
    return render_template('editar_comunidade.html', comunidade=comunidade, 
                           nome_val=comunidade['nome'], 
                           descricao_val=comunidade['descricao'], 
                           chat_id_val=comunidade['chat_id'])

@comunidades_bp.route('/comunidades/deletar/<int:id>', methods=['POST'])
def deletar(id): # Endpoint: 'comunidades.deletar' (para desativar/excluir)
    logger.debug(f"Requisição para /comunidades/deletar/{id}. Método: POST")
    comunidade_service = ComunidadeService(get_db_connection)
    
    try:
        # Chamamos a função 'desativar' do serviço, que muda o status para 'inativa'
        sucesso = comunidade_service.desativar(id) 
        if sucesso:
            flash('Comunidade desativada com sucesso!', 'success')
        else:
            flash('Falha ao desativar comunidade. Comunidade não encontrada ou já inativa.', 'danger')
    except Exception as e:
        logger.error(f"ERRO ao desativar comunidade: {e}", exc_info=True)
        flash('Erro inesperado ao desativar comunidade.', 'danger')
    
    return redirect(url_for('comunidades.comunidades'))

