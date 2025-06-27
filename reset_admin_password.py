import os
import psycopg2
import getpass
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

# Carrega variáveis de ambiente de um arquivo .env (se existir)
# Isso é útil para rodar localmente, mas no Render as variáveis já estarão no ambiente.
load_dotenv()

# Pega a URL do banco de dados das variáveis de ambiente
DATABASE_URL = os.getenv('DATABASE_URL')

def reset_password():
    """
    Script para resetar a senha de um usuário administrador existente no banco de dados.
    """
    if not DATABASE_URL:
        print("ERRO: A variável de ambiente DATABASE_URL não foi encontrada.")
        return

    print("--- Reset de Senha de Administrador ---")
    
    username_to_reset = input("Digite o nome do usuário admin que deseja resetar a senha (ex: admin): ")
    new_password = getpass.getpass("Digite a NOVA senha: ")
    new_password_confirm = getpass.getpass("Confirme a NOVA senha: ")

    if not username_to_reset or not new_password:
        print("\n[ERRO] Nome de usuário e senha não podem ser vazios.")
        return

    if new_password != new_password_confirm:
        print("\n[ERRO] As senhas não coincidem. Tente novamente.")
        return

    conn = None
    try:
        # Gera o hash seguro da nova senha
        hashed_password = generate_password_hash(new_password)

        # Conecta ao banco de dados PostgreSQL
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        cur = conn.cursor()

        # Primeiro, verifica se o usuário existe
        cur.execute("SELECT id FROM admin WHERE username = %s", (username_to_reset,))
        user_exists = cur.fetchone()

        if not user_exists:
            print(f"\n[ERRO] O usuário '{username_to_reset}' não foi encontrado no banco de dados.")
            return

        # Se o usuário existe, atualiza a senha
        cur.execute(
            "UPDATE admin SET password_hash = %s WHERE username = %s",
            (hashed_password, username_to_reset)
        )
        
        # Verifica se alguma linha foi de fato atualizada
        if cur.rowcount == 0:
            print(f"\n[AVISO] Nenhuma linha foi atualizada. O usuário '{username_to_reset}' existe, mas a senha não foi alterada.")
        else:
            conn.commit()
            print(f"\n[SUCESSO] A senha do usuário '{username_to_reset}' foi atualizada com sucesso!")

    except psycopg2.Error as e:
        print(f"\nOcorreu um erro de banco de dados: {e}")
        if conn:
            conn.rollback()
    except Exception as e:
        print(f"\nOcorreu um erro inesperado: {e}")
    finally:
        # Garante que a conexão com o banco de dados seja sempre fechada
        if conn:
            cur.close()
            conn.close()
            print("\nConexão com o banco de dados fechada.")

if __name__ == '__main__':
    reset_password()
