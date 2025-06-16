import sqlite3
import getpass
from werkzeug.security import generate_password_hash

# --- CONFIGURAÇÃO ---
DB_NAME = 'dashboard.db'

def create_admin_user():
    """
    Script para criar um usuário administrador no banco de dados.
    Este script deve ser executado apenas uma vez ou sempre que
    precisar adicionar um novo administrador.
    """
    print("--- Criação de Usuário Administrador ---")
    
    # Coleta as informações do usuário de forma segura
    username = input("Digite o nome de usuário para o admin: ")
    password = getpass.getpass("Digite a senha para o admin: ")
    password_confirm = getpass.getpass("Confirme a senha: ")

    # Validação simples
    if not username or not password:
        print("\n[ERRO] Nome de usuário e senha não podem ser vazios.")
        return

    if password != password_confirm:
        print("\n[ERRO] As senhas não coincidem. Tente novamente.")
        return

    try:
        # Gera um hash seguro da senha. NUNCA armazene a senha em texto plano.
        # O método 'pbkdf2:sha256' é um padrão forte e recomendado.
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        # Conecta ao banco de dados
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Insere o novo administrador usando parâmetros de consulta para evitar SQL Injection
        cursor.execute(
            "INSERT INTO admin (username, password_hash) VALUES (?, ?)",
            (username, hashed_password)
        )
        
        # Salva as alterações
        conn.commit()
        print(f"\n[SUCESSO] Usuário '{username}' criado com sucesso!")

    except sqlite3.IntegrityError:
        # Este erro ocorre se o username já existir (devido à restrição UNIQUE)
        print(f"\n[ERRO] O nome de usuário '{username}' já existe. Tente outro.")
    except Exception as e:
        print(f"\nOcorreu um erro inesperado: {e}")
    finally:
        # Garante que a conexão com o banco de dados seja sempre fechada
        if conn:
            conn.close()

if __name__ == '__main__':
    create_admin_user()
