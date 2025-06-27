# bot/handlers/ofertas.py
from telebot.types import Message
from datetime import datetime

def register_ofertas_handlers(bot, get_db_connection):

    @bot.message_handler(commands=['criar_oferta'])
    def criar_oferta(msg: Message):
        parts = msg.text.split(maxsplit=4)
        if len(parts) < 4:
            bot.reply_to(msg, "Uso: /criar_oferta <comunidade_id> <titulo> <link> [descricao]")
            return
        comunidade_id = int(parts[1]); titulo = parts[2]; link = parts[3]
        descricao = parts[4] if len(parts) > 4 else ''
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ofertas (titulo, link, descricao, comunidade_id, data_inicio) "
                "VALUES (%s,%s,%s,%s,%s)",
                (titulo, link, descricao, comunidade_id, datetime.utcnow())
            )
            conn.commit()
        bot.reply_to(msg, "Oferta criada ✅")

    @bot.message_handler(commands=['listar_ofertas'])
    def listar_ofertas(msg: Message):
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id, titulo FROM ofertas ORDER BY id DESC LIMIT 20")
            rows = cur.fetchall()
        txt = ("Sem ofertas." if not rows
               else "Ofertas:\n" + "\n".join(f"{r[0]} — {r[1]}" for r in rows))
        bot.reply_to(msg, txt)
