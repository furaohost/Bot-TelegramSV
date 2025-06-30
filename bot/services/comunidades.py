# web/routes/comunidades.py

@comunidades_bp.route('/comunidades/editar/<int:id>', methods=['GET', 'POST'])
def editar_comunidade(id): # <-- Endpoint: 'comunidades.editar_comunidade'
    comunidade_service = ComunidadeService(get_db_connection)
    
    # Busca a comunidade para garantir que ela existe antes de mais nada
    comunidade = comunidade_service.obter(id)
    if not comunidade:
        flash('Comunidade não encontrada.', 'danger')
        return redirect(url_for('comunidades.comunidades'))

    try:
        if request.method == 'POST':
            # Pega os dados do formulário
            nome = request.form['nome'].strip()
            descricao = request.form.get('descricao', '').strip()
            chat_id_str = request.form.get('chat_id', '').strip()
            chat_id = None

            # Validação do chat_id
            if chat_id_str:
                try:
                    chat_id = int(chat_id_str)
                except ValueError:
                    flash('ID do Chat/Grupo inválido. Deve ser um número.', 'danger')
                    # Se der erro, renderiza a página de novo com os dados que o utilizador já inseriu
                    return render_template('editar_comunidade.html', 
                                           comunidade=comunidade, 
                                           nome_val=nome, 
                                           descricao_val=descricao, 
                                           chat_id_val=chat_id_str)

            # Tenta editar no banco de dados
            sucesso = comunidade_service.editar(id, nome, descricao, chat_id)
            if sucesso:
                flash('Comunidade atualizada com sucesso!', 'success')
                return redirect(url_for('comunidades.comunidades'))
            else:
                flash('Falha ao atualizar a comunidade. Tente novamente.', 'danger')

        # Se for um pedido GET (primeiro acesso à página), apenas mostra o formulário
        return render_template('editar_comunidade.html', 
                               comunidade=comunidade, 
                               nome_val=comunidade['nome'], 
                               descricao_val=comunidade['descricao'], 
                               chat_id_val=comunidade['chat_id'] or '')

    except Exception as e:
        print(f"ERRO ao editar comunidade: {e}")
        flash('Ocorreu um erro inesperado ao editar a comunidade.', 'danger')
        return redirect(url_for('comunidades.comunidades'))