# bot/services/comunidades.py
import sqlite3 
import traceback 

class ComunidadeService:
    def __init__(self, get_db_connection_func):
        self.get_db_connection = get_db_connection_func

    def _execute_query(self, query, params=None, fetch=None, return_id=False):
        conn = None
        result = None
        last_insert_id = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print(f"ERRO DB: Não foi possível obter conexão com a base de dados.")
                return None
            
            is_sqlite = isinstance(conn, sqlite3.Connection)

            with conn:
                with conn.cursor() as cur:
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
                            pass 

        except Exception as e:
            print(f"ERRO DB (_execute_query): {e}")
            traceback.print_exc() 
            if conn: 
                conn.rollback() 
            return None
        finally:
            if conn:
                conn.close()
        
        if return_id:
            return last_insert_id if last_insert_id is not None else result 
        return result

    def listar(self):
        query = "SELECT * FROM comunidades ORDER BY nome ASC"
        return self._execute_query(query, fetch='all')

    def obter(self, comunidade_id):
        query = "SELECT * FROM comunidades WHERE id = %s"
        return self._execute_query(query, (comunidade_id,), fetch='one')

    def obter_por_chat_id(self, chat_id):
        """
        Obtém uma comunidade específica pelo seu Chat ID do Telegram.
        """
        query = "SELECT * FROM comunidades WHERE chat_id = %s"
        params = (chat_id,)
        if isinstance(self.get_db_connection(), sqlite3.Connection):
            query = query.replace('%s', '?')
        return self._execute_query(query, params, fetch='one')

    def criar(self, nome, descricao, chat_id):
        query = "INSERT INTO comunidades (nome, descricao, chat_id) VALUES (%s, %s, %s) RETURNING id"
        params = (nome, descricao, chat_id)
        
        if isinstance(self.get_db_connection(), sqlite3.Connection):
            query = "INSERT INTO comunidades (nome, descricao, chat_id) VALUES (?, ?, ?)"
            return_id_flag = True
        else:
            return_id_flag = False 

        new_id_result = self._execute_query(query, params, fetch='one', return_id=return_id_flag) 
        
        if new_id_result:
            if isinstance(new_id_result, dict) and 'id' in new_id_result:
                new_id = new_id_result['id']
            elif isinstance(new_id_result, (tuple, list)) and new_id_result:
                new_id = new_id_result[0]
            else:
                new_id = new_id_result 

            if new_id is not None:
                return self.obter(new_id) 
        return None 

    def editar(self, comunidade_id, nome, descricao, chat_id):
        query = "UPDATE comunidades SET nome = %s, descricao = %s, chat_id = %s WHERE id = %s"
        params = (nome, descricao, chat_id, comunidade_id)
        return self._execute_query(query, params) 

    def deletar(self, comunidade_id):
        query = "DELETE FROM comunidades WHERE id = %s"
        return self._execute_query(query, (comunidade_id,))