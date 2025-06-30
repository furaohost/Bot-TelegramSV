# bot/services/comunidades.py

# Este arquivo deve conter APENAS a classe de serviço para interagir com o banco de dados.
# Nenhuma rota da web (@...route) deve estar aqui.

class ComunidadeService:
    def __init__(self, get_db_connection_func):
        """
        Inicializa o serviço com uma função que obtém uma conexão com o banco.
        """
        self.get_db_connection = get_db_connection_func

    def _execute_query(self, query, params=None, fetch=None):
        """
        Função auxiliar para executar consultas no banco de dados.
        """
        conn = None
        result = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print("ERRO DB: Não foi possível obter conexão com a base de dados.")
                return None
            
            with conn:
                cur = conn.cursor()
                cur.execute(query, params or ())
                
                if fetch == 'one':
                    result = cur.fetchone()
                elif fetch == 'all':
                    result = cur.fetchall()
                # Se fetch for None, é uma operação como INSERT, UPDATE, DELETE
                
        except Exception as e:
            print(f"ERRO DB (_execute_query): {e}")
            # Em caso de erro, retorna None
            return None
        finally:
            if conn:
                conn.close()
        return result

    def listar(self):
        """Lista todas as comunidades."""
        return self._execute_query("SELECT * FROM comunidades ORDER BY nome ASC", fetch='all')

    def obter(self, comunidade_id):
        """Obtém uma comunidade específica pelo ID."""
        return self._execute_query("SELECT * FROM comunidades WHERE id = %s", (comunidade_id,), fetch='one')

    def criar(self, nome, descricao, chat_id):
        """Cria uma nova comunidade."""
        self._execute_query(
            "INSERT INTO comunidades (nome, descricao, chat_id) VALUES (%s, %s, %s)",
            (nome, descricao, chat_id)
        )
        return True # Assumindo sucesso se não houver exceção

    def editar(self, comunidade_id, nome, descricao, chat_id):
        """Edita uma comunidade existente."""
        self._execute_query(
            "UPDATE comunidades SET nome = %s, descricao = %s, chat_id = %s WHERE id = %s",
            (nome, descricao, chat_id, comunidade_id)
        )
        return True # Assumindo sucesso se não houver exceção

    def deletar(self, comunidade_id):
        """Deleta uma comunidade pelo ID."""
        self._execute_query("DELETE FROM comunidades WHERE id = %s", (comunidade_id,))
        return True # Assumindo sucesso se não houver exceção