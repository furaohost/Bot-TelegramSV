import os
import psycopg2
from werkzeug.security import generate_password_hash # Para criptografar a senha
from psycopg2.extras import RealDictCursor # Para acessar resultados por nome da coluna

# Importa dotenv para carregar variáveis de ambiente de um arquivo .env,
# útil para rodar este script localmente em desenvolvimento.
from dotenv import load_dotenv
load_dotenv() # Carrega as variáveis do .env

# IMPORTANTE: Use a mesma DATABASE_URL que está no seu ambiente de deploy (ex: Render)
# ou no seu arquivo .env local.
DATABASE_URL = os.getenv('DATABASE_URL') 

# Verifica se a DATABASE_URL foi definida
if not DATABASE_URL:
    print("ERRO: DATABASE_URL não definida. Defina no ambiente ou no .env para conectar ao PostgreSQL.")
    exit(1) # Sai do script se a URL do DB não estiver configurada

# --- Credenciais do NOVO ADMINISTRADOR ---
# !!! ATENÇÃO !!!
# TROQUE AQUI PELO USERNAME E SENHA DESEJADOS ANTES DE EXECUTAR EM PRODUÇÃO!
USERNAME = "admin" # <<<<< TROQUE AQUI PELO USERNAME DESEJADO
PASSWORD = "admin123"     # <<<<< TROQUE AQUI PELA SENHA DESEJADA
# ----------------------------------------

def create_admin():
    """
    Script para criar ou verificar a existência de um usuário administrador padrão
    no banco de dados PostgreSQL.
    Este script pode ser executado uma vez no deploy para garantir que o admin exista.
    """
    conn = None
    cur = None
    try:
        # Conecta ao banco de dados PostgreSQL
        # cursor_factory=RealDictCursor permite acessar colunas como dicionário (ex: row['username'])
        # sslmode='require' é importante para segurança em ambientes de produção.
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, sslmode='require')
        cur = conn.cursor()

        # Criptografa a senha usando werkzeug.security
        password_hash = generate_password_hash(PASSWORD)

        # Insere o usuário admin na tabela 'admin'.
        # 'ON CONFLICT (username) DO NOTHING;' evita erro se o usuário já existir.
        cur.execute("INSERT INTO admin (username, password_hash) VALUES (%s, %s) ON CONFLICT (username) DO NOTHING;",
                    (USERNAME, password_hash))
        conn.commit() # Confirma a transação

        # Verifica se o usuário foi realmente inserido ou já existia
        cur.execute("SELECT * FROM admin WHERE username = %s;", (USERNAME,))
        admin_user = cur.fetchone()

        if admin_user:
            print(f"Usuário administrador '{USERNAME}' criado/verificado com sucesso!")
        else:
            # Esta mensagem pode aparecer se o usuário já existia e 'DO NOTHING' foi ativado.
            print(f"Aviso: Usuário '{USERNAME}' já existia ou ocorreu um problema na inserção.")

    except Exception as e:
        print(f"ERRO: Falha ao criar usuário administrador: {e}")
        # import traceback; traceback.exc_info() # Descomente para ver o stack trace completo
        if conn:
            conn.rollback() # Reverte a transação em caso de erro
    finally:
        # Garante que o cursor e a conexão sejam sempre fechados
        if cur: cur.close()
        if conn: conn.close()

if __name__ == '__main__':
    # Este bloco é executado apenas quando o script é rodado diretamente.
    create_admin()
