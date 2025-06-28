import sqlite3
import psycopg2
from datetime import datetime

class ComunidadeService:
    """
    Classe de serviço para lidar com a lógica de negócios das comunidades.
    Responsável por interagir com o banco de dados.
    """

    def __init__(self, get_db_connection):
        """
        Inicializa o serviço de comunidade com uma função para obter a conexão do DB.
        Isso permite flexibilidade para usar SQLite ou PostgreSQL.
        """
        self.get_db_connection = get_db_connection

    def criar(self, nome, descricao=None, chat_id=None):
        """
        Cria uma nova comunidade no banco de dados.
        Args:
            nome (str): O nome da comunidade (obrigatório).
            descricao (str, optional): A descrição da comunidade. Defaults to None.
            chat_id (int, optional): O ID do chat do Telegram associado à comunidade. Defaults to None.
        Returns:
            dict or None: Um dicionário representando a comunidade criada se sucesso, ou None em caso de falha.
        """
        conn = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print("ERRO SVC: Não foi possível obter conexão com o banco de dados para criar comunidade.")
                return None

            cursor = conn.cursor()
            query = """
                INSERT INTO comunidades (nome, descricao, chat_id, status, created_at)
                VALUES (%s, %s, %s, %s, %s) RETURNING id, nome, descricao, chat_id, status, created_at;
            """
            # Detecta o tipo de banco de dados para ajustar a query e os valores
            if isinstance(conn, sqlite3.Connection):
                query = """
                    INSERT INTO comunidades (nome, descricao, chat_id, status, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """
                cursor.execute(query, (nome, descricao, chat_id, 'ativa', datetime.now().isoformat()))
                conn.commit()
                # Para SQLite, precisamos obter o último ID inserido e depois buscar o registro
                # No PostgreSQL, o RETURNING já retorna os dados.
                last_id = cursor.lastrowid
                cursor.execute("SELECT id, nome, descricao, chat_id, status, created_at FROM comunidades WHERE id = ?", (last_id,))
                comunidade = cursor.fetchone()
            else: # PostgreSQL
                cursor.execute(query, (nome, descricao, chat_id, 'ativa', datetime.now()))
                comunidade = cursor.fetchone()
                conn.commit() # Confirma a transação no PostgreSQL
            
            if comunidade:
                return dict(comunidade) # Converte Row ou RealDictRow para dicionário
            return None
        except (sqlite3.Error, psycopg2.Error) as e:
            print(f"ERRO SVC: Erro ao criar comunidade '{nome}': {e}")
            if conn:
                conn.rollback() # Reverte a transação em caso de erro
            return None
        finally:
            if conn:
                conn.close()

    def obter(self, comunidade_id):
        """
        Obtém uma comunidade pelo seu ID.
        Args:
            comunidade_id (int): O ID da comunidade.
        Returns:
            dict or None: Um dicionário representando a comunidade se encontrada, ou None.
        """
        conn = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print("ERRO SVC: Não foi possível obter conexão com o banco de dados para obter comunidade.")
                return None

            cursor = conn.cursor()
            query = "SELECT id, nome, descricao, chat_id, status, created_at FROM comunidades WHERE id = %s;"
            if isinstance(conn, sqlite3.Connection):
                query = "SELECT id, nome, descricao, chat_id, status, created_at FROM comunidades WHERE id = ?;"
            
            cursor.execute(query, (comunidade_id,))
            comunidade = cursor.fetchone()
            return dict(comunidade) if comunidade else None
        except (sqlite3.Error, psycopg2.Error) as e:
            print(f"ERRO SVC: Erro ao obter comunidade {comunidade_id}: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def listar(self):
        """
        Lista todas as comunidades ativas.
        Returns:
            list: Uma lista de dicionários, cada um representando uma comunidade.
        """
        conn = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print("ERRO SVC: Não foi possível obter conexão com o banco de dados para listar comunidades.")
                return []

            cursor = conn.cursor()
            query = "SELECT id, nome, descricao, chat_id, status, created_at FROM comunidades WHERE status = %s ORDER BY nome;"
            if isinstance(conn, sqlite3.Connection):
                query = "SELECT id, nome, descricao, chat_id, status, created_at FROM comunidades WHERE status = ? ORDER BY nome;"
            
            cursor.execute(query, ('ativa',))
            comunidades = cursor.fetchall()
            return [dict(c) for c in comunidades]
        except (sqlite3.Error, psycopg2.Error) as e:
            print(f"ERRO SVC: Erro ao listar comunidades: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def editar(self, comunidade_id, novo_nome, nova_descricao=None):
        """
        Edita uma comunidade existente.
        Args:
            comunidade_id (int): O ID da comunidade a ser editada.
            novo_nome (str): O novo nome da comunidade.
            nova_descricao (str, optional): A nova descrição. Defaults to None.
        Returns:
            bool: True se a edição foi bem-sucedida, False caso contrário.
        """
        conn = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print("ERRO SVC: Não foi possível obter conexão com o banco de dados para editar comunidade.")
                return False

            cursor = conn.cursor()
            query = """
                UPDATE comunidades
                SET nome = %s, descricao = %s
                WHERE id = %s;
            """
            if isinstance(conn, sqlite3.Connection):
                query = """
                    UPDATE comunidades
                    SET nome = ?, descricao = ?
                    WHERE id = ?;
                """
            
            cursor.execute(query, (novo_nome, nova_descricao, comunidade_id))
            conn.commit() # Confirma a transação
            return cursor.rowcount > 0 # Retorna True se alguma linha foi afetada
        except (sqlite3.Error, psycopg2.Error) as e:
            print(f"ERRO SVC: Erro ao editar comunidade {comunidade_id}: {e}")
            if conn:
                conn.rollback() # Reverte a transação em caso de erro
            return False
        finally:
            if conn:
                conn.close()

    def deletar(self, comunidade_id):
        """
        Altera o status de uma comunidade para 'inativa' (exclusão lógica).
        Args:
            comunidade_id (int): O ID da comunidade a ser desativada.
        Returns:
            bool: True se a desativação foi bem-sucedida, False caso contrário.
        """
        conn = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print("ERRO SVC: Não foi possível obter conexão com o banco de dados para deletar comunidade.")
                return False

            cursor = conn.cursor()
            query = "UPDATE comunidades SET status = %s WHERE id = %s;"
            if isinstance(conn, sqlite3.Connection):
                query = "UPDATE comunidades SET status = ? WHERE id = ?;"
            
            cursor.execute(query, ('inativa', comunidade_id))
            conn.commit()
            return cursor.rowcount > 0
        except (sqlite3.Error, psycopg2.Error) as e:
            print(f"ERRO SVC: Erro ao deletar comunidade {comunidade_id}: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def obter_por_chat_id(self, chat_id):
        """
        Obtém uma comunidade pelo seu chat_id do Telegram.
        Args:
            chat_id (int): O ID do chat do Telegram.
        Returns:
            dict or None: Um dicionário representando a comunidade se encontrada, ou None.
        """
        conn = None
        try:
            conn = self.get_db_connection()
            if conn is None:
                print("ERRO SVC: Não foi possível obter conexão com o banco de dados para obter comunidade por chat_id.")
                return None

            cursor = conn.cursor()
            query = "SELECT id, nome, descricao, chat_id, status, created_at FROM comunidades WHERE chat_id = %s;"
            if isinstance(conn, sqlite3.Connection):
                query = "SELECT id, nome, descricao, chat_id, status, created_at FROM comunidades WHERE chat_id = ?;"
            
            cursor.execute(query, (chat_id,))
            comunidade = cursor.fetchone()
            return dict(comunidade) if comunidade else None
        except (sqlite3.Error, psycopg2.Error) as e:
            print(f"ERRO SVC: Erro ao obter comunidade por chat_id {chat_id}: {e}")
            return None
        finally:
            if conn:
                conn.close()
