# db_init.py
import sqlite3

DB_NAME = "dashboard.db"
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# ------------------------------------------------------------------
# USERS
# ------------------------------------------------------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username     TEXT,
    first_name   TEXT,
    last_name    TEXT,
    data_registro TEXT
)
""")

# ------------------------------------------------------------------
# PRODUTOS
# ------------------------------------------------------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS produtos (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nome   TEXT NOT NULL,
    preco  REAL NOT NULL,
    link   TEXT NOT NULL
)
""")

# ------------------------------------------------------------------
# VENDAS  (mantida sua atualização com 'preco')
# ------------------------------------------------------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS vendas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    produto_id  INTEGER,
    preco       REAL,           -- valor no momento da venda
    payment_id  TEXT,
    status      TEXT,
    data_venda  TEXT,
    payer_name  TEXT,
    payer_email TEXT,
    FOREIGN KEY (user_id)    REFERENCES users (id),
    FOREIGN KEY (produto_id) REFERENCES produtos (id)
)
""")

# ------------------------------------------------------------------
# >>> NOVA TABELA: COMUNIDADES  (Sprint 1)
# ------------------------------------------------------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS comunidades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT    NOT NULL,
    chat_id     INTEGER,
    descricao   TEXT,
    status      TEXT    DEFAULT 'active',
    created_at  TEXT    DEFAULT (datetime('now'))
)
""")

# ---- garante colunas novas caso você já tenha um arquivo .db antigo
def ensure_column(table, col_def):
    col_name = col_def.split()[0]
    cursor.execute(
        "PRAGMA table_info(%s)" % table
    )
    if col_name not in [row[1] for row in cursor.fetchall()]:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")

# Se em algum momento você acrescentar colunas depois,
# basta listar abaixo:
for definition in [
    "chat_id INTEGER",
    "descricao TEXT",
    "status TEXT DEFAULT 'active'",
    "created_at TEXT DEFAULT (datetime('now'))",
]:
    ensure_column("comunidades", definition)

# ------------------------------------------------------------------
# ADMIN
# ------------------------------------------------------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS admin (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
)
""")

conn.commit()
conn.close()
print(f"Banco de dados '{DB_NAME}' inicializado com sucesso!")
