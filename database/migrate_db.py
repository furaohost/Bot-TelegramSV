import sqlite3

# --- CONFIGURAÇÃO ---
# Nomes dos arquivos de banco de dados SQLite para a migração.
# O OLD_DB_NAME é o banco de dados com a estrutura antiga (ou de backup).
# O NEW_DB_NAME é o banco de dados com a estrutura nova (ou recém-criada por db_init.py).
OLD_DB_NAME = 'dashboard_old.db' # Ex: seu DB antes das alterações de esquema
NEW_DB_NAME = 'dashboard.db'     # Ex: seu DB com o esquema atualizado

def migrate_data():
    """
    Este script copia os dados de um banco de dados SQLite antigo para um novo
    que possui uma estrutura de tabelas atualizada.
    É útil para migrar dados de desenvolvimento local entre versões do esquema DB.
    
    ATENÇÃO: Use com cautela! Faça um backup dos seus bancos de dados antes de executar.
    """
    old_conn = None
    new_conn = None
    try:
        # Conecta ao banco de dados antigo
        old_conn = sqlite3.connect(OLD_DB_NAME)
        # Permite acessar colunas por nome no DB antigo (ex: row['id'])
        old_conn.row_factory = sqlite3.Row 

        # Conecta ao novo banco de dados. Este DB deve ter sido inicializado
        # com a nova estrutura via db_init.py antes de rodar a migração.
        new_conn = sqlite3.connect(NEW_DB_NAME)
        
        old_cursor = old_conn.cursor()
        new_cursor = new_conn.cursor()

        print(f"Iniciando a migração de '{OLD_DB_NAME}' para '{NEW_DB_NAME}'...")

        # --- Tabelas a serem migradas generlamente ---
        # Lista as tabelas que podem ser copiadas diretamente (desde que as colunas existam)
        tables_to_migrate = ['users', 'produtos', 'admin', 'config', 'comunidades', 'scheduled_messages'] 
        # Adicione 'comunidades' e 'scheduled_messages' aqui se quiser migrar seus dados também.
        # Certifique-se de que os esquemas da nova tabela são compatíveis.

        for table in tables_to_migrate:
            print(f"Migrando dados da tabela '{table}'...")
            try:
                old_cursor.execute(f"SELECT * FROM {table}")
                rows = old_cursor.fetchall()
                
                if rows:
                    # Pega os nomes das colunas da tabela antiga para garantir a ordem correta na inserção
                    columns = [description[0] for description in old_cursor.description]
                    # Cria placeholders para a query INSERT
                    placeholders = ', '.join(['?'] * len(columns))
                    
                    # Converte as linhas (do tipo Row) em tuplas para serem usadas com executemany
                    data_tuples = [tuple(row) for row in rows]

                    # Insere os dados na nova tabela
                    new_cursor.executemany(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})", data_tuples)
                    print(f"{len(rows)} registros inseridos em '{table}'.")
                else:
                    print(f"Nenhum registro encontrado em '{table}'.")
            except sqlite3.OperationalError as e:
                print(f"[AVISO] Tabela '{table}' não encontrada no DB antigo ou erro de esquema: {e}. Pulando migração desta tabela.")
            except Exception as e:
                print(f"[ERRO] Falha ao migrar tabela '{table}': {e}")
                # import traceback; traceback.exc_info() # Descomente para ver o stack trace

        # --- Migração especial para a tabela 'vendas' ---
        # Esta é uma migração mais complexa porque 'vendas' pode ter uma coluna 'preco' nova
        # que precisa ser preenchida com base nos produtos.
        print("Migrando dados da tabela 'vendas'...")
        try:
            # Esta query busca os dados da venda antiga e FAZ UM JOIN com a tabela de produtos
            # para obter o preço que o produto tinha (aproximadamente) na época da venda.
            # Assume que a nova tabela 'vendas' tem a coluna 'preco'.
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
                # A ordem das colunas e dos placeholders é crucial.
                new_cursor.executemany(
                    "INSERT INTO vendas (id, user_id, produto_id, preco, payment_id, status, data_venda, payer_name, payer_email) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    data_tuples
                )
                print(f"{len(vendas_data)} registros inseridos em 'vendas'.")
            else:
                print("Nenhum registro encontrado em 'vendas'.")

        except sqlite3.OperationalError as e:
            print(f"\n[AVISO] Não foi possível migrar a tabela 'vendas'. Erro: {e}. Verifique o esquema da tabela 'vendas' no novo DB.")
        except Exception as e:
            print(f"[ERRO] Falha crítica na migração da tabela 'vendas': {e}")
            # import traceback; traceback.exc_info()

        # Salva (commita) as alterações no novo banco de dados
        new_conn.commit()
        print("\nMigração de dados concluída com sucesso!")

    except sqlite3.Error as e:
        print(f"\nOcorreu um erro geral durante a migração: {e}")
        # import traceback; traceback.print_exc()
    finally:
        # Garante que as conexões sejam sempre fechadas, mesmo em caso de erro
        if old_conn:
            old_conn.close()
        if new_conn:
            new_conn.close()
        print("Conexões com os bancos de dados foram fechadas.")

if __name__ == '__main__':
    # Este bloco é executado apenas quando o script é rodado diretamente.
    migrate_data()