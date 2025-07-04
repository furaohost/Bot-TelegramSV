# web/routes/subscription_plans.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db_connection
import traceback

# Cria um novo Blueprint para organizar as rotas de planos
plans_bp = Blueprint('plans', __name__, template_folder='../templates')

@plans_bp.route('/subscription-plans', methods=['GET', 'POST'])
def list_plans():
    """
    Rota para listar os planos de assinatura existentes e
    adicionar novos planos.
    """
    conn = None
    try:
        conn = get_db_connection()
        
        # Se a requisição for POST, tenta criar um novo plano
        if request.method == 'POST':
            name = request.form.get('name')
            description = request.form.get('description')
            price = request.form.get('price')
            frequency = request.form.get('frequency')
            frequency_type = request.form.get('frequency_type')
            community_id = request.form.get('community_id')

            if not all([name, price, frequency, frequency_type, community_id]):
                flash('Todos os campos são obrigatórios.', 'danger')
                return redirect(url_for('plans.list_plans'))

            # TODO: Futuramente, aqui entrará a lógica para criar o plano no Mercado Pago
            # e salvar o mercadopago_plan_id. Por enquanto, salvamos como NULL.
            
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO subscription_plans 
                    (name, description, price, frequency, frequency_type, community_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (name, description, float(price), int(frequency), frequency_type, int(community_id))
                )
            conn.commit()
            flash('Plano de assinatura criado com sucesso!', 'success')
            return redirect(url_for('plans.list_plans'))

        # Se a requisição for GET, busca os dados para exibir na página
        with conn.cursor() as cur:
            # Busca os planos já existentes
            cur.execute("SELECT * FROM subscription_plans ORDER BY created_at DESC")
            plans = cur.fetchall()
            
            # Busca as comunidades para preencher o dropdown do formulário
            cur.execute("SELECT id, nome FROM comunidades ORDER BY nome ASC")
            communities = cur.fetchall()

        return render_template('subscription_plans.html', plans=plans, communities=communities)

    except Exception as e:
        print("ERRO EM PLANOS DE ASSINATURA:", e)
        traceback.print_exc()
        flash('Ocorreu um erro ao gerenciar os planos de assinatura.', 'danger')
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()
