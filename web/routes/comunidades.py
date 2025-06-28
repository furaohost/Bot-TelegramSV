# -*- coding: utf-8 -*-
"""
Blueprint de Comunidades para o painel Flask.
Caminho base: /comunidades
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
# Importa o serviço de comunidades (ajustado para a nova estrutura)
from bot.services.comunidades import ComunidadeService 

def create_comunidades_blueprint(get_db_connection_func):
    """
    Cria e configura o Blueprint Flask para as rotas de gerenciamento de comunidades.
    Args:
        get_db_connection_func (function): Função para obter a conexão do DB.
    Returns:
        Blueprint: O Blueprint configurado.
    """
    # Define o Blueprint com um prefixo de URL para todas as rotas
    bp = Blueprint("comunidades", __name__, url_prefix="/comunidades")
    
    # Inicializa o serviço de comunidades com a função de conexão do DB
    svc = ComunidadeService(get_db_connection_func)

    # ------------------------------------------------------------------
    # LISTAR Comunidades (GET /comunidades/)
    # ------------------------------------------------------------------
    @bp.route("/", methods=["GET"])
    def lista():
        """
        Exibe a lista de todas as comunidades ativas.
        """
        comunidades = svc.listar()
        return render_template("comunidades/lista.html", comunidades=comunidades)

    # ------------------------------------------------------------------
    # FORMULARIO NOVA Comunidade / CRIAR (GET /comunidades/nova, POST /comunidades/nova)
    # ------------------------------------------------------------------
    @bp.route("/nova", methods=["GET", "POST"])
    def nova():
        """
        Exibe o formulário para criar uma nova comunidade (GET)
        ou processa a submissão do formulário para criar a comunidade (POST).
        """
        if request.method == "POST":
            nome = request.form["nome"].strip()
            descricao = request.form.get("descricao", "").strip() # Pega a descrição, pode ser vazia
            
            if not nome:
                flash("O nome da comunidade é obrigatório.", "error")
                return render_template("comunidades/nova.html", nome=nome, descricao=descricao)

            # Aqui você pode adicionar validações adicionais, como chat_id se necessário na web
            # Por enquanto, chat_id é opcional e pode ser definido pelo bot.

            nova_comunidade = svc.criar(nome, descricao)
            if nova_comunidade:
                flash(f"Comunidade '{nova_comunidade['nome']}' criada com sucesso!", "success")
                return redirect(url_for("comunidades.lista"))
            else:
                flash("Erro ao criar a comunidade. Tente novamente.", "error")
        
        # Renderiza o formulário para GET requests ou POST com erro
        return render_template("comunidades/nova.html")

    # ------------------------------------------------------------------
    # EDITAR Comunidade (GET /comunidades/<id>/editar, POST /comunidades/<id>/editar)
    # ------------------------------------------------------------------
    @bp.route("/<int:cid>/editar", methods=["GET", "POST"])
    def editar(cid):
        """
        Exibe o formulário para editar uma comunidade existente (GET)
        ou processa a submissão do formulário para atualizar a comunidade (POST).
        Args:
            cid (int): O ID da comunidade a ser editada.
        """
        comunidade = svc.obter(cid)
        if not comunidade:
            flash("Comunidade não encontrada.", "error")
            return redirect(url_for("comunidades.lista"))

        if request.method == "POST":
            novo_nome = request.form["nome"].strip()
            nova_descricao = request.form.get("descricao", "").strip()

            if not novo_nome:
                flash("O nome da comunidade é obrigatório.", "error")
                return render_template("comunidades/editar.html", comunidade=comunidade) # Permanece na página de edição com erro

            sucesso = svc.editar(cid, novo_nome, nova_descricao)
            if sucesso:
                flash(f"Comunidade '{novo_nome}' atualizada com sucesso!", "success")
                return redirect(url_for("comunidades.lista"))
            else:
                flash("Erro ao atualizar a comunidade. Tente novamente.", "error")
        
        # Renderiza o formulário para GET requests ou POST com erro
        return render_template("comunidades/editar.html", comunidade=comunidade)
    
    # ------------------------------------------------------------------
    # DELETAR Comunidade (POST /comunidades/<id>/deletar)
    # Esta rota é para exclusão lógica (muda o status para 'inativa')
    # ------------------------------------------------------------------
    @bp.route("/<int:cid>/deletar", methods=["POST"])
    def deletar(cid):
        """
        Processa a requisição para "deletar" (desativar) uma comunidade.
        Args:
            cid (int): O ID da comunidade a ser desativada.
        """
        sucesso = svc.deletar(cid)
        if sucesso:
            flash("Comunidade desativada com sucesso!", "success")
        else:
            flash("Erro ao desativar a comunidade.", "error")
        return redirect(url_for("comunidades.lista"))


    return bp

