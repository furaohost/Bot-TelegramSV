# web/routes/access_passes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db_connection
import traceback

# Novo Blueprint para os passes de acesso
passes_bp = Blueprint('passes', __name__, template_folder='../templates')

@passes_bp.route('/access-passes', methods=['GET', 'POST'])
def manage_passes():
    """
    Rota para listar os passes de acesso existentes e adicionar novos.
    """
    conn = None
    try:
        conn = get_db_connection()
        
        # Se a requisição for POST, tenta criar um novo passe
        if request.method == 'POST':
            # Pega os dados do formulário (sem o campo de link)
            name = request.form.get('name')
            description = request.form.get('description')
            price = request.form.get('price')
            duration_days = request.form.get('duration_days')
            community_id = request.form.get('community_id')

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

        # Se a requisição for GET, busca os dados para exibir na página
        with conn.cursor() as cur:
            # Busca os passes já existentes
            cur.execute("""
                SELECT ap.*, c.nome as community_name 
                FROM access_passes ap
                LEFT JOIN comunidades c ON ap.community_id = c.id
                ORDER BY ap.created_at DESC
            """)
            passes = cur.fetchall()
            
            # Busca as comunidades para preencher o dropdown do formulário
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
