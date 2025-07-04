# web/routes/subscription_plans.py

from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import get_db_connection
import pagamentos  # Importa o nosso módulo de pagamentos
import traceback

plans_bp = Blueprint('plans', __name__, template_folder='../templates')

@plans_bp.route('/subscription-plans', methods=['GET', 'POST'])
def list_plans():
    """
    Rota para listar os planos de assinatura e criar novos,
    agora integrada com o Mercado Pago.
    """
    conn = None
    try:
        conn = get_db_connection()
        
        if request.method == 'POST':
            name = request.form.get('name')
            description = request.form.get('description')
            price = float(request.form.get('price'))
            frequency = int(request.form.get('frequency'))
            frequency_type = request.form.get('frequency_type')
            community_id = int(request.form.get('community_id'))

            if not all([name, price, frequency, frequency_type, community_id]):
                flash('Todos os campos são obrigatórios.', 'danger')
                return redirect(url_for('plans.list_plans'))

            # ETAPA 1: Criar o plano no Mercado Pago
            plan_data_for_mp = {
                "name": name,
                "price": price,
                "frequency": frequency,
                "frequency_type": frequency_type
            }
            mp_plan_response = pagamentos.criar_plano_de_assinatura_mp(plan_data_for_mp)

            # Verifica se a criação no MP falhou e mostra uma mensagem de erro específica
            if not mp_plan_response or 'id' not in mp_plan_response:
                error_details = mp_plan_response.get('error', 'Erro desconhecido.') if mp_plan_response else 'Nenhuma resposta da API.'
                flash(f'Falha ao criar o plano no Mercado Pago: {error_details}', 'danger')
                return redirect(url_for('plans.list_plans'))
            
            mercadopago_plan_id = mp_plan_response['id']

            # ETAPA 2: Salvar o plano no nosso banco de dados com o ID do MP
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO subscription_plans 
                    (name, description, price, frequency, frequency_type, community_id, mercadopago_plan_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (name, description, price, frequency, frequency_type, community_id, mercadopago_plan_id)
                )
            conn.commit()
            flash(f'Plano de assinatura "{name}" criado com sucesso!', 'success')
            return redirect(url_for('plans.list_plans'))

        # Se a requisição for GET, busca os dados para exibir na página
        with conn.cursor() as cur:
            # Busca os planos já existentes, juntando com o nome da comunidade
            cur.execute("""
                SELECT p.*, c.nome as community_name 
                FROM subscription_plans p 
                LEFT JOIN comunidades c ON p.community_id = c.id 
                ORDER BY p.created_at DESC
            """)
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
