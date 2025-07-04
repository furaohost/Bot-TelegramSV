import os
import mercadopago
import json
import traceback

# Variável global para guardar a instância do SDK.
sdk = None

def init_mercadopago_sdk():
    """
    Inicializa o SDK do Mercado Pago e armazena na variável global 'sdk'.
    """
    global sdk
    access_token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')

    if not access_token:
        print("[ERRO FATAL MP] MERCADOPAGO_ACCESS_TOKEN não está definida.")
        return

    try:
        print("DEBUG MP: Inicializando SDK do Mercado Pago...")
        sdk = mercadopago.SDK(access_token)
        print("DEBUG MP: SDK inicializado com sucesso.")
    except Exception as e:
        print(f"[ERRO FATAL MP] Erro ao inicializar SDK do Mercado Pago: {e}")
        traceback.print_exc()
        sdk = None

# --- SUAS FUNÇÕES DE PAGAMENTO PIX (MANTIDAS COMO ESTAVAM) ---

def criar_pagamento_pix(produto, user, venda_id):
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
        'transaction_amount': transaction_amount, 'payment_method_id': 'pix',
        'payer': {'email': f"user_{user.id}@telegram.user", 'first_name': user.first_name or "Comprador", 'last_name': user.last_name or "Bot"},
        'notification_url': notification_url, 'external_reference': str(venda_id), 'description': f"Venda de: {produto.get('nome', 'Produto Digital')}"
    }
    try:
        payment_response = sdk.payment().create(payment_data)
        return payment_response.get("response")
    except Exception as e:
        print(f"[ERRO GERAL MP] Falha ao criar pagamento PIX: {e}")
        traceback.print_exc()
        return None

def verificar_status_pagamento(payment_id):
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

# --- FUNÇÕES DE ASSINATURA CORRIGIDAS COM A SINTAXE ANTIGA (v1.x) ---

def criar_plano_de_assinatura_mp(plan_data):
    """
    Cria um plano de assinatura recorrente no Mercado Pago usando a sintaxe antiga (v1.x).
    """
    global sdk
    if not sdk:
        return {"error": "SDK do Mercado Pago não foi inicializado."}

    try:
        request_options = {
            "reason": plan_data['name'],
            "auto_recurring": {
                "frequency": plan_data['frequency'],
                "frequency_type": plan_data['frequency_type'],
                "transaction_amount": plan_data['price'],
                "currency_id": "BRL"
            },
            "back_url": os.getenv("BASE_URL", "https://www.google.com"),
            "status": "active"
        }
        
        print(f"DEBUG MP: Enviando dados para criar plano (sintaxe antiga): {request_options}")
        # CORREÇÃO: Usando a sintaxe antiga que o seu ambiente espera
        plan_response = sdk.preapproval_plan().create(request_options)
        print(f"DEBUG MP: Resposta da API: {plan_response}")
        
        if plan_response and plan_response.get("status") == 201:
            return plan_response["response"]
        else:
            error_message = plan_response.get("response", {}).get("message", "Erro desconhecido da API.")
            return {"error": error_message, "details": plan_response}

    except Exception as e:
        print(f"ERRO CRÍTICO ao criar plano no MP: {e}")
        # Tratamento de erro mais genérico para a versão antiga da lib
        if hasattr(e, 'response'):
             print(f"ERRO API MP ao criar plano: {e.response}")
             return {"error": getattr(e, 'message', str(e)), "details": e.response}
        return {"error": str(e)}

def criar_link_de_assinatura(plan, user):
    """
    Cria uma assinatura para um usuário usando a sintaxe antiga (v1.x).
    """
    global sdk
    if not sdk:
        return None

    try:
        external_reference = f"user:{user.id}_plan:{plan['id']}"
        subscription_data = {
            "preapproval_plan_id": plan['mercadopago_plan_id'],
            "reason": plan['name'],
            "payer_email": f"{user.id}@telegram.user",
            "back_url": f"https://t.me/{os.getenv('BOT_USERNAME', 'seu_bot_username')}",
            "external_reference": external_reference
        }

        print(f"DEBUG MP: Enviando dados para criar assinatura (sintaxe antiga): {subscription_data}")
        # CORREÇÃO: Usando a sintaxe antiga
        subscription_response = sdk.preapproval().create(subscription_data)
        print(f"DEBUG MP: Resposta da API de assinatura: {subscription_response}")
        
        if subscription_response and subscription_response.get("status") == 201:
            return subscription_response["response"]
        return None

    except Exception as e:
        print(f"ERRO CRÍTICO ao criar link de assinatura no MP: {e}")
        return None

def verificar_assinatura_mp(subscription_id):
    """
    Busca os detalhes de uma assinatura usando a sintaxe antiga (v1.x).
    """
    global sdk
    if not sdk:
        return None
    
    try:
        print(f"DEBUG MP: Verificando assinatura com ID (sintaxe antiga): {subscription_id}")
        # CORREÇÃO: Usando a sintaxe antiga
        subscription_details = sdk.preapproval().get(subscription_id)
        print(f"DEBUG MP: Detalhes da assinatura recebidos: {subscription_details}")

        if subscription_details and subscription_details.get("status") == 200:
            return subscription_details["response"]
        return None

    except Exception as e:
        print(f"ERRO CRÍTICO ao verificar assinatura no MP: {e}")
        return None
    
    