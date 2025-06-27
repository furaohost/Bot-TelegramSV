import os
import mercadopago
import json
import traceback
import psycopg2                # <-- NOVO: requerido para upgrade VIP

# --- Variáveis Globais para o SDK ---
sdk = None
BASE_URL_FOR_MP_WEBHOOK = None


def init_mercadopago_sdk():
    """
    Inicializa o SDK do Mercado Pago e define BASE_URL global
    para o webhook. Chame no main (app.py) depois de carregar
    as variáveis de ambiente.
    """
    global sdk, BASE_URL_FOR_MP_WEBHOOK

    access_token = os.getenv("MERCADOPAGO_ACCESS_TOKEN")
    BASE_URL_FOR_MP_WEBHOOK = os.getenv("BASE_URL")

    if not access_token:
        raise ValueError("MERCADOPAGO_ACCESS_TOKEN não definido")

    if not BASE_URL_FOR_MP_WEBHOOK:
        raise ValueError("BASE_URL não definida (webhook Mercado Pago)")

    try:
        sdk = mercadopago.SDK(access_token)
        print("DEBUG MP: SDK inicializado.")
    except Exception as e:
        print(f"[ERRO FATAL MP] {e}")
        traceback.print_exc()
        raise


# ------------- CRIAÇÃO DO PAGAMENTO PIX -----------------
def criar_pagamento_pix(produto, user, venda_id):
    global sdk, BASE_URL_FOR_MP_WEBHOOK

    if sdk is None or BASE_URL_FOR_MP_WEBHOOK is None:
        init_mercadopago_sdk()

    notification_url = f"{BASE_URL_FOR_MP_WEBHOOK}/webhook/mercado-pago"

    payment_data = {
        "transaction_amount": float(produto["preco"]),
        "payment_method_id": "pix",
        "payer": {
            "email": f"user_{user.id}@email.com",
            "first_name": user.first_name or "Comprador",
            "last_name": user.last_name or "Bot",
            "identification": {"type": "OTHER", "number": str(user.id)},
        },
        "notification_url": notification_url,
        "external_reference": str(venda_id),
        "description": f"Venda de produto digital: {produto['nome']}",
        "statement_descriptor": "BOTVENDAS",
    }

    try:
        payment = sdk.payment().create(payment_data)["response"]
        return payment
    except Exception as e:
        print(f"[ERRO MP] Falha ao criar pagamento PIX: {e}")
        traceback.print_exc()
        return None


# ------------- VERIFICAÇÃO DE STATUS --------------------
def verificar_status_pagamento(payment_id):
    global sdk
    if sdk is None:
        init_mercadopago_sdk()
    try:
        payment_info = sdk.payment().get(payment_id)
        return payment_info["response"]
    except Exception as e:
        print(f"[ERRO MP] Falha ao verificar status: {e}")
        traceback.print_exc()
        return None


# ========================================================
# === WEBHOOK MERCADO PAGO ===============================
# ========================================================
def processar_webhook_mp(payload: dict):
    """
    Função de utilidade que você chama no endpoint
    `/webhook/mercado-pago` passando o JSON recebido.
    """
    if payload.get("type") != "payment":
        return "ignored"

    data = payload.get("data", {})
    status = data.get("status") or data.get("status_detail")

    # ---------- PAGO COM SUCESSO -------------------------
    if status == "approved":
        telegram_user_id = int(data["metadata"]["telegram_id"])
        venda_id = int(data["external_reference"])
        print(f"[WEBHOOK] Pagamento aprovado • venda {venda_id}")

        # ➜ Atualize sua tabela de vendas aqui (já existente)...
        # atualizar_venda_aprovada(venda_id)

        # --------- BLOCO DE UPGRADE VIP -------------------
        DATABASE_URL = os.environ["DATABASE_URL"]
        comunidade_id = 1  # ID da comunidade VIP padrão

        try:
            with psycopg2.connect(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO membros (telegram_id, comunidade_id, nivel)
                        VALUES (%s,%s,'vip')
                        ON CONFLICT (telegram_id, comunidade_id)
                        DO UPDATE SET nivel='vip'
                        """,
                        (telegram_user_id, comunidade_id),
                    )
                    conn.commit()
            print(f"[VIP] Usuário {telegram_user_id} marcado como VIP ✅")
        except Exception as e:
            print(f"[ERRO VIP] Falha ao atualizar nível VIP: {e}")
            traceback.print_exc()
        # --------------------------------------------------

        return "ok"

    # --- Não aprovado (pending, rejected, etc.) ----------
    print(f"[WEBHOOK] Pagamento {payload['id']} com status {status}")
    return "ignored"


