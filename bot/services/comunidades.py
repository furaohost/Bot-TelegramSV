# bot/services/comunidades.py
# CORRIGIDO: Agora usa DictCursor para retornar dicionários em vez de tuplos.
import sqlite3 # Importado para verificar tipo de conexão
import traceback # Para logs de erro mais detalhados

class ComunidadeService:
    def __init__(self, get_db_connection_func):
        """
        Inicializa o serviço com uma função que obtém uma conexão com o banco.
        """
        self.get_db_connection = get_db_connection_func

    def _execute_query(self, query, params=None, fetch=None, return_id=False):
        """
        Função auxiliar para executar consultas no banco de dados,
        garantindo que os resultados sejam dicionários.
        Inclui o tratamento para SQLite/PostgreSQL e retorno de ID.
        """
        conn = None
        result = None
        last_insert_id = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print("ERRO DB: Não foi possível obter conexão com a base de dados.")
                return None
            
            is_sqlite = isinstance(conn, sqlite3.Connection)

            with conn:
                with conn.cursor() as cur:
                    # Ajusta o placeholder da query se for SQLite
                    if is_sqlite:
                        query = query.replace('%s', '?')

                    cur.execute(query, params or ())
                    
                    if fetch == 'one':
                        result = cur.fetchone()
                    elif fetch == 'all':
                        result = cur.fetchall()
                    
                    if return_id:
                        if is_sqlite:
                            cur.execute("SELECT last_insert_rowid()")
                            last_insert_id = cur.fetchone()[0]
                        else:
                            # Para PostgreSQL, assumimos que a query INSERT já usa RETURNING id
                            # e o fetchone() já traz o resultado.
                            # Ex: "INSERT INTO ... RETURNING id"
                            # Se a query não tiver RETURNING id, você precisaria de outra forma
                            # de obter o ID, ou não usar return_id para inserts em PG.
                            pass 

        except Exception as e:
            print(f"ERRO DB (_execute_query): {e}")
            traceback.print_exc() # Adicionado para ver o traceback completo
            if conn: # Garante rollback em caso de erro
                conn.rollback() 
            return None
        finally:
            if conn:
                conn.close()
        
        if return_id:
            # Para inserts, new_id pode ser um dicionário/tupla com o ID ou None
            return last_insert_id if last_insert_id is not None else result 
        return result

    def listar(self):
        """Lista todas as comunidades, ordenadas por nome."""
        query = "SELECT * FROM comunidades ORDER BY nome ASC"
        return self._execute_query(query, fetch='all')

    def obter(self, comunidade_id):
        """Obtém uma comunidade específica pelo seu ID."""
        query = "SELECT * FROM comunidades WHERE id = %s"
        return self._execute_query(query, (comunidade_id,), fetch='one')

    def obter_por_chat_id(self, chat_id):
        """
        NOVA FUNÇÃO: Obtém uma comunidade específica pelo seu Chat ID do Telegram.
        """
        query = "SELECT * FROM comunidades WHERE chat_id = %s"
        params = (chat_id,)
        if isinstance(self.get_db_connection(), sqlite3.Connection):
            query = query.replace('%s', '?')
        return self._execute_query(query, params, fetch='one')

    def criar(self, nome, descricao, chat_id):
        """Cria uma nova comunidade no banco de dados."""
        # Use RETURNING id para PostgreSQL para obter o ID do novo registro
        query = "INSERT INTO comunidades (nome, descricao, chat_id) VALUES (%s, %s, %s) RETURNING id"
        params = (nome, descricao, chat_id)
        
        if isinstance(self.get_db_connection(), sqlite3.Connection):
            query = "INSERT INTO comunidades (nome, descricao, chat_id) VALUES (?, ?, ?)"
            return_id_flag = True
        else:
            return_id_flag = False # Para PG, o RETURNING id já será parte do fetchone se a query incluir

        new_id_result = self._execute_query(query, params, fetch='one', return_id=return_id_flag) 
        
        if new_id_result:
            # Em PostgreSQL com RETURNING id, fetchone() retorna uma tupla ou dicionário
            # com o ID. Precisamos extraí-lo.
            if isinstance(new_id_result, dict) and 'id' in new_id_result:
                new_id = new_id_result['id']
            elif isinstance(new_id_result, (tuple, list)) and new_id_result:
                new_id = new_id_result[0]
            else:
                new_id = new_id_result # Caso seja um valor simples diretamente (ex: de return_id para SQLite)

            if new_id is not None:
                return self.obter(new_id) # Retorna o objeto completo da nova comunidade
        return None # Retorna None se não conseguir criar ou obter o ID

    def editar(self, comunidade_id, nome, descricao, chat_id):
        """Edita os dados de uma comunidade existente."""
        query = "UPDATE comunidades SET nome = %s, descricao = %s, chat_id = %s WHERE id = %s"
        return self._execute_query(query, (nome, descricao, chat_id, comunidade_id))

    def deletar(self, comunidade_id):
        """Deleta uma comunidade do banco de dados (funcionalidade original mantida)."""
        query = "DELETE FROM comunidades WHERE id = %s"
        return self._execute_query(query, (comunidade_id,))