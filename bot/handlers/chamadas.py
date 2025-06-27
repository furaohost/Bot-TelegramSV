# bot/handlers/chamadas.py
from telebot.types import Message
from datetime import datetime

def register_chamadas_handlers(bot, get_db_connection):

    @bot.message_handler(commands=['agendar_chamada'])
    def agendar_chamada(msg: Message):
        """
        /agendar_chamada <comunidade_id> <titulo> <link> <YYYY-MM-DD_HH:MM>
        """
        parts = msg.text.split(maxsplit=5)
        if len(parts) < 5:
            bot.reply_to(
                msg,
                "Uso: /agendar_chamada <comunidade_id> "
                "<titulo> <link> <YYYY-MM-DD_HH:MM>"
            )
            return

        comunidade_id = int(parts[1])
        titulo = parts[2]
        link = parts[3]
        horario_str = parts[4]
        try:
            horario = datetime.strptime(horario_str, "%Y-%m-%d_%H:%M")
        except ValueError:
            bot.reply_to(msg, "Formato de data/hora inválido.")
            return

        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chamadas_video "
                "(titulo, link, horario, comunidade_id) "
                "VALUES (%s,%s,%s,%s)",
                (titulo, link, horario, comunidade_id),
            )
            conn.commit()

        bot.reply_to(msg, "Chamada de vídeo agendada ✅")

    @bot.message_handler(commands=['listar_chamadas'])
    def listar_chamadas(msg: Message):
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, titulo, horario "
                "FROM chamadas_video "
                "ORDER BY horario DESC LIMIT 20"
            )
            rows = cur.fetchall()

        if not rows:
            bot.reply_to(msg, "Sem chamadas agendadas.")
            return

        txt = "Chamadas:\n" + "\n".join(
            f"{r[0]} — {r[1]} — {r[2].strftime('%d/%m %H:%M')}" for r in rows
        )
        bot.reply_to(msg, txt)
