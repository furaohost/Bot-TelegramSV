# bot/services/comunidades.py

import psycopg2
from datetime import datetime

class ComunidadeService:
    def __init__(self, get_db_connection_func):
        """
        Inicializa o serviço com uma função que obtém uma conexão com o banco.
        """
        self.get_db_connection = get_db_connection_func

    def _execute_query(self, query, params=None, fetch=None):
        """
        Função auxiliar para executar consultas no banco de dados.
        Retorna o resultado da consulta (dict para fetchone, lista de dicts para fetchall, ou None/True/False para outros).
        """
        conn = None
        cur = None
        result = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print("ERRO DB: Não foi possível obter conexão com a base de dados.")
                return None
            
            with conn: # Isso garante que a transação é commitada ou revertida automaticamente
                cur = conn.cursor()
                cur.execute(query, params or ())
                
                if fetch == 'one':
                    # Obtém os nomes das colunas para mapear para dicionário
                    col_names = [desc[0] for desc in cur.description]
                    row = cur.fetchone()
                    result = dict(zip(col_names, row)) if row else None
                elif fetch == 'all':
                    col_names = [desc[0] for desc in cur.description]
                    rows = cur.fetchall()
                    result = [dict(zip(col_names, row)) for row in rows]
                else:
                    # Para INSERT, UPDATE, DELETE: retorna o número de linhas afetadas
                    result = cur.rowcount if cur else 0
                
        except psycopg2.Error as e: # Captura erros específicos do Psycopg2
            print(f"ERRO DB (_execute_query) - Query: {query}, Params: {params} | Erro: {e}")
            return None
        except Exception as e: # Captura outros erros gerais
            print(f"ERRO GERAL (_execute_query): {e}")
            return None
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close() # Sempre fecha a conexão
        return result

    def listar(self, ativos_apenas=False):
        """Lista todas as comunidades, opcionalmente apenas as ativas."""
        query = "SELECT id, nome, descricao, chat_id, status, created_at FROM comunidades"
        params = ()
        if ativos_apenas:
            query += " WHERE status = 'ativa'"
        query += " ORDER BY nome ASC"
        return self._execute_query(query, params, fetch='all')

    def obter(self, comunidade_id):
        """Obtém uma comunidade específica pelo ID."""
        query = "SELECT id, nome, descricao, chat_id, status, created_at FROM comunidades WHERE id = %s"
        return self._execute_query(query, (comunidade_id,), fetch='one')

    def criar(self, nome, descricao=None, chat_id=None):
        """Cria uma nova comunidade e retorna o objeto da comunidade criada."""
        # Define status inicial como 'ativa' e created_at como o tempo atual
        query = """
            INSERT INTO comunidades (nome, descricao, chat_id, status, created_at)
            VALUES (%s, %s, %s, %s, %s) RETURNING id, nome, descricao, chat_id, status, created_at;
        """
        params = (nome, descricao, chat_id, 'ativa', datetime.now())
        try:
            # Ao usar RETURNING, fetchone é apropriado para obter o objeto recém-criado
            comunidade_criada = self._execute_query(query, params, fetch='one')
            return comunidade_criada
        except Exception as e:
            print(f"Erro ao criar comunidade no DB: {e}")
            return None # Retorna None em caso de falha

    def editar(self, comunidade_id, nome=None, descricao=None, chat_id=None, status=None):
        """Edita uma comunidade existente. Retorna True se editado, False caso contrário."""
        updates = []
        params = []
        
        if nome is not None:
            updates.append("nome = %s")
            params.append(nome)
        if descricao is not None:
            updates.append("descricao = %s")
            params.append(descricao)
        if chat_id is not None:
            updates.append("chat_id = %s")
            params.append(chat_id)
        if status is not None:
            updates.append("status = %s")
            params.append(status)

        if not updates: # Nenhuma atualização a ser feita
            return False

        query = f"UPDATE comunidades SET {', '.join(updates)} WHERE id = %s"
        params.append(comunidade_id)

        rows_affected = self._execute_query(query, tuple(params))
        return rows_affected > 0 # Retorna True se pelo menos uma linha foi afetada

    def desativar(self, comunidade_id):
        """Desativa uma comunidade (muda o status para 'inativa')."""
        query = "UPDATE comunidades SET status = 'inativa' WHERE id = %s"
        rows_affected = self._execute_query(query, (comunidade_id,))
        return rows_affected > 0

    def ativar(self, comunidade_id):
        """Ativa uma comunidade (muda o status para 'ativa')."""
        query = "UPDATE comunidades SET status = 'ativa' WHERE id = %s"
        rows_affected = self._execute_query(query, (comunidade_id,))
        return rows_affected > 0

    def excluir_permanentemente(self, comunidade_id):
        """
        EXCLUI PERMANENTEMENTE uma comunidade do banco de dados.
        Use com EXTREMA CAUTELA! Geralmente é melhor desativar.
        """
        query = "DELETE FROM comunidades WHERE id = %s"
        rows_affected = self._execute_query(query, (comunidade_id,))
        return rows_affected > 0