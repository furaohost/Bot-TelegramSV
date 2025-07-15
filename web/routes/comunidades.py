# web/routes/comunidades.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db_connection
from bot.services.comunidades import ComunidadeService 
import traceback # Importar traceback para tratamento de erros

# Linha de depuração para verificar se o módulo está sendo carregado
print("DEBUG: Módulo comunidades.py está sendo carregado!") # <--- ESTA É A NOVA LINHA DE DEBUG

# Cria o Blueprint para organizar as rotas de comunidades
comunidades_bp = Blueprint('comunidades', __name__, template_folder='../templates')

@comunidades_bp.route('/comunidades')
def manage_comunidades(): # FUNÇÃO RENOMEADA
    """ Rota para listar todas as comunidades. """
    try:
        service = ComunidadeService(get_db_connection)
        comunidades_list = service.listar()
        # Se comunidades_list for None (devido a um erro de DB), trata como lista vazia
        if comunidades_list is None:
            comunidades_list = []
            flash('Ocorreu um erro ao buscar as comunidades.', 'danger')
            
    except Exception as e:
        print(f"ERRO CRÍTICO ao carregar comunidades: {e}")
        traceback.print_exc() # Adicionado traceback para melhor depuração
        flash('Um erro inesperado ocorreu. Verifique os logs.', 'danger')
        comunidades_list = []

    return render_template('comunidades.html', comunidades=comunidades_list)

@comunidades_bp.route('/comunidades/adicionar', methods=['POST'])
def adicionar_comunidade():
    """ Rota para adicionar uma nova comunidade via formulário. """
    try:
        nome = request.form.get('nome', '').strip()
        if not nome:
            flash('O nome da comunidade é obrigatório.', 'danger')
            return redirect(url_for('comunidades.manage_comunidades'))

        descricao = request.form.get('descricao', '').strip()
        chat_id_str = request.form.get('chat_id', '').strip()
        chat_id = int(chat_id_str) if chat_id_str else None

        service = ComunidadeService(get_db_connection)
        service.criar(nome=nome, descricao=descricao, chat_id=chat_id)
        flash('Comunidade adicionada com sucesso!', 'success')

    except ValueError:
        flash('ID do Chat/Grupo inválido. Deve ser um número.', 'danger')
    except Exception as e:
        print(f"ERRO ao adicionar comunidade: {e}")
        traceback.print_exc() # Adicionado traceback
        flash('Ocorreu um erro ao adicionar a comunidade.', 'danger')
        
    return redirect(url_for('comunidades.manage_comunidades'))

@comunidades_bp.route('/comunidades/editar/<int:id>', methods=['GET', 'POST'])
def editar_comunidade(id):
    """ Rota para exibir o formulário de edição (GET) e processar a atualização (POST). """
    service = ComunidadeService(get_db_connection)
    comunidade = service.obter(id)

    if not comunidade:
        flash('Comunidade não encontrada.', 'danger')
        return redirect(url_for('comunidades.manage_comunidades'))

    if request.method == 'POST':
        try:
            nome = request.form.get('nome', '').strip()
            if not nome:
                flash('O nome da comunidade é obrigatório.', 'danger')
                return render_template('editar_comunidade.html', comunidade=comunidade)

            descricao = request.form.get('descricao', '').strip()
            chat_id_str = request.form.get('chat_id', '').strip()
            chat_id = int(chat_id_str) if chat_id_str else None
            
            service.editar(id, nome, descricao, chat_id)
            flash('Comunidade atualizada com sucesso!', 'success')
            return redirect(url_for('comunidades.manage_comunidades'))

        except ValueError:
            flash('ID do Chat/Grupo inválido. Deve ser um número.', 'danger')
        except Exception as e:
            print(f"ERRO ao editar comunidade: {e}")
            traceback.print_exc() # Adicionado traceback
            flash('Ocorreu um erro ao editar a comunidade.', 'danger')
    
    # Para a requisição GET, apenas exibe a página de edição
    return render_template('editar_comunidade.html', comunidade=comunidade)

@comunidades_bp.route('/comunidades/deletar/<int:id>', methods=['POST'])
def deletar_comunidade(id):
    """ Rota para deletar uma comunidade. """
    try:
        service = ComunidadeService(get_db_connection)
        service.deletar(id)
        flash('Comunidade deletada com sucesso!', 'success')
    except Exception as e:
        print(f"ERRO ao deletar comunidade: {e}")
        traceback.print_exc() # Adicionado traceback
        flash('Ocorreu um erro ao deletar a comunidade.', 'danger')

    return redirect(url_for('comunidades.manage_comunidades'))