# web/routes/access_passes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db_connection
import traceback

passes_bp = Blueprint('passes', __name__, template_folder='../templates')

@passes_bp.route('/access-passes', methods=['GET', 'POST'])
def manage_passes():
    """
    Rota para listar os passes de acesso existentes e adicionar novos.
    AGORA SEM O CAMPO DE LINK DE CONVITE.
    """
    conn = None
    try:
        conn = get_db_connection()
        
        if request.method == 'POST':
            # Pega os dados do formulário (sem o campo de link)
            name = request.form.get('name')
            description = request.form.get('description')
            price = request.form.get('price')
            duration_days = request.form.get('duration_days')
            community_id = request.form.get('community_id')

            # Validação atualizada, não verifica mais o invite_link
            if not all([name, price, duration_days, community_id]):
                flash('Todos os campos são obrigatórios.', 'danger')
                return redirect(url_for('passes.manage_passes'))

            with conn.cursor() as cur:
                # A query SQL foi atualizada para não incluir 'invite_link'
                cur.execute(
                    """
                    INSERT INTO access_passes 
                    (name, description, price, duration_days, community_id)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (name, description, float(price), int(duration_days), int(community_id))
                )
            conn.commit()
            flash('Passe de Acesso criado com sucesso!', 'success')
            return redirect(url_for('passes.manage_passes'))

        # Lógica para GET (exibir a página)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ap.*, c.nome as community_name 
                FROM access_passes ap
                LEFT JOIN comunidades c ON ap.community_id = c.id
                ORDER BY ap.created_at DESC
            """)
            passes = cur.fetchall()
            
            cur.execute("SELECT id, nome FROM comunidades ORDER BY nome ASC")
            communities = cur.fetchall()

        return render_template('access_passes.html', passes=passes, communities=communities)

    except Exception as e:
        print("ERRO EM PASSES DE ACESSO:", e)
        traceback.print_exc()
        flash('Ocorreu um erro ao gerenciar os passes de acesso.', 'danger')
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()
# web/routes/access_passes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db_connection
import traceback
import sqlite3 # Adicionado: Importar sqlite3 para verificações de tipo de conexão

passes_bp = Blueprint('passes', __name__, template_folder='../templates')

@passes_bp.route('/access-passes', methods=['GET', 'POST'])
def manage_passes():
    """
    Rota para listar os passes de acesso existentes e adicionar novos.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None: # Adicionado: Tratamento para conexão nula
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('index')) # Redireciona para o index em caso de erro crítico

        is_sqlite = isinstance(conn, sqlite3.Connection) # Verifica o tipo de conexão

        # NOTE: conn.row_factory deve ser configurado dentro de get_db_connection() para ser consistente.
        # Se get_db_connection já retorna linhas como dicionários, esta linha não é necessária aqui.
        # if is_sqlite:
        #    conn.row_factory = sqlite3.Row 
        
        if request.method == 'POST':
            name = request.form.get('name')
            description = request.form.get('description')
            price = request.form.get('price')
            duration_days = request.form.get('duration_days')
            community_id = request.form.get('community_id')

            if not all([name, price, duration_days, community_id]):
                flash('Todos os campos são obrigatórios.', 'danger')
                return redirect(url_for('passes.manage_passes'))

            with conn.cursor() as cur:
                # Modificado: Inclui is_active e ajusta a query para SQLite/PostgreSQL
                if is_sqlite:
                    cur.execute(
                        """
                        INSERT INTO access_passes 
                        (name, description, price, duration_days, community_id, is_active)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (name, description, float(price), int(duration_days), int(community_id), True) # is_active padrão como TRUE
                    )
                else: # PostgreSQL
                    cur.execute(
                        """
                        INSERT INTO access_passes 
                        (name, description, price, duration_days, community_id, is_active)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (name, description, float(price), int(duration_days), int(community_id), True) # is_active padrão como TRUE
                    )
            conn.commit()
            flash('Passe de Acesso criado com sucesso!', 'success')
            return redirect(url_for('passes.manage_passes'))

        # Lógica para GET (exibir a página)
        with conn.cursor() as cur:
            # Query para listar passes com nome da comunidade e status is_active
            cur.execute("""
                SELECT ap.*, c.nome as community_name 
                FROM access_passes ap
                LEFT JOIN comunidades c ON ap.community_id = c.id
                ORDER BY ap.created_at DESC
            """)
            passes = cur.fetchall()
            
            # Query para listar comunidades (para o dropdown no formulário)
            cur.execute("SELECT id, nome FROM comunidades ORDER BY nome ASC")
            communities = cur.fetchall()

        return render_template('access_passes.html', passes=passes, communities=communities)

    except Exception as e:
        print("ERRO EM PASSES DE ACESSO:", e)
        traceback.print_exc()
        flash('Ocorreu um erro ao gerenciar os passes de acesso.', 'danger')
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()

# Rota para alternar o status de ativação do passe (existente no seu código)
@passes_bp.route('/toggle_pass_status/<int:pass_id>', methods=['POST'])
def toggle_pass_status(pass_id):
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco de dados.', 'danger')
            return redirect(url_for('passes.manage_passes'))

        is_sqlite = isinstance(conn, sqlite3.Connection)
        
        # Garante que o cursor retorne dicionários para consistência (para sqlite)
        if isinstance(conn, sqlite3.Connection):
            conn.row_factory = sqlite3.Row
        
        with conn.cursor() as cur:
            # 1. Obter o status atual do passe
            if is_sqlite:
                cur.execute("SELECT is_active FROM access_passes WHERE id = ?", (pass_id,))
            else:
                cur.execute("SELECT is_active FROM access_passes WHERE id = %s", (pass_id,))
            
            pass_item = cur.fetchone()

            if not pass_item:
                flash('Passe de acesso não encontrado.', 'danger')
                return redirect(url_for('passes.manage_passes'))

            current_status = pass_item['is_active']
            # O psycopg2 (PostgreSQL) pode retornar True/False diretamente
            # O sqlite3 com row_factory pode retornar 1/0
            if isinstance(current_status, int): # Para SQLite, converter 1/0 para True/False
                current_status = bool(current_status)

            new_status = not current_status # Inverte o status
            
            # 2. Atualizar o status no banco de dados
            if is_sqlite:
                cur.execute("UPDATE access_passes SET is_active = ? WHERE id = ?", (new_status, pass_id))
            else:
                cur.execute("UPDATE access_passes SET is_active = %s WHERE id = %s", (new_status, pass_id))
            conn.commit()

            status_text = "ativado" if new_status else "desativado"
            flash(f'Passe de acesso {pass_id} {status_text} com sucesso!', 'success')

    except Exception as e:
        print(f"ERRO ao alternar status do passe: {e}")
        traceback.print_exc()
        flash('Ocorreu um erro ao alternar o status do passe.', 'danger')
    finally:
        if conn:
            conn.close()
            
    return redirect(url_for('passes.manage_passes'))