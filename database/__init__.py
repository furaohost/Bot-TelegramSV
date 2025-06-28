import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
# Importa a função de conexão centralizada da pasta database
from database import get_db_connection 
from werkzeug.security import generate_password_hash # Para o hash da senha do admin

# ------------------------------------------------------------------
# Função auxiliar para garantir que colunas existem (útil para migrações leves)
# ------------------------------------------------------------------
def ensure_column(cursor, table, col_def, db_type):
    """
    Verifica se uma coluna existe em uma tabela e a adiciona se não existir.
    Compatível com SQLite e PostgreSQL.
    Args:
        cursor: Objeto cursor do banco de dados.
        table (str): Nome da tabela.
        col_def (str): Definição da coluna (ex: "chat_id BIGINT").
        db_type (str): Tipo do banco de dados ("sqlite" ou "postgresql").
    """
    col_name = col_def.split()[0]
    try:
        if db_type == "sqlite":
            cursor.execute(f"PRAGMA table_info({table})")
            existing_columns = [row[1] for row in cursor.fetchall()]
        elif db_type == "postgresql":
            cursor.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s AND column_name = %s;
                """,
                (table, col_name)
            )
            existing_columns = [row['column_name'] for row in cursor.fetchall()]
        else:
            print(f"AVISO: Tipo de banco de dados '{db_type}' não suportado para ensure_column.")
            return

        if col_name not in existing_columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
            print(f"Adicionada coluna '{col_name}' à tabela '{table}'.")
        else:
            print(f"Coluna '{col_name}' já existe na tabela '{table}'.")

    except Exception as e:
        print(f"Erro ao verificar/adicionar coluna '{col_name}' em '{table}': {e}")


# ------------------------------------------------------------------
# Função principal de inicialização do DB
# ------------------------------------------------------------------
def init_db():
    """
    Inicializa o esquema do banco de dados (cria tabelas se não existirem)
    e insere dados padrão (ex: usuário admin, mensagens de boas-vindas).
    Compatível com SQLite e PostgreSQL, adaptando as sintaxes SQL.
    """
    conn = None
    try:
        conn = get_db_connection() # Obtém a conexão usando a função centralizada
        if conn is None:
            print("ERRO: Não foi possível obter uma conexão com o banco de dados para inicialização.")
            return

        # Detecta o tipo de banco de dados para comandos específicos SQL
        db_type = "postgresql" if isinstance(conn, psycopg2.extensions.connection) else "sqlite"
        print(f"Inicializando banco de dados ({db_type})...")

        with conn.cursor() as cur:
            # ------------------------------------------------------------------
            # USERS
            # ------------------------------------------------------------------
            if db_type == "sqlite":
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        data_registro TEXT DEFAULT (datetime('now')),
                        is_active BOOLEAN DEFAULT 1
                    );
                """)
            else: # PostgreSQL
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id BIGINT PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE
                    );
                """)
            
            # ------------------------------------------------------------------
            # PRODUTOS
            # ------------------------------------------------------------------
            if db_type == "sqlite":
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS produtos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT NOT NULL,
                        preco REAL NOT NULL,
                        link TEXT NOT NULL
                    );
                """)
            else: # PostgreSQL
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS produtos (
                        id SERIAL PRIMARY KEY,
                        nome TEXT NOT NULL,
                        preco NUMERIC(10,2) NOT NULL,
                        link TEXT NOT NULL
                    );
                """)

            # ------------------------------------------------------------------
            # VENDAS
            # ------------------------------------------------------------------
            if db_type == "sqlite":
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS vendas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        produto_id INTEGER,
                        preco REAL,
                        status TEXT,
                        data_venda TEXT DEFAULT (datetime('now')),
                        payment_id TEXT,
                        payer_name TEXT,
                        payer_email TEXT,
                        FOREIGN KEY (user_id) REFERENCES users (id),
                        FOREIGN KEY (produto_id) REFERENCES produtos (id)
                    );
                """)
            else: # PostgreSQL
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS vendas (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        produto_id INTEGER,
                        preco NUMERIC(10,2),
                        status TEXT,
                        data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        payment_id TEXT,
                        payer_name TEXT,
                        payer_email TEXT,
                        FOREIGN KEY (user_id) REFERENCES users(id),
                        FOREIGN KEY (produto_id) REFERENCES produtos(id)
                    );
                """)

            # ------------------------------------------------------------------
            # ADMIN
            # ------------------------------------------------------------------
            if db_type == "sqlite":
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS admin (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL
                    );
                """)
            else: # PostgreSQL
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS admin (
                        id SERIAL PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL
                    );
                """)

            # ------------------------------------------------------------------
            # CONFIG
            # ------------------------------------------------------------------
            if db_type == "sqlite":
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS config (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    );
                """)
            else: # PostgreSQL
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS config (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    );
                """)

            # ------------------------------------------------------------------
            # COMUNIDADES (Sprint 1)
            # ------------------------------------------------------------------
            if db_type == "sqlite":
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS comunidades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT NOT NULL,
                        descricao TEXT,
                        chat_id INTEGER,
                        status TEXT DEFAULT 'ativa',
                        created_at TEXT DEFAULT (datetime('now'))
                    );
                """)
            else: # PostgreSQL
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS comunidades (
                        id SERIAL PRIMARY KEY,
                        nome TEXT NOT NULL,
                        descricao TEXT,
                        chat_id BIGINT,
                        status TEXT DEFAULT 'ativa',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)

            # ------------------------------------------------------------------
            # SCHEDULED_MESSAGES
            # ------------------------------------------------------------------
            if db_type == "sqlite":
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS scheduled_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_text TEXT NOT NULL,
                        target_chat_id INTEGER,
                        image_url TEXT,
                        schedule_time TEXT NOT NULL,
                        status TEXT DEFAULT 'pending',
                        created_at TEXT DEFAULT (datetime('now')),
                        sent_at TEXT
                    );
                """)
            else: # PostgreSQL
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS scheduled_messages (
                        id SERIAL PRIMARY KEY,
                        message_text TEXT NOT NULL,
                        target_chat_id BIGINT,
                        image_url TEXT,
                        schedule_time TIMESTAMP WITH TIME ZONE NOT NULL,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        sent_at TIMESTAMP
                    );
                """)

            # ---- Garante colunas novas caso você já tenha um DB antigo (aplica apenas a SQLite/PostgreSQL)
            # A função ensure_column foi melhorada para ser mais robusta.
            # Se em algum momento você acrescentar colunas depois, basta listar abaixo:
            for definition in [
                "descricao TEXT",
                "chat_id BIGINT", # Usar BIGINT para chat_id para compatibilidade com Telegram
                "status TEXT DEFAULT 'ativa'",
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            ]:
                # Para PostgreSQL, certifique-se de que o tipo BIGINT é compatível se a coluna já existia como INTEGER
                # Ou ajuste a definição da coluna para o tipo correto para migração.
                ensure_column(cur, "comunidades", definition, db_type)

            # ------------------------------------------------------------------
            # ADMIN padrão (usando generate_password_hash do Flask-Security)
            # ------------------------------------------------------------------
            
            if db_type == "sqlite":
                cur.execute("SELECT id FROM admin WHERE username = 'admin'")
                if not cur.fetchone():
                    cur.execute(
                        "INSERT INTO admin (username, password_hash) VALUES (?, ?)",
                        ("admin", generate_password_hash("admin123")),
                    )
            else: # PostgreSQL
                cur.execute("SELECT id FROM admin WHERE username = 'admin'")
                if not cur.fetchone():
                    cur.execute(
                        "INSERT INTO admin (username, password_hash) VALUES (%s, %s)",
                        ("admin", generate_password_hash("admin123")),
                    )

            # Mensagens padrão
            if db_type == "sqlite":
                cur.execute(
                    "INSERT INTO config (key, value) VALUES ('welcome_message_bot',?) ON CONFLICT (key) DO NOTHING;",
                    ("Olá, {first_name}! Bem-vindo(a) ao bot!",),
                )
                cur.execute(
                    "INSERT INTO config (key, value) VALUES ('welcome_message_community',?) ON CONFLICT (key) DO NOTHING;",
                    ("Bem-vindo(a) à nossa comunidade, {first_name}!",),
                )
            else: # PostgreSQL
                cur.execute(
                    "INSERT INTO config (key, value) VALUES ('welcome_message_bot',%s) ON CONFLICT (key) DO NOTHING;",
                    ("Olá, {first_name}! Bem-vindo(a) ao bot!",),
                )
                cur.execute(
                    "INSERT INTO config (key, value) VALUES ('welcome_message_community',%s) ON CONFLICT (key) DO NOTHING;",
                    ("Bem-vindo(a) à nossa comunidade, {first_name}!",),
                )

            conn.commit()
            print("DEBUG DB INIT: Tabelas e dados padrão OK.")

    except Exception as e:
        print(f"ERRO DB INIT: {e}")
        # import traceback; traceback.print_exc() # Descomente para ver o stack trace completo
        if conn:
            conn.rollback() # Reverte as mudanças em caso de erro
        raise # Re-levanta a exceção
    finally:
        if conn:
            conn.close()
            print("Conexão com o banco de dados fechada após inicialização.")

if __name__ == '__main__':
    # Este bloco será executado apenas quando você rodar 'python database/db_init.py'
    init_db()
