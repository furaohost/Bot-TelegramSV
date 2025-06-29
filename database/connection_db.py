# database/connection_db.py (ou database/database.py, se você não renomeou)
import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_NAME = "dashboard.db"

def get_db_connection():
    DATABASE_URL = os.getenv("DATABASE_URL")

    if not DATABASE_URL:
        print("AVISO: DATABASE_URL não definida, usando SQLite local.")
        db_path = os.path.join(os.getcwd(), DATABASE_NAME)
        try:
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            print(f"DEBUG DB: Conectado ao SQLite local em '{db_path}'.")
            return conn
        except sqlite3.Error as e:
            print(f"ERRO DB: Falha ao conectar ao SQLite: {e}")
            # Em vez de levantar, retornamos None para que o chamador possa lidar
            return None 
            # Se for um erro fatal de deploy, raise pode ser útil para o Render falhar o build
            # raise # Descomente esta linha se você quer que o erro pare o deploy no Render
    
    try:
        conn = psycopg2.connect(
            DATABASE_URL, cursor_factory=RealDictCursor, sslmode="require"
        )
        conn.autocommit = False
        print("DEBUG DB: Conectado ao PostgreSQL.")
        return conn
    except Exception as e:
        print(f"ERRO DB: Falha ao conectar ao PostgreSQL: {e}")
        # Em vez de levantar, retornamos None para que o chamador possa lidar
        return None
        # raise # Descomente esta linha se você quer que o erro pare o deploy no Render

# A seção if __name__ == '__main__': (de teste) não precisa ser enviada no deploy
# mas pode ficar comentada para uso local.
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