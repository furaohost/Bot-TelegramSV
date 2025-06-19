import os
import mercadopago

# --- Variáveis Globais para o SDK ---
sdk = None
BASE_URL_FOR_MP_WEBHOOK = None


def init_mercadopago_sdk():
    global sdk, BASE_URL_FOR_MP_WEBHOOK

    access_token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
    base_url_env = os.getenv('BASE_URL')

    if access_token is None or access_token == "":
        print("[ERRO FATAL MP] MERCADOPAGO_ACCESS_TOKEN não está definida ou está vazia.")
        raise ValueError("MERCADOPAGO_ACCESS_TOKEN é obrigatória e não foi definida corretamente.")

    if base_url_env is None or base_url_env == "":
        print("[ERRO FATAL MP] BASE_URL não está definida ou está vazia para o webhook do Mercado Pago.")
        raise ValueError("BASE_URL é obrigatória para configurar o webhook do Mercado Pago.")

    try:
        sdk = mercadopago.SDK(access_token)
        BASE_URL_FOR_MP_WEBHOOK = base_url_env
        print("DEBUG MP: SDK do Mercado Pago inicializado com sucesso.")
    except Exception as e:
        print(f"[ERRO FATAL MP] Erro ao inicializar SDK do Mercado Pago: {e}")
        raise


def criar_pagamento_pix(produto, user, venda_id):
    global sdk, BASE_URL_FOR_MP_WEBHOOK

    if sdk is None or BASE_URL_FOR_MP_WEBHOOK is None:
        print("[AVISO MP] SDK do Mercado Pago não inicializado ou BASE_URL_FOR_MP_WEBHOOK não definida. Tentando inicializar...")
        try:
            init_mercadopago_sdk()
        except ValueError as e:
            print(f"[ERRO MP] Falha na inicialização do SDK antes de criar pagamento: {e}")
            return None

    notification_url = f"{BASE_URL_FOR_MP_WEBHOOK}/webhook/mercado-pago"

    print(f"DEBUG MP: Montando payload de pagamento para o produto '{produto['nome']}' (ID: {produto['id']}).")
    print(f"DEBUG MP: Notification URL para MP: {notification_url}") # Adicionado log da URL

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

    # Log do payload completo antes do envio
    print(f"DEBUG MP: Payload completo enviado ao Mercado Pago: {json.dumps(payment_data, indent=2)}")

    try:
        print(f"DEBUG MP: Enviando requisição de pagamento para o Mercado Pago...")
        payment_response = sdk.payment().create(payment_data)
        payment = payment_response["response"]
        print(f"DEBUG MP: Resposta COMPLETA do Mercado Pago recebida: {json.dumps(payment, indent=2)}") # Log da resposta completa formatada
        return payment
    except mercadopago.exceptions.MPApiException as e:
        print(f"[ERRO MP - API] Falha ao criar pagamento PIX. Status HTTP: {e.status}")
        if e.response:
            print(f"Detalhes do Erro Mercado Pago (e.response): {json.dumps(e.response, indent=2)}") # Log detalhado da resposta de erro
        else:
            print(f"Nenhum detalhe de erro da API do Mercado Pago disponível no objeto de exceção 'e.response'.")
        return None
    except Exception as e:
        print(f"[ERRO GERAL MP] Falha ao criar pagamento PIX (Exceção Inesperada): {e}")
        # Loga o tipo da exceção também, para ajudar a identificar
        print(f"Tipo da exceção: {type(e)}")
        return None


def verificar_status_pagamento(payment_id):
    global sdk
    if sdk is None:
        print("[AVISO MP] SDK do Mercado Pago não inicializado. Tentando inicializar...")
        try:
            init_mercadopago_sdk()
        except ValueError as e:
            print(f"[ERRO MP] Falha na inicialização do SDK antes de verificar pagamento: {e}")
            return None
    try:
        print(f"DEBUG MP: Verificando status do pagamento ID: {payment_id}")
        payment_info = sdk.payment().get(payment_id)
        print(f"DEBUG MP: Status do pagamento {payment_id} recebido: {payment_info['response'].get('status')}")
        return payment_info["response"]
    except mercadopago.exceptions.MPApiException as e:
        print(f"[ERRO MP] Falha ao verificar status do pagamento (API Error). Status HTTP: {e.status}")
        if e.response:
            print(f"Detalhes do Erro Mercado Pago: {e.response}")
        else:
            print(f"Nenhum detalhe de erro da API do Mercado Pago disponível no objeto de exceção.")
        return None
    except Exception as e:
        print(f"Erro geral ao verificar status do pagamento: {e}")
        return None
