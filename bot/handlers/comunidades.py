# web/routes/comunidades.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db_connection
from bot.services.comunidades import ComunidadeService 

# Cria o Blueprint com o nome 'comunidades'
comunidades_bp = Blueprint('comunidades', __name__, template_folder='../templates')

@comunidades_bp.route('/comunidades')
def comunidades(): # <<-- ESTA É A FUNÇÃO QUE CRIA O ENDPOINT 'comunidades.comunidades'
    conn = None
    comunidades_list = []
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return render_template('comunidades.html', comunidades=[])

        comunidade_service = ComunidadeService(get_db_connection)
        comunidades_list = comunidade_service.listar()

    except Exception as e:
        print(f"ERRO ao carregar comunidades: {e}")
        flash('Erro ao carregar comunidades.', 'danger')
    finally:
        if conn:
            conn.close()
    return render_template('comunidades.html', comunidades=comunidades_list)

# A rota para adicionar que estava no exemplo anterior. O endpoint será 'comunidades.adicionar_comunidade'
@comunidades_bp.route('/comunidades/adicionar', methods=['POST'])
def adicionar_comunidade():
    if request.method == 'POST':
        nome = request.form['nome'].strip()
        descricao = request.form.get('descricao', '').strip()
        chat_id = request.form.get('chat_id', '').strip() or None 
        
        if chat_id:
            try:
                chat_id = int(chat_id)
            except ValueError:
                flash('ID do Chat/Grupo inválido. Deve ser um número.', 'danger')
                return redirect(url_for('comunidades.comunidades'))

        conn = None
        try:
            conn = get_db_connection()
            if conn is None:
                flash('Erro de conexão com o banco de dados.', 'danger')
                return redirect(url_for('comunidades.comunidades'))

            comunidade_service = ComunidadeService(get_db_connection)
            nova_comunidade = comunidade_service.criar(nome=nome, descricao=descricao, chat_id=chat_id)
            if nova_comunidade:
                flash('Comunidade adicionada com sucesso!', 'success')
            else:
                flash('Falha ao adicionar comunidade.', 'danger')
        except Exception as e:
            print(f"ERRO ao adicionar comunidade: {e}")
            flash('Erro ao adicionar comunidade.', 'danger')
        finally:
            if conn:
                conn.close()
    return redirect(url_for('comunidades.comunidades'))

# Rota para edição (GET para exibir formulário, POST para salvar)
@comunidades_bp.route('/comunidades/editar/<int:id>', methods=['GET', 'POST'])
def editar_comunidade(id):
    conn = None
    comunidade = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('comunidades.comunidades'))
        
        comunidade_service = ComunidadeService(get_db_connection)
        comunidade = comunidade_service.obter(id)

        if not comunidade:
            flash('Comunidade não encontrada.', 'danger')
            return redirect(url_for('comunidades.comunidades'))

        if request.method == 'POST':
            nome = request.form['nome'].strip()
            descricao = request.form.get('descricao', '').strip()
            chat_id = request.form.get('chat_id', '').strip() or None

            if chat_id:
                try:
                    chat_id = int(chat_id)
                except ValueError:
                    flash('ID do Chat/Grupo inválido. Deve ser um número.', 'danger')
                    # Passar os valores atuais para o template em caso de erro
                    return render_template('editar_comunidade.html', comunidade=comunidade, nome_val=nome, descricao_val=descricao, chat_id_val=chat_id)

            sucesso = comunidade_service.editar(id, nome, descricao, chat_id)
            if sucesso:
                flash('Comunidade atualizada com sucesso!', 'success')
                return redirect(url_for('comunidades.comunidades'))
            else:
                flash('Falha ao atualizar comunidade.', 'danger')

    except Exception as e:
        print(f"ERRO ao editar comunidade: {e}")
        flash('Erro ao editar comunidade.', 'danger')
    finally:
        if conn:
            conn.close()
    # Se for GET, ou POST falhar, renderiza o formulário de edição
    return render_template('editar_comunidade.html', comunidade=comunidade, 
                           nome_val=comunidade['nome'], 
                           descricao_val=comunidade['descricao'], 
                           chat_id_val=comunidade['chat_id'])


@comunidades_bp.route('/comunidades/deletar/<int:id>', methods=['POST'])
def deletar_comunidade(id):
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('comunidades.comunidades'))
        
        comunidade_service = ComunidadeService(get_db_connection)
        sucesso = comunidade_service.deletar(id)
        if sucesso:
            flash('Comunidade deletada com sucesso!', 'success')
        else:
            flash('Falha ao deletar comunidade.', 'danger')
    except Exception as e:
        print(f"ERRO ao deletar comunidade: {e}")
        flash('Erro ao deletar comunidade.', 'danger')
    finally:
        if conn:
            conn.close()
    return redirect(url_for('comunidades.comunidades'))

# Importar esta função em app.py e registrar o blueprint
def create_comunidades_blueprint(get_db_connection_func):
    # Passa a função de conexão para o serviço quando o blueprint é criado
    # Isso pode ser feito se o seu ComunidadeService aceita a função no construtor
    # Ou você pode passar get_db_connection_func para cada método do serviço, como já faz na rota
    return comunidades_bp