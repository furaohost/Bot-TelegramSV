from flask import Blueprint, render_template, request, redirect, url_for
from app import get_db_connection

bp = Blueprint("comunidades", __name__, url_prefix="/comunidades")

@bp.route("/")
def lista():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, nome, descricao FROM comunidades ORDER BY id")
        comunidades = cur.fetchall()
    return render_template("comunidades/lista.html", comunidades=comunidades)

@bp.route("/nova", methods=["POST"])
def nova():
    nome = request.form["nome"]
    desc = request.form.get("descricao", "")
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO comunidades (nome, descricao) VALUES (%s,%s) ON CONFLICT DO NOTHING",
            (nome, desc)
        )
        conn.commit()
    return redirect(url_for("comunidades.lista"))
