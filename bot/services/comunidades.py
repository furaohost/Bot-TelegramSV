# -*- coding: utf-8 -*-
"""Camada de serviço para Comunidades (Sprint-1)."""

from typing import List, Dict


class ComunidadeService:
    """Recebe get_db_connection do app principal no construtor."""

    def __init__(self, get_db_connection):
        self.db = get_db_connection

    # ──────────────────── CRUD ────────────────────── #

    def criar(self, nome: str, descricao: str = "", chat_id: int | None = None) -> int:
        with self.db() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO comunidades (nome, descricao, chat_id)
                     VALUES (%s, %s, %s)
                  RETURNING id
                """,
                (nome, descricao, chat_id),
            )
            cid = cur.fetchone()[0]
            conn.commit()
            return cid

    def listar(self) -> List[Dict]:
        with self.db() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, nome, descricao, chat_id, status FROM comunidades ORDER BY id"
            )
            return cur.fetchall()

    def obter(self, cid: int) -> Dict | None:
        with self.db() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM comunidades WHERE id = %s", (cid,))
            return cur.fetchone()

    def editar(self, cid: int, nome: str, descricao: str = "") -> bool:
        with self.db() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE comunidades
                   SET nome = %s,
                       descricao = %s
                 WHERE id = %s
                """,
                (nome, descricao, cid),
            )
            conn.commit()
            return cur.rowcount == 1
