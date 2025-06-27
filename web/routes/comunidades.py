# -*- coding: utf-8 -*-
"""
Blueprint de Comunidades para o painel Flask.
Caminho base: /comunidades
"""

from flask import Blueprint, render_template, request, redirect, url_for
from bot.services.comunidades import ComunidadeService


def create_comunidades_blueprint(get_db_connection):
    bp = Blueprint("comunidades", __name__, url_prefix="/comunidades")
    svc = ComunidadeService(get_db_connection)

    # LISTAR
    @bp.route("/")
    def lista():
        comunidades = svc.listar()
        return render_template("comunidades/lista.html", comunidades=comunidades)

    # FORM NOVE / CRIAR
    @bp.route("/nova", methods=["GET", "POST"])
    def nova():
        if request.method == "POST":
            svc.criar(request.form["nome"], request.form.get("descricao", ""))
            return redirect(url_for("comunidades.lista"))
        return render_template("comunidades/nova.html")

    # EDITAR
    @bp.route("/<int:cid>/editar", methods=["GET", "POST"])
    def editar(cid):
        if request.method == "POST":
            svc.editar(cid, request.form["nome"], request.form.get("descricao", ""))
            return redirect(url_for("comunidades.lista"))
        comunidade = svc.obter(cid)
        if not comunidade:
            return redirect(url_for("comunidades.lista"))
        return render_template("comunidades/editar.html", comunidade=comunidade)

    return bp
