# bot/handlers/conteudos.py
from telebot.types import Message
from datetime import datetime

# Uploader em duas etapas — guardamos estado no dict abaixo
_pending_upload = {}   # user_id -> (comunidade_id, tipo, titulo)

def register_conteudos_handlers(bot, get_db_connection):

    @bot.message_handler(commands=['novo_conteudo'])
    def novo_conteudo(msg: Message):
        parts = msg.text.split(maxsplit=4)
        if len(parts) < 4:
            bot.reply_to(msg, "Uso: /novo_conteudo <comunidade_id> <text/photo/video> <titulo>")
            return
        comunidade_id = int(parts[1]); tipo = parts[2]; titulo = parts[3]
        if tipo not in ('text', 'photo', 'video'):
            bot.reply_to(msg, "Tipo deve ser text/photo/video")
            return

        if tipo == 'text':
            _salvar_conteudo(get_db_connection(), comunidade_id, tipo, None, titulo)
            bot.reply_to(msg, "Conteúdo de texto salvo ✅")
        else:
            _pending_upload[msg.from_user.id] = (comunidade_id, tipo, titulo)
            bot.reply_to(msg, "Envie o arquivo agora…")

    @bot.message_handler(content_types=['photo', 'video'])
    def receber_midia(msg: Message):
        state = _pending_upload.pop(msg.from_user.id, None)
        if not state:
            return  # usuário não está enviando media
        comunidade_id, tipo, titulo = state
        file_id = (msg.photo[-1].file_id if tipo == 'photo' else msg.video.file_id)
        _salvar_conteudo(get_db_connection(), comunidade_id, tipo, file_id, titulo)
        bot.reply_to(msg, "Conteúdo salvo ✅")

    @bot.message_handler(commands=['listar_conteudos'])
    def listar_conteudos(msg: Message):
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id, titulo FROM conteudos ORDER BY criado_em DESC LIMIT 20")
            rows = cur.fetchall()
        txt = ("Sem conteúdos." if not rows
               else "Conteúdos:\n" + "\n".join(f"{r[0]} — {r[1]}" for r in rows))
        bot.reply_to(msg, txt)

def _salvar_conteudo(conn, comunidade_id, tipo, file_id, titulo):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO conteudos (titulo, arquivo_id, tipo, comunidade_id, criado_em) "
            "VALUES (%s,%s,%s,%s,%s)",
            (titulo, file_id, tipo, comunidade_id, datetime.utcnow())
        )
        conn.commit()
