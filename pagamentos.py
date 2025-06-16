import os
import mercadopago

# --- Variáveis Globais para o SDK ---
# Serão inicializadas pela função init_mercadopago_sdk()
sdk = None
BASE_URL_FOR_MP_WEBHOOK = None # Variável global para a BASE_URL usada especificamente pelo Mercado Pago


def init_mercadopago_sdk():
    """
    Inicializa o SDK do Mercado Pago e a BASE_URL global para o webhook do MP.
    Esta função deve ser chamada após a garantia de que as variáveis de ambiente
    já foram carregadas (ex: no main do app.py).
    """
    global sdk, BASE_URL_FOR_MP_WEBHOOK

    # Lendo as chaves diretamente das Variáveis de Ambiente
    access_token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
    base_url_env = os.getenv('BASE_URL') # Pega a BASE_URL definida no Render/app.py

    # Verificações de segurança para garantir que os tokens não são None ou vazios
    if access_token is None or access_token == "":
        print("[ERRO FATAL MP] MERCADOPAGO_ACCESS_TOKEN não está definida ou está vazia.")
        raise ValueError("MERCADOPAGO_ACCESS_TOKEN é obrigatória e não foi definida corretamente.")

    if base_url_env is None or base_url_env == "":
        print("[ERRO FATAL MP] BASE_URL não está definida ou está vazia para o webhook do Mercado Pago.")
        raise ValueError("BASE_URL é obrigatória para configurar o webhook do Mercado Pago.")

    try:
        sdk = mercadopago.SDK(access_token)
        BASE_URL_FOR_MP_WEBHOOK = base_url_env
        print("SDK do Mercado Pago inicializado com sucesso.")
    except Exception as e:
        print(f"[ERRO FATAL MP] Erro ao inicializar SDK do Mercado Pago: {e}")
        raise


def criar_pagamento_pix(produto, user, venda_id):
    """
    Cria um pagamento PIX no Mercado Pago com todos os campos de qualidade recomendados.
    """
    global sdk, BASE_URL_FOR_MP_WEBHOOK

    # Garante que o SDK foi inicializado antes de tentar usá-lo
    if sdk is None or BASE_URL_FOR_MP_WEBHOOK is None:
        print("[AVISO] SDK do Mercado Pago não inicializado ou BASE_URL_FOR_MP_WEBHOOK não definida. Tentando inicializar...")
        try:
            init_mercadopago_sdk()
        except ValueError as e:
            print(f"[ERRO] Falha na inicialização do SDK antes de criar pagamento: {e}")
            return None # Retorna None se a inicialização falhar

    notification_url = f"{BASE_URL_FOR_MP_WEBHOOK}/webhook/mercado-pago"
    
    payment_data = {
        'transaction_amount': float(produto['preco']),
        'payment_method_id': 'pix',
        'payer': {
            'email': f"user_{user.id}@email.com", # Email genérico baseado no user_id
            'first_name': user.first_name or "Comprador",
            'last_name': user.last_name or "Bot",
            'identification': {
                'type': 'OTHER', # Tipo de identificação genérico
                'number': str(user.id) # Usando o ID do Telegram como número de identificação
            }
        },
        'notification_url': notification_url,
        'external_reference': str(venda_id), # Referência externa para associar o pagamento à sua venda
        'description': f"Venda de produto digital: {produto['nome']}",
        'statement_descriptor': 'BOTVENDAS', # Descritor que aparecerá na fatura do pagador (limite de caracteres)
        'additional_info': {
            "items": [
                {
                    "id": str(produto['id']),
                    "title": produto['nome'],
                    "description": f"Conteúdo digital: {produto['nome']}",
                    "category_id": "digital_content", # Categoria de item (importante para PIX)
                    "quantity": 1,
                    "unit_price": float(produto['preco']),
                }
            ],
            # Informações do pagador adicionais (alguns campos são opcionais, mas recomendados)
            "payer": {
                "first_name": user.first_name or "Comprador",
                "last_name": user.last_name or "Bot",
                "phone": {
                    "area_code": "11", # Substituir por área real se tiver
                    "number": "999999999" # Substituir por número real se tiver
                }
            },
        }
    }

    try:
        # A chamada real para a API do Mercado Pago para criar o pagamento
        payment_response = sdk.payment().create(payment_data)
        payment = payment_response["response"]
        return payment
    except mercadopago.exceptions.MPApiException as e: # Captura exceções específicas do MP
        print(f"[ERRO MP] Falha ao criar pagamento PIX (API Error): {e}")
        if e.status and e.response: # Detalhes da resposta da API
            print(f"Status HTTP: {e.status}")
            print(f"Erro Mercado Pago: {e.response}")
        return None
    except Exception as e: # Captura outras exceções genéricas
        print(f"[ERRO GERAL] Falha ao criar pagamento PIX: {e}")
        return None


def verificar_status_pagamento(payment_id):
    """
    Verifica o status de um pagamento específico no Mercado Pago.
    """
    global sdk # Garante que estamos usando a variável global
    if sdk is None:
        print("[AVISO] SDK do Mercado Pago não inicializado. Tentando inicializar...")
        try:
            init_mercadopago_sdk()
        except ValueError as e:
            print(f"[ERRO] Falha na inicialização do SDK antes de verificar pagamento: {e}")
            return None
    try:
        payment_info = sdk.payment().get(payment_id)
        return payment_info["response"]
    except mercadopago.exceptions.MPApiException as e:
        print(f"[ERRO MP] Falha ao verificar status do pagamento (API Error): {e}")
        if e.status and e.response:
            print(f"Status HTTP: {e.status}")
            print(f"Erro Mercado Pago: {e.response}")
        return None
    except Exception as e:
        print(f"Erro geral ao verificar status do pagamento: {e}")
        return None