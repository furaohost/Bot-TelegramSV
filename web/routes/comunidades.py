from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime

def create_comunidades_blueprint(get_db_connection):
    bp = Blueprint("comunidades", __name__, url_prefix="/comunidades")

    @bp.route('/')
    def comunidades():
        if not session.get('logged_in'):
            return redirect(url_for('login.login'))

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM comunidades ORDER BY id DESC")
        comunidades = cur.fetchall()
        conn.close()
        return render_template('comunidades.html', comunidades=comunidades)

    @bp.route('/nova', methods=['GET', 'POST'])
    def nova_comunidade():
        if not session.get('logged_in'):
            return redirect(url_for('login.login'))

        if request.method == 'POST':
            nome = request.form['nome']
            link = request.form['link']
            categoria = request.form['categoria']
            criada_em = datetime.now()

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO comunidades (nome, link, categoria, criada_em) VALUES (%s, %s, %s, %s)",
                        (nome, link, categoria, criada_em))
            conn.commit()
            conn.close()

            flash('Comunidade adicionada com sucesso!', 'success')
            return redirect(url_for('comunidades.comunidades'))

        return render_template('nova_comunidade.html')

    @bp.route('/excluir/<int:comunidade_id>', methods=['POST'])
    def excluir_comunidade(comunidade_id):
        if not session.get('logged_in'):
            return redirect(url_for('login.login'))

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM comunidades WHERE id = %s", (comunidade_id,))
        conn.commit()
        conn.close()

        flash('Comunidade excluída com sucesso!', 'success')
        return redirect(url_for('comunidades.comunidades'))

    return bp
