import os
import mercadopago # SDK oficial do Mercado Pago
import json # Usado para serializar/deserializar JSON, especialmente para logs
import traceback # Para imprimir o stack trace completo em caso de erro

# --- ALTERAÇÃO 1: Variável global para guardar a instância do SDK ---
# Esta variável será definida uma única vez e reutilizada por todas as funções.
sdk = None

# --- ALTERAÇÃO 2: Função de inicialização simplificada ---
def init_mercadopago_sdk():
    """
    Inicializa o SDK do Mercado Pago e armazena na variável global 'sdk'.
    Esta função deve ser chamada UMA VEZ na inicialização da aplicação (app.py).
    """
    global sdk
    access_token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')

    if not access_token:
        print("[ERRO FATAL MP] MERCADOPAGO_ACCESS_TOKEN não está definida.")
        # Não levanta erro aqui, apenas não inicializa. As funções abaixo verificarão.
        return

    try:
        print("DEBUG MP: Inicializando SDK do Mercado Pago...")
        sdk = mercadopago.SDK(access_token)
        print("DEBUG MP: SDK inicializado com sucesso.")
    except Exception as e:
        print(f"[ERRO FATAL MP] Erro ao inicializar SDK do Mercado Pago: {e}")
        traceback.print_exc()
        sdk = None

# --- ALTERAÇÃO 3: Funções agora usam a variável global 'sdk' ---

def criar_pagamento_pix(produto, user, venda_id):
    """
    Cria um pagamento PIX no Mercado Pago.
    """
    global sdk
    if sdk is None:
        print("[ERRO MP] Tentativa de criar pagamento PIX, mas o SDK não está inicializado.")
        return None

    notification_url = f"{os.getenv('BASE_URL')}/webhook/mercado-pago"
    
    try:
        transaction_amount = float(str(produto.get('preco')).replace(',', '.'))
    except (ValueError, TypeError):
        print(f"[ERRO MP] Preço inválido para o produto ID {produto.get('id')}: {produto.get('preco')}")
        return None

    payment_data = {
        'transaction_amount': transaction_amount,
        'payment_method_id': 'pix',
        'payer': {
            'email': f"user_{user.id}@telegram.user",
            'first_name': user.first_name or "Comprador",
            'last_name': user.last_name or "Bot"
        },
        'notification_url': notification_url,
        'external_reference': str(venda_id),
        'description': f"Venda de: {produto.get('nome', 'Produto Digital')}"
    }

    try:
        payment_response = sdk.payment().create(payment_data)
        return payment_response.get("response")
    except Exception as e:
        print(f"[ERRO GERAL MP] Falha ao criar pagamento PIX: {e}")
        traceback.print_exc()
        return None

def verificar_status_pagamento(payment_id):
    """
    Verifica o status de um pagamento específico no Mercado Pago.
    """
    global sdk
    if sdk is None:
        print("[ERRO MP] Tentativa de verificar pagamento, mas o SDK não está inicializado.")
        return None
    try:
        payment_info = sdk.payment().get(payment_id)
        return payment_info.get("response")
    except Exception as e:
        print(f"Erro geral ao verificar status do pagamento: {e}")
        traceback.print_exc()
        return None

def criar_plano_de_assinatura_mp(plan_data):
    """
    Cria um plano de assinatura recorrente no Mercado Pago.
    """
    global sdk
    if not sdk:
        print("ERRO: Tentativa de criar plano, mas o SDK não está inicializado.")
        return {"error": "SDK do Mercado Pago não foi inicializado."}

    base_url = os.getenv("BASE_URL", "https://www.google.com") 

    request_options = {
        "reason": plan_data['name'],
        "auto_recurring": {
            "frequency": plan_data['frequency'],
            "frequency_type": plan_data['frequency_type'],
            "transaction_amount": plan_data['price'],
            "currency_id": "BRL"
        },
        "back_url": base_url,
        "status": "active"
    }

    try:
        plan_response = sdk.preapproval_plan().create(request_options)
        if plan_response and plan_response.get("status") == 201:
            return plan_response["response"]
        else:
            error_message = plan_response.get("response", {}).get("message", "Erro desconhecido da API.")
            return {"error": error_message, "details": plan_response}
    except Exception as e:
        print(f"ERRO CRÍTICO ao criar plano no MP: {e}")
        return {"error": str(e)}

def criar_link_de_assinatura(plan, user):
    """
    Cria uma assinatura para um usuário com base em um plano.
    """
    global sdk
    if not sdk:
        print("ERRO: Tentativa de criar link de assinatura, mas o SDK não está inicializado.")
        return None

    external_reference = f"user:{user.id}_plan:{plan['id']}"
    subscription_data = {
        "preapproval_plan_id": plan['mercadopago_plan_id'],
        "reason": plan['name'],
        "payer_email": f"{user.id}@telegram.user",
        "back_url": f"https://t.me/{os.getenv('BOT_USERNAME', 'seu_bot_username')}",
        "external_reference": external_reference
    }

    try:
        subscription_response = sdk.preapproval().create(subscription_data)
        if subscription_response and subscription_response.get("status") == 201:
            return subscription_response["response"]
        else:
            return None
    except Exception as e:
        print(f"ERRO CRÍTICO ao criar link de assinatura no MP: {e}")
        return None

def verificar_assinatura_mp(subscription_id):
    """
    Busca os detalhes de uma assinatura específica no Mercado Pago.
    """
    global sdk
    if not sdk:
        print("ERRO: Tentativa de verificar assinatura, mas o SDK não está inicializado.")
        return None
    
    try:
        subscription_details = sdk.preapproval().get(subscription_id)
        if subscription_details and subscription_details.get("status") == 200:
            return subscription_details["response"]
        else:
            return None
    except Exception as e:
        print(f"ERRO CRÍTICO ao verificar assinatura no MP: {e}")
        return None
