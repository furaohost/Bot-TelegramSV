# bot/handlers/comunidades.py
from telebot.types import Message
from telebot import TeleBot
from datetime import datetime


def register_comunidades_handlers(bot: TeleBot, get_db_connection):
    """
    Registra os comandos:
        /nova_comunidade <nome> [descrição]
        /listar_comunidades
        /editar_comunidade <id> <novo_nome> [nova_descrição]
    """

    # ------------------------------------------------------------------
    # /nova_comunidade  (alias /criar_comunidade para retro-compatibilidade)
    # ------------------------------------------------------------------
    @bot.message_handler(commands=['nova_comunidade', 'criar_comunidade'])
    def nova_comunidade(msg: Message):
        parts = msg.text.split(maxsplit=2)
        if len(parts) < 2:
            bot.reply_to(
                msg,
                "Uso: /nova_comunidade <nome> [descrição opcional]",
            )
            return

        nome = parts[1]
        descricao = parts[2] if len(parts) > 2 else ""
        chat_id = msg.chat.id

        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO comunidades (nome, descricao, chat_id)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (nome, descricao, chat_id),
            )
            comunidade_id = cur.fetchone()[0]
            conn.commit()

        bot.reply_to(
            msg,
            f"🔔 Comunidade *{nome}* criada!\nID `{comunidade_id}`",
            parse_mode="Markdown",
        )

    # ------------------------------------------------------------------
    # /listar_comunidades
    # ------------------------------------------------------------------
    @bot.message_handler(commands=['listar_comunidades'])
    def listar_comunidades(msg: Message):
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nome, status FROM comunidades ORDER BY id"
            )
            rows = cur.fetchall()

        if not rows:
            bot.reply_to(msg, "Nenhuma comunidade cadastrada.")
            return

        linhas = "\n".join(
            f"• {row[0]} — *{row[1]}*  _({row[2]})_"
            for row in rows
        )
        bot.reply_to(
            msg,
            "*Comunidades cadastradas:*\n" + linhas,
            parse_mode="Markdown",
        )

    # ------------------------------------------------------------------
    # /editar_comunidade <id> <novo_nome> [nova_descrição]
    # ------------------------------------------------------------------
    @bot.message_handler(commands=['editar_comunidade'])
    def editar_comunidade(msg: Message):
        parts = msg.text.split(maxsplit=3)
        if len(parts) < 3:
            bot.reply_to(
                msg,
                "Uso: /editar_comunidade <id> <novo_nome> "
                "[nova descrição opcional]",
            )
            return

        comunidade_id = parts[1]
        novo_nome = parts[2]
        nova_desc = parts[3] if len(parts) > 3 else ""

        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE comunidades
                SET nome = %s,
                    descricao = %s,
                    status = 'active'
                WHERE id = %s
                """,
                (novo_nome, nova_desc, comunidade_id),
            )
            if cur.rowcount == 0:
                bot.reply_to(msg, "❌ Comunidade não encontrada.")
                return
            conn.commit()

        bot.reply_to(
            msg,
            f"✅ Comunidade `{comunidade_id}` agora se chama "
            f"*{novo_nome}*.",
            parse_mode="Markdown",
        )

