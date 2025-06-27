# bot/handlers/comunidades.py
from telebot import TeleBot
from telebot.types import Message


def register_comunidades_handlers(bot: TeleBot, get_db_connection):
    """
    /criar_comunidade  <nome> [descrição]
    /nova_comunidade   <nome> [descrição]   (alias)
    /listar_comunidades
    /editar_comunidade <id> <novo_nome> [nova descrição]
    """

    # 1 ────────────────────────────────────────────────────────────────
    @bot.message_handler(commands=['criar_comunidade', 'nova_comunidade'])
    def criar(msg: Message):
        args = msg.text.split(maxsplit=2)
        if len(args) < 2:
            bot.reply_to(msg,
                         "Uso: /criar_comunidade <nome> [descrição opcional]")
            return
        nome, desc = args[1], (args[2] if len(args) > 2 else "")
        chat_id = msg.chat.id

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO comunidades (nome, descricao, chat_id) VALUES (?,?,?)",
            (nome, desc, chat_id)
        )
        comunidade_id = cur.lastrowid
        conn.commit()

        bot.reply_to(msg,
                     f"🔔 Comunidade *{nome}* criada!\nID `{comunidade_id}`",
                     parse_mode="Markdown")

    # 2 ────────────────────────────────────────────────────────────────
    @bot.message_handler(commands=['listar_comunidades'])
    def listar(msg: Message):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, nome, status FROM comunidades ORDER BY id")
        rows = cur.fetchall()

        if not rows:
            bot.reply_to(msg, "Nenhuma comunidade cadastrada.")
            return

        linhas = "\n".join(f"• {r[0]} — *{r[1]}* _({r[2]})_" for r in rows)
        bot.reply_to(msg,
                     "*Comunidades cadastradas:*\n" + linhas,
                     parse_mode="Markdown")

    # 3 ────────────────────────────────────────────────────────────────
    @bot.message_handler(commands=['editar_comunidade'])
    def editar(msg: Message):
        args = msg.text.split(maxsplit=3)
        if len(args) < 3:
            bot.reply_to(
                msg,
                "Uso: /editar_comunidade <id> <novo_nome> "
                "[nova descrição opcional]"
            )
            return

        cid, novo_nome = args[1], args[2]
        nova_desc = args[3] if len(args) > 3 else ""

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE comunidades SET nome=?, descricao=?, status='active' "
            "WHERE id=?",
            (novo_nome, nova_desc, cid)
        )
        conn.commit()

        if cur.rowcount == 0:
            bot.reply_to(msg, "❌ Comunidade não encontrada.")
        else:
            bot.reply_to(
                msg,
                f"✅ Comunidade `{cid}` renomeada para *{novo_nome}*.",
                parse_mode="Markdown")


