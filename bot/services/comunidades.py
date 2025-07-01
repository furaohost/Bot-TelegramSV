# bot/services/comunidades.py
# CORRIGIDO: Agora usa DictCursor para retornar dicionários em vez de tuplos.

class ComunidadeService:
    def __init__(self, get_db_connection_func):
        """
        Inicializa o serviço com uma função que obtém uma conexão com o banco.
        """
        self.get_db_connection = get_db_connection_func

    def _execute_query(self, query, params=None, fetch=None):
        """
        Função auxiliar para executar consultas no banco de dados,
        garantindo que os resultados sejam dicionários.
        """
        conn = None
        result = None
        try:
            # Pega uma conexão nova para cada operação para garantir segurança.
            conn = self.get_db_connection()
            if conn is None:
                print("ERRO DB: Não foi possível obter conexão com a base de dados.")
                return None
            
            # Usa 'with conn' para gestão de transações (commit/rollback)
            with conn:
                # Usa 'with cur' para garantir que o cursor seja fechado
                with conn.cursor() as cur:
                    cur.execute(query, params or ())
                    
                    if fetch == 'one':
                        result = cur.fetchone()
                    elif fetch == 'all':
                        result = cur.fetchall()
                    # Se fetch for None (INSERT, UPDATE, DELETE), a transação é commitada
                    # automaticamente ao sair do bloco 'with conn'.
        
        except Exception as e:
            print(f"ERRO DB (_execute_query): {e}")
            # Em caso de erro, a transação é desfeita e retorna None.
            return None
        finally:
            # Garante que a conexão seja sempre fechada.
            if conn:
                conn.close()
        return result

    def listar(self):
        """Lista todas as comunidades, ordenadas por nome."""
        query = "SELECT * FROM comunidades ORDER BY nome ASC"
        return self._execute_query(query, fetch='all')

    def obter(self, comunidade_id):
        """Obtém uma comunidade específica pelo seu ID."""
        query = "SELECT * FROM comunidades WHERE id = %s"
        return self._execute_query(query, (comunidade_id,), fetch='one')

    def criar(self, nome, descricao, chat_id):
        """Cria uma nova comunidade no banco de dados."""
        query = "INSERT INTO comunidades (nome, descricao, chat_id) VALUES (%s, %s, %s)"
        # Retorna o resultado da execução para saber se houve sucesso
        return self._execute_query(query, (nome, descricao, chat_id))

    def editar(self, comunidade_id, nome, descricao, chat_id):
        """Edita os dados de uma comunidade existente."""
        query = "UPDATE comunidades SET nome = %s, descricao = %s, chat_id = %s WHERE id = %s"
        return self._execute_query(query, (nome, descricao, chat_id, comunidade_id))

    def deletar(self, comunidade_id):
        """Deleta uma comunidade do banco de dados."""
        query = "DELETE FROM comunidades WHERE id = %s"
        return self._execute_query(query, (comunidade_id,))