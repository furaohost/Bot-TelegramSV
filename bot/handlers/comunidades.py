# bot/handlers/comunidades.py
from telebot.types import Message
from datetime import datetime

def register_comunidades_handlers(bot, get_db_connection):

    @bot.message_handler(commands=['criar_comunidade'])
    def criar_comunidade(msg: Message):
        parts = msg.text.split(maxsplit=2)
        if len(parts) < 2:
            bot.reply_to(msg, "Uso: /criar_comunidade <nome> [descricao]")
            return
        nome = parts[1]
        descricao = parts[2] if len(parts) > 2 else ''
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO comunidades (nome, descricao) "
                "VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (nome, descricao)
            )
            conn.commit()
        bot.reply_to(msg, f"Comunidade *{nome}* criada ✅", parse_mode='Markdown')

    @bot.message_handler(commands=['listar_comunidades'])
    def listar_comunidades(msg: Message):
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id, nome FROM comunidades ORDER BY id")
            rows = cur.fetchall()
        txt = ("Nenhuma comunidade." if not rows
               else "Comunidades:\n" + "\n".join(f"{r[0]} — {r[1]}" for r in rows))
        bot.reply_to(msg, txt)
