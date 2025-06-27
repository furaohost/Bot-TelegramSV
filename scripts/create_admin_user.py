import os
# import sqlite3 # Não precisamos mais de sqlite3 aqui
import getpass # Ainda útil para gerar senha localmente, mas não no deploy
from werkzeug.security import generate_password_hash # Para criptografar a senha

# Imports para PostgreSQL
import psycopg2
from psycopg2.extras import RealDictCursor # Para retornar linhas como dicionários

# --- CONFIGURAÇÃO: Lendo DATABASE_URL do ambiente ---
# No Render, essa variável já está disponível no ambiente de execução.
# Localmente, você pode definir em um arquivo .env ou no seu ambiente.
DATABASE_URL = os.getenv('DATABASE_URL') 

# --- Importa dotenv para carregar variáveis LOCALMENTE (se for testar no PC) ---
# No Render, esta parte será ignorada ou não fará diferença pois o ambiente já injeta as variáveis.
try:
    from dotenv import load_dotenv
    load_dotenv()
    if not DATABASE_URL: # Tenta carregar DATABASE_URL do .env se não veio do ambiente
        DATABASE_URL = os.getenv('DATABASE_URL')
except ImportError:
    # dotenv não está instalada ou não é necessária (ex: no Render)
    pass


# --- Credenciais do ADMINISTRADOR (DEFINIDAS AQUI) ---
# ESTES VALORES SERÃO USADOS PARA INSERIR O ADMIN NO DB
ADMIN_USERNAME = "admin" # <<<<< USERNAME FIXO: admin
ADMIN_PASSWORD = "admin123" # <<<<< SENHA FIXA: admin123
# ---------------------------------------------------

def create_admin_user():
    print("--- Criação de Usuário Administrador para PostgreSQL ---")
    
    if not DATABASE_URL:
        print("\n[ERRO FATAL] A variável de ambiente DATABASE_URL não está definida.")
        print("Certifique-se de que ela está configurada no Render ou no seu arquivo .env local.")
        return

    conn = None
    cur = None
    try:
        # Conecta ao banco de dados PostgreSQL
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode='require')
        cur = conn.cursor()

        # Criptografa a senha (usando o método recomendado 'pbkdf2:sha256')
        hashed_password = generate_password_hash(ADMIN_PASSWORD, method='pbkdf2:sha256')

        # Insere o novo administrador. ON CONFLICT (username) DO NOTHING evita erro se já existir.
        cur.execute(
            "INSERT INTO admin (username, password_hash) VALUES (%s, %s) ON CONFLICT (username) DO NOTHING;",
            (ADMIN_USERNAME, hashed_password)
        )
        
        # Confirma as alterações
        conn.commit()

        # Verifica se o usuário foi realmente inserido (ou já existia)
        cur.execute("SELECT * FROM admin WHERE username = %s;", (ADMIN_USERNAME,))
        admin_user = cur.fetchone()

        if admin_user:
            print(f"\n[SUCESSO] Usuário administrador '{ADMIN_USERNAME}' criado/verificado com sucesso no PostgreSQL!")
            print("Você pode tentar logar no painel agora.")
        else:
            print(f"\n[AVISO] Usuário '{ADMIN_USERNAME}' já existia ou ocorreu um problema na inserção (mas o ON CONFLICT deveria ter lidado com isso).")

    except psycopg2.Error as e:
        print(f"\n[ERRO DB PostgreSQL] Ocorreu um erro de banco de dados: {e.pgcode} - {e.pgerror}")
        if conn:
            conn.rollback() # Reverte a transação em caso de erro
    except Exception as e:
        print(f"\n[ERRO GERAL] Ocorreu um erro inesperado ao criar admin: {e}")
    finally:
        # Garante que a conexão com o banco de dados seja sempre fechada
        if cur: cur.close()
        if conn: conn.close()

if __name__ == '__main__':
    create_admin_user()