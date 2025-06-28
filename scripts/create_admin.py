import sqlite3
import getpass # Para coletar senhas de forma segura (não exibindo no terminal)
from werkzeug.security import generate_password_hash # Para gerar hash seguro da senha

# --- CONFIGURAÇÃO ---
# Nome do banco de dados SQLite que este script irá interagir.
# Certifique-se de que corresponda ao nome do seu DB SQLite local.
DB_NAME = 'dashboard.db' # Ou 'dashboard_local.db' se for o nome usado para o SQLite local

def create_admin_user():
    """
    Script interativo para criar um usuário administrador no banco de dados SQLite local.
    Este script é útil para configurar o primeiro admin para o painel web.
    Deve ser executado no terminal (`python scripts/create_admin.py`).
    """
    print("--- Criação de Usuário Administrador ---")
    
    # Coleta as informações do usuário de forma segura
    username = input("Digite o nome de usuário para o admin: ").strip()
    # getpass esconde a senha digitada no terminal
    password = getpass.getpass("Digite a senha para o admin: ").strip()
    password_confirm = getpass.getpass("Confirme a senha: ").strip()

    # Validação simples de entrada
    if not username:
        print("\n[ERRO] Nome de usuário não pode ser vazio.")
        return
    if not password:
        print("\n[ERRO] Senha não pode ser vazia.")
        return
    if password != password_confirm:
        print("\n[ERRO] As senhas não coincidem. Tente novamente.")
        return

    conn = None # Inicializa conn para garantir que esteja definido para o finally
    try:
        # Conecta ao banco de dados SQLite
        # Este script foca no SQLite, então conecta diretamente.
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Gera um hash seguro da senha. É crucial NUNCA armazenar a senha em texto plano.
        # 'pbkdf2:sha256' é um método forte e recomendado pelo Werkzeug.
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        # Insere o novo administrador.
        # Usa parâmetros de consulta (?) para evitar ataques de SQL Injection.
        cursor.execute(
            "INSERT INTO admin (username, password_hash) VALUES (?, ?)",
            (username, hashed_password)
        )
        
        # Salva (commita) as alterações no banco de dados
        conn.commit()
        print(f"\n[SUCESSO] Usuário '{username}' criado com sucesso!")

    except sqlite3.IntegrityError:
        # Este erro específico ocorre se o 'username' já existir
        # (devido à restrição UNIQUE na coluna username da tabela admin).
        print(f"\n[ERRO] O nome de usuário '{username}' já existe. Tente outro.")
    except Exception as e:
        # Captura outras exceções inesperadas
        print(f"\nOcorreu um erro inesperado: {e}")
        # import traceback; traceback.exc_info() # Descomente para ver o stack trace
    finally:
        # Garante que a conexão com o banco de dados seja sempre fechada
        if conn:
            conn.close()

if __name__ == '__main__':
    # Este bloco é executado apenas quando o script é rodado diretamente
    create_admin_user()

