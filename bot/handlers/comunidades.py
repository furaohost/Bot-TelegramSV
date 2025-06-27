# -*- coding: utf-8 -*-
"""Comandos Telegram para Comunidades – Sprint 1."""

from telebot import TeleBot
from telebot.types import Message
from bot.services.comunidades import ComunidadeService


def register_comunidades_handlers(bot: TeleBot, get_db_connection):
    svc = ComunidadeService(get_db_connection)

    # /nova_comunidade <nome> [descrição]
    @bot.message_handler(commands=["nova_comunidade", "criar_comunidade"])
    def nova(msg: Message):
        parts = msg.text.split(maxsplit=2)
        if len(parts) < 2:
            bot.reply_to(
                msg,
                "Uso: `/nova_comunidade <nome> [descrição opcional]`",
                parse_mode="Markdown",
            )
            return

        cid = svc.criar(
            nome=parts[1], descricao=(parts[2] if len(parts) > 2 else ""), chat_id=msg.chat.id
        )
        bot.reply_to(msg, f"✅ Comunidade *{parts[1]}* criada! (id `{cid}`)", parse_mode="Markdown")

    # /listar_comunidades
    @bot.message_handler(commands=["listar_comunidades"])
    def listar(msg: Message):
        dados = svc.listar()
        if not dados:
            bot.reply_to(msg, "Nenhuma comunidade cadastrada.")
            return
        linhas = "\n".join(f"• {c['id']} — *{c['nome']}*" for c in dados)
        bot.reply_to(msg, "*Comunidades:*\n" + linhas, parse_mode="Markdown")

    # /editar_comunidade <id> <novo_nome> [nova descrição]
    @bot.message_handler(commands=["editar_comunidade"])
    def editar(msg: Message):
        parts = msg.text.split(maxsplit=3)
        if len(parts) < 3:
            bot.reply_to(
                msg,
                "Uso: `/editar_comunidade <id> <novo_nome> [nova descrição]`",
                parse_mode="Markdown",
            )
            return

        ok = svc.editar(
            cid=int(parts[1]),
            nome=parts[2],
            descricao=(parts[3] if len(parts) > 3 else ""),
        )
        if ok:
            bot.reply_to(msg, "✅ Comunidade atualizada com sucesso!")
        else:
            bot.reply_to(msg, "❌ Comunidade não encontrada.")


