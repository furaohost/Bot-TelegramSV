# bot/services/comunidades.py
import sqlite3 # Adicionado para verificar tipo de conexão
import traceback # Para depuração de erros em serviços

# A classe ComunidadeService não importa a si mesma.
# Ela depende de get_db_connection_func que é passada no construtor.

class ComunidadeService:
    def __init__(self, get_db_connection_func):
        self.get_db_connection = get_db_connection_func

    def criar(self, nome, descricao=None, chat_id=None):
        conn = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print("ERRO ComunidadeService: Não foi possível obter conexão com a base de dados.")
                return None

            is_sqlite = isinstance(conn, sqlite3.Connection)
            with conn:
                cur = conn.cursor()
                if is_sqlite:
                    cur.execute("INSERT INTO comunidades (nome, descricao, chat_id) VALUES (?, ?, ?)",
                                (nome, descricao, chat_id))
                    cur.execute("SELECT last_insert_rowid()")
                    new_id = cur.fetchone()[0]
                else:
                    cur.execute("INSERT INTO comunidades (nome, descricao, chat_id) VALUES (%s, %s, %s) RETURNING id",
                                (nome, descricao, chat_id))
                    new_id = cur.fetchone()[0]
                
                # Retorna os dados da nova comunidade para confirmação
                return {"id": new_id, "nome": nome, "descricao": descricao, "chat_id": chat_id}
        except Exception as e:
            print(f"ERRO ComunidadeService.criar: {e}")
            traceback.print_exc()
            return None
        finally:
            if conn:
                conn.close()

    def listar(self):
        conn = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print("ERRO ComunidadeService: Não foi possível obter conexão com a base de dados para listar.")
                return []
            
            is_sqlite = isinstance(conn, sqlite3.Connection)
            with conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM comunidades ORDER BY nome")
                return cur.fetchall()
        except Exception as e:
            print(f"ERRO ComunidadeService.listar: {e}")
            traceback.print_exc()
            return []
        finally:
            if conn:
                conn.close()

    def obter(self, id):
        conn = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print("ERRO ComunidadeService: Não foi possível obter conexão com a base de dados para obter.")
                return None

            is_sqlite = isinstance(conn, sqlite3.Connection)
            with conn:
                cur = conn.cursor()
                if is_sqlite:
                    cur.execute("SELECT * FROM comunidades WHERE id = ?", (id,))
                else:
                    cur.execute("SELECT * FROM comunidades WHERE id = %s", (id,))
                return cur.fetchone()
        except Exception as e:
            print(f"ERRO ComunidadeService.obter: {e}")
            traceback.print_exc()
            return None
        finally:
            if conn:
                conn.close()

    def editar(self, id, nome, descricao=None, chat_id=None):
        conn = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print("ERRO ComunidadeService: Não foi possível obter conexão com a base de dados para editar.")
                return False

            is_sqlite = isinstance(conn, sqlite3.Connection)
            with conn:
                cur = conn.cursor()
                if is_sqlite:
                    cur.execute("UPDATE comunidades SET nome = ?, descricao = ?, chat_id = ? WHERE id = ?",
                                (nome, descricao, chat_id, id))
                else:
                    cur.execute("UPDATE comunidades SET nome = %s, descricao = %s, chat_id = %s WHERE id = %s",
                                (nome, descricao, chat_id, id))
                return cur.rowcount > 0 # Retorna True se alguma linha foi afetada
        except Exception as e:
            print(f"ERRO ComunidadeService.editar: {e}")
            traceback.print_exc()
            return False
        finally:
            if conn:
                conn.close()

    def deletar(self, id):
        conn = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print("ERRO ComunidadeService: Não foi possível obter conexão com a base de dados para deletar.")
                return False

            is_sqlite = isinstance(conn, sqlite3.Connection)
            with conn:
                cur = conn.cursor()
                if is_sqlite:
                    cur.execute("DELETE FROM comunidades WHERE id = ?", (id,))
                else:
                    cur.execute("DELETE FROM comunidades WHERE id = %s", (id,))
                return cur.rowcount > 0 # Retorna True se alguma linha foi afetada
        except Exception as e:
            print(f"ERRO ComunidadeService.deletar: {e}")
            traceback.print_exc()
            return False
        finally:
            if conn:
                conn.close()