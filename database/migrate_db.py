import sqlite3

OLD_DB_NAME = 'dashboard_old.db'
NEW_DB_NAME = 'dashboard.db'

def migrate_data():
    """
    Este script copia os dados de um banco de dados SQLite antigo para um novo
    que possui uma estrutura de tabelas atualizada.
    """
    try:
        old_conn = sqlite3.connect(OLD_DB_NAME)
        old_conn.row_factory = sqlite3.Row # Permite acessar colunas por nome
        new_conn = sqlite3.connect(NEW_DB_NAME)
        
        old_cursor = old_conn.cursor()
        new_cursor = new_conn.cursor()

        print(f"Iniciando a migração de '{OLD_DB_NAME}' para '{NEW_DB_NAME}'...")

        # --- Tabelas a serem migradas ---
        tables_to_migrate = ['users', 'produtos', 'admin']

        for table in tables_to_migrate:
            print(f"Migrando dados da tabela '{table}'...")
            old_cursor.execute(f"SELECT * FROM {table}")
            rows = old_cursor.fetchall()
            
            if rows:
                # Pega os nomes das colunas para garantir a ordem correta
                columns = [description[0] for description in old_cursor.description]
                placeholders = ', '.join(['?'] * len(columns))
                
                # Converte as linhas (que são do tipo Row) em tuplas
                data_tuples = [tuple(row) for row in rows]

                new_cursor.executemany(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})", data_tuples)
                print(f"{len(rows)} registros inseridos em '{table}'.")
            else:
                print(f"Nenhum registro encontrado em '{table}'.")

        # --- Migração especial para a tabela 'vendas' ---
        print("Migrando dados da tabela 'vendas'...")
        try:
            # Esta query busca os dados da venda antiga e FAZ UM JOIN com a tabela de produtos
            # para obter o preço que o produto tinha (aproximadamente) na época.
            old_cursor.execute('''
                SELECT v.id, v.user_id, v.produto_id, p.preco, v.payment_id, v.status, v.data_venda, v.payer_name, v.payer_email
                FROM vendas v
                LEFT JOIN produtos p ON v.produto_id = p.id
            ''')
            vendas_data = old_cursor.fetchall()

            if vendas_data:
                # Converte as linhas em tuplas
                data_tuples = [tuple(row) for row in vendas_data]
                
                # Insere os dados nas colunas correspondentes da nova tabela, incluindo o preço.
                new_cursor.executemany(
                    "INSERT INTO vendas (id, user_id, produto_id, preco, payment_id, status, data_venda, payer_name, payer_email) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    data_tuples
                )
                print(f"{len(vendas_data)} registros inseridos em 'vendas'.")
            else:
                print("Nenhum registro encontrado em 'vendas'.")

        except sqlite3.OperationalError as e:
            print(f"\n[AVISO] Não foi possível migrar a tabela 'vendas'. Erro: {e}")

        # Salva (commita) as alterações no novo banco de dados
        new_conn.commit()
        print("\nMigração de dados concluída com sucesso!")

    except sqlite3.Error as e:
        print(f"\nOcorreu um erro durante a migração: {e}")
    finally:
        # Garante que as conexões sejam sempre fechadas
        if 'old_conn' in locals() and old_conn:
            old_conn.close()
        if 'new_conn' in locals() and new_conn:
            new_conn.close()
        print("Conexões com os bancos de dados foram fechadas.")

if __name__ == '__main__':
    migrate_data()
