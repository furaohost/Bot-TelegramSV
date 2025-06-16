import sqlite3

DB_NAME = 'dashboard.db'
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    data_registro TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    preco REAL NOT NULL,
    link TEXT NOT NULL
)
''')

# --- TABELA DE VENDAS ATUALIZADA ---
# Adicionamos a coluna 'preco' para guardar o valor no momento da venda.
print("Atualizando tabela 'vendas'...")
cursor.execute('''
CREATE TABLE IF NOT EXISTS vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    produto_id INTEGER,
    preco REAL, 
    payment_id TEXT,
    status TEXT,
    data_venda TEXT,
    payer_name TEXT,
    payer_email TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (produto_id) REFERENCES produtos (id)
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS admin (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
)
''')

conn.commit()
conn.close()
print(f"Banco de dados '{DB_NAME}' inicializado com sucesso!")
