import os
import mercadopago

# Remova a inicialização do sdk daqui:
# sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN)
# MERCADOPAGO_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
# BASE_URL = os.getenv('BASE_URL')

# Declare sdk como global, mas inicialize-o depois
sdk = None
BASE_URL_GLOBAL = None # Use um nome diferente para evitar conflito ou ambiguidade

def init_mercadopago_sdk():
    """
    Inicializa o SDK do Mercado Pago e outras variáveis após ter certeza
    que as variáveis de ambiente estão carregadas.
    """
    global sdk, BASE_URL_GLOBAL # Declara que estamos modificando as variáveis globais

    # Leitura das variáveis de ambiente
    access_token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
    base_url_env = os.getenv('BASE_URL')

    if access_token is None or access_token == "":
        raise ValueError("ERRO CRÍTICO: MERCADOPAGO_ACCESS_TOKEN não está definido ou está vazio.")
    if base_url_env is None or base_url_env == "":
        raise ValueError("ERRO CRÍTICO: BASE_URL não está definido ou está vazio.")

    sdk = mercadopago.SDK(access_token)
    BASE_URL_GLOBAL = base_url_env
    print("SDK do Mercado Pago inicializado com sucesso.")


def criar_pagamento_pix(produto, user, venda_id):
    """
    Cria um pagamento PIX no Mercado Pago com todos os campos de qualidade recomendados.
    """
    if sdk is None: # Garante que o SDK foi inicializado
        print("[ERRO] SDK do Mercado Pago não inicializado. Tentando inicializar...")
        try:
            init_mercadopago_sdk()
        except ValueError as e:
            print(f"[ERRO] Falha na inicialização do SDK: {e}")
            return None

    if not BASE_URL_GLOBAL: # Usa a variável global agora
        print("[ERRO] A variável de ambiente BASE_URL_GLOBAL não está definida mesmo após inicialização.")
        return None
        
    notification_url = f"{BASE_URL_GLOBAL}/webhook/mercado-pago" # Usa a variável global agora
    
    # ... (restante do seu payment_data) ...
    payment_data = {
        'transaction_amount': float(produto['preco']),
        'payment_method_id': 'pix',
        'payer': {
            'email': f"user_{user.id}@email.com",
            'first_name': user.first_name or "Comprador",
            'last_name': user.last_name or "Bot",
            'identification': {
                'type': 'OTHER',
                'number': str(user.id)
            }
        },
        'notification_url': notification_url,
        'external_reference': str(venda_id),
        'description': f"Venda de produto digital: {produto['nome']}",
        'statement_descriptor': 'BOTVENDAS',
        'additional_info': {
            "items": [
                {
                    "id": str(produto['id']),
                    "title": produto['nome'],
                    "description": f"Conteúdo digital: {produto['nome']}",
                    "category_id": "digital_content",
                    "quantity": 1,
                    "unit_price": float(produto['preco']),
                }
            ],
            "payer": {
                "first_name": user.first_name or "Comprador",
                "last_name": user.last_name or "Bot",
                "phone": {
                    "area_code": "11",
                    "number": "999999999"
                }
            },
        }
    }

    try:
        payment_response = sdk.payment().create(payment_data)
        payment = payment_response["response"]
        return payment
    except Exception as e:
        print(f"Erro ao criar pagamento PIX: {e}")
        if hasattr(e, 'response') and hasattr(e.response, 'json'):
            print("Resposta do MP:", e.response.json())
        return None

def verificar_status_pagamento(payment_id):
    """
    Verifica o status de um pagamento específico no Mercado Pago.
    """
    if sdk is None: # Garante que o SDK foi inicializado
        print("[ERRO] SDK do Mercado Pago não inicializado. Tentando inicializar...")
        try:
            init_mercadopago_sdk()
        except ValueError as e:
            print(f"[ERRO] Falha na inicialização do SDK: {e}")
            return None
    try:
        payment_info = sdk.payment().get(payment_id)
        return payment_info["response"]
    except Exception as e:
        print(f"Erro ao verificar status do pagamento: {e}")
        return None