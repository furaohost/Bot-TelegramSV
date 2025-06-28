import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor

# Define o nome do banco de dados principal (para SQLite fallback)
DATABASE_NAME = "dashboard.db"

def get_db_connection():
    """
    Estabelece e retorna uma nova conexão com o banco de dados.
    Prioriza PostgreSQL se DATABASE_URL estiver definida, caso contrário, usa SQLite local.
    Configura o cursor_factory para RealDictCursor (PostgreSQL) ou row_factory (SQLite).
    """
    # Tenta obter a URL do banco de dados a partir das variáveis de ambiente
    DATABASE_URL = os.getenv("DATABASE_URL")

    if not DATABASE_URL:
        # Se DATABASE_URL não estiver definida, usa SQLite local
        print("AVISO: DATABASE_URL não definida, usando SQLite local.")
        # O caminho do banco de dados SQLite será o diretório atual do projeto
        # Use um nome de DB diferente para evitar conflito com 'dashboard.db' que é o nome para deploy
        # ou se certifique que 'dashboard.db' é para SQLite
        db_path = os.path.join(os.getcwd(), DATABASE_NAME)
        try:
            # Conecta ao banco de dados. Se o arquivo não existir, ele será criado.
            # check_same_thread=False é importante para Flask, pois diferentes
            # threads de requisição podem tentar usar a mesma conexão.
            conn = sqlite3.connect(db_path, check_same_thread=False)
            # Permite acessar as colunas por nome (como um dicionário)
            conn.row_factory = sqlite3.Row
            print(f"DEBUG DB: Conectado ao SQLite local em '{db_path}'.")
            return conn
        except sqlite3.Error as e:
            print(f"ERRO DB: Falha ao conectar ao SQLite: {e}")
            raise # Levanta a exceção para que a aplicação saiba que a conexão falhou
    
    # Se DATABASE_URL estiver definida, tenta conectar ao PostgreSQL
    try:
        # Conecta ao PostgreSQL usando a URL fornecida
        # cursor_factory=RealDictCursor permite acessar os resultados das consultas
        # como dicionários, o que é muito conveniente.
        # sslmode="require" é importante para conexões seguras em ambientes de deploy.
        conn = psycopg2.connect(
            DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require"
        )
        # Define autocommit como False para que as transações precisem ser confirmadas
        # explicitamente com conn.commit() ou revertidas com conn.rollback().
        conn.autocommit = False
        print("DEBUG DB: Conectado ao PostgreSQL.")
        return conn
    except Exception as e:
        print(f"ERRO DB: Falha ao conectar ao PostgreSQL: {e}")
        raise

# --- Opcional: Bloco de teste (descomente para testar este arquivo isoladamente) ---
# if __name__ == '__main__':
#     conn = None
#     try:
#         conn = get_db_connection()
#         if conn:
#             print("Conexão com o banco de dados estabelecida com sucesso!")
#             cursor = conn.cursor()
#             cursor.execute("SELECT 1;")
#             print("Consulta de teste executada.")
#         else:
#             print("Não foi possível estabelecer a conexão com o banco de dados.")
#     except Exception as e:
#         print(f"Erro inesperado no teste de conexão: {e}")
#     finally:
#         if conn:
#             conn.close()
#             print("Conexão com o banco de dados fechada.")