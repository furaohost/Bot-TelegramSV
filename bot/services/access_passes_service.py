# bot/services/access_passes_service.py
import sqlite3
import traceback

class AccessPassService:
    def __init__(self, get_db_connection_func):
        self.get_db_connection = get_db_connection_func

    def _execute_query(self, query, params=None, fetch=None, return_id=False):
        conn = None
        result = None
        last_insert_id = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print(f"ERRO DB: AccessPassService - Não foi possível obter conexão com a base de dados.")
                return None
            
            is_sqlite = isinstance(conn, sqlite3.Connection)
            # Garante que o cursor retorne dicionários para consistência (para sqlite)
            if is_sqlite:
                conn.row_factory = sqlite3.Row

            with conn:
                with conn.cursor() as cur:
                    if is_sqlite:
                        query = query.replace('%s', '?') # Substitui %s por ? para SQLite

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
                            # Para PostgreSQL, RETURNING id já pega o ID. Result deve ser o ID.
                            # Se a query original era '... RETURNING id', o ID já estará em 'result'
                            if result and isinstance(result, dict) and 'id' in result:
                                last_insert_id = result['id']
                            elif result and isinstance(result, (list, tuple)) and result:
                                last_insert_id = result[0]
                            # Se não é SQLite e não tinha RETURNING, last_insert_id permanece None
                            pass 

        except Exception as e:
            print(f"ERRO DB (AccessPassService._execute_query): {e}")
            traceback.print_exc() 
            if conn: 
                conn.rollback() # Garante rollback em caso de erro
            return None
        finally:
            if conn:
                conn.close()
        
        if return_id:
            return last_insert_id if last_insert_id is not None else result
        return result

    def listar(self):
        query = "SELECT * FROM access_passes ORDER BY name ASC"
        return self._execute_query(query, fetch='all')

    def obter(self, pass_id):
        query = "SELECT * FROM access_passes WHERE id = %s"
        return self._execute_query(query, (pass_id,), fetch='one')
    
    def criar(self, name, description, price, duration_days, community_id):
        query = """
        INSERT INTO access_passes (name, description, price, duration_days, community_id, is_active)
        VALUES (%s, %s, %s, %s, %s, TRUE) RETURNING id
        """
        params = (name, description, price, duration_days, community_id)
        
        # Para SQLite, remove RETURNING id da query e usa return_id=True para last_insert_rowid()
        if isinstance(self.get_db_connection(), sqlite3.Connection):
            query = """
            INSERT INTO access_passes (name, description, price, duration_days, community_id, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            """
            new_id = self._execute_query(query, params, return_id=True)
        else:
            new_id_result = self._execute_query(query, params, fetch='one')
            new_id = new_id_result['id'] if new_id_result and 'id' in new_id_result else None

        if new_id:
            return self.obter(new_id)
        return None

    def editar(self, pass_id, name, description, price, duration_days, community_id, is_active):
        query = """
        UPDATE access_passes 
        SET name = %s, description = %s, price = %s, duration_days = %s, community_id = %s, is_active = %s
        WHERE id = %s
        """
        params = (name, description, price, duration_days, community_id, is_active, pass_id)
        return self._execute_query(query, params)

    def deletar(self, pass_id):
        query = "DELETE FROM access_passes WHERE id = %s"
        return self._execute_query(query, (pass_id,))