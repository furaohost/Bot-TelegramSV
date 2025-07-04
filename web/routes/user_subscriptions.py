# web/routes/user_subscriptions.py

from flask import Blueprint, render_template, redirect, url_for, flash
from database import get_db_connection
import traceback

# Cria um novo Blueprint para organizar as rotas de assinaturas
subscriptions_bp = Blueprint('subscriptions', __name__, template_folder='../templates')

@subscriptions_bp.route('/subscriptions')
def list_subscriptions():
    """
    Rota para listar todas as assinaturas de usuários.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Query que junta as 3 tabelas para obter todas as informações
            cur.execute("""
                SELECT 
                    us.id,
                    us.status,
                    us.start_date,
                    us.expiration_date,
                    us.last_payment_date,
                    u.username AS user_username,
                    u.first_name AS user_first_name,
                    sp.name AS plan_name
                FROM 
                    user_subscriptions us
                JOIN 
                    users u ON us.user_id = u.id
                JOIN 
                    subscription_plans sp ON us.plan_id = sp.id
                ORDER BY 
                    us.start_date DESC;
            """)
            subscriptions = cur.fetchall()

        return render_template('user_subscriptions.html', subscriptions=subscriptions)

    except Exception as e:
        print("ERRO AO LISTAR ASSINATURAS:", e)
        traceback.print_exc()
        flash('Ocorreu um erro ao carregar a lista de assinaturas.', 'danger')
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()
