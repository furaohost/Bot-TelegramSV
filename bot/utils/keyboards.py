from telebot import types
from typing import List, Tuple

def confirm_18_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(
            "Sou maior de 18 anos ✅", callback_data="confirm_18"
        )
    )
    return kb

def menu_principal() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("📅 Agendar",  callback_data="menu_agendar"),
        types.InlineKeyboardButton("🔞 Conteúdo", callback_data="menu_conteudo"),
    )
    kb.row(
        types.InlineKeyboardButton("🎁 Ofertas",   callback_data="menu_ofertas"),
        types.InlineKeyboardButton("👥 Comunidades", callback_data="menu_comunidades"),
    )
    return kb

def comunidades_keyboard(comunidades: List[Tuple[int, str]]):
    """
    Recebe uma lista [(id, nome), …] e gera botões para o usuário escolher
    uma comunidade.
    """
    kb = types.InlineKeyboardMarkup()
    for cid, nome in comunidades:
        kb.add(types.InlineKeyboardButton(nome, callback_data=f"sel_com_{cid}"))
    kb.add(types.InlineKeyboardButton("⬅️ Voltar", callback_data="menu_back"))
    return kb

