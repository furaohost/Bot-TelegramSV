import os
import psycopg2
from werkzeug.security import generate_password_hash # Para criptografar a senha
from psycopg2.extras import RealDictCursor

# IMPORTANTE: Use a mesma DATABASE_URL que está no seu Render para o bot
DATABASE_URL = os.getenv('DATABASE_URL') 

# Se você for rodar localmente para testar, pode precisar da .env
from dotenv import load_dotenv
load_dotenv()
if not DATABASE_URL:
    DATABASE_URL = os.getenv('DATABASE_URL') # Tenta carregar do .env local
    if not DATABASE_URL:
        print("ERRO: DATABASE_URL não definida. Defina no ambiente ou no .env")
        exit(1)

# --- Credenciais do NOVO ADMINISTRADOR ---
USERNAME = "admin" # <<<<< TROQUE AQUI PELO USERNAME DESEJADO
PASSWORD = "admin123"     # <<<<< TROQUE AQUI PELA SENHA DESEJADA
# ----------------------------------------

def create_admin():
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode='require')
        cur = conn.cursor()

        # Criptografa a senha
        password_hash = generate_password_hash(PASSWORD)

        # Insere o usuário admin na tabela 'admin'
        cur.execute("INSERT INTO admin (username, password_hash) VALUES (%s, %s) ON CONFLICT (username) DO NOTHING;",
                    (USERNAME, password_hash))
        conn.commit()

        # Verifica se o usuário foi realmente inserido
        cur.execute("SELECT * FROM admin WHERE username = %s;", (USERNAME,))
        admin_user = cur.fetchone()

        if admin_user:
            print(f"Usuário administrador '{USERNAME}' criado/verificado com sucesso!")
        else:
            print(f"Aviso: Usuário '{USERNAME}' já existia ou ocorreu um problema na inserção.")

    except Exception as e:
        print(f"ERRO: Falha ao criar usuário administrador: {e}")
        if conn:
            conn.rollback()
    finally:
        if cur: cur.close()
        if conn: conn.close()

if __name__ == '__main__':
    create_admin()