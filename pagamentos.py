import os
import mercadopago 
import json 
import traceback 

sdk = None
BASE_URL_FOR_MP_WEBHOOK = None


def init_mercadopago_sdk():
    global sdk, BASE_URL_FOR_MP_WEBHOOK
    access_token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
    base_url_env = os.getenv('BASE_URL')

    if access_token is None or access_token == "":
        print(f"[ERRO FATAL MP] MERCADOPAGO_ACCESS_TOKEN não está definida ou está vazia.")
        raise ValueError("MERCADOPAGO_ACCESS_TOKEN é obrigatória e não foi definida corretamente.")

    if base_url_env is None or base_url_env == "":
        print(f"[ERRO FATAL MP] BASE_URL não está definida ou está vazia para o webhook do Mercado Pago.")
        raise ValueError("BASE_URL é obrigatória para configurar o webhook do Mercado Pago.")

    try:
        sdk = mercadopago.SDK(access_token)
        BASE_URL_FOR_MP_WEBHOOK = base_url_env
        print(f"DEBUG MP: SDK do Mercado Pago inicializado com sucesso e BASE_URL para webhook definida.")
    except Exception as e:
        print(f"[ERRO FATAL MP] Erro ao inicializar SDK do Mercado Pago: {e}")
        traceback.print_exc() 
        raise 


def criar_pagamento_pix(produto, user, venda_id):
    global sdk, BASE_URL_FOR_MP_WEBHOOK

    print(f"DEBUG MP (INICIO FUNCAO): Entrando em criar_pagamento_pix. SDK={'Inicializado' if sdk else 'NULO'}, BASE_URL={'Definida' if BASE_URL_FOR_MP_WEBHOOK else 'INDDEFINIDA'}.")

    if sdk is None or BASE_URL_FOR_MP_WEBHOOK is None:
        print(f"[AVISO MP] SDK do Mercado Pago não inicializado ou BASE_URL_FOR_MP_WEBHOOK não definida. Tentando inicializar...")
        try:
            init_mercadopago_sdk()
        except ValueError as e:
            print(f"[ERRO MP] Falha na inicialização do SDK antes de criar pagamento: {e}")
            traceback.print_exc() 
            return None

    notification_url = f"{BASE_URL_FOR_MP_WEBHOOK}/webhook/mercado-pago"

    # --- LÓGICA CORRIGIDA E MAIS ROBUSTA ---
    # Tenta obter 'price' (para passes) e, se não encontrar, tenta 'preco' (para produtos).
    preco_raw = produto.get('price', produto.get('preco'))
    # Tenta obter 'name' (para passes) e, se não encontrar, tenta 'nome' (para produtos).
    nome_item = produto.get('name', produto.get('nome', 'Item Desconhecido'))
    item_id = produto.get('id', 'N/A')
    # --- FIM DA CORREÇÃO ---

    print(f"DEBUG MP: Montando payload de pagamento para o produto '{produto.get('nome', 'N/A')}' (ID: {produto.get('id', 'N/A')}).")
    print(f"DEBUG MP: Notification URL para MP: {notification_url}")

    
    print(f"DEBUG MP: Valor bruto do preço: '{preco_raw}' (Tipo: {type(preco_raw)})")

    transaction_amount = None 

    try:
        if isinstance(preco_raw, str):
            transaction_amount = float(preco_raw.replace(',', '.'))
        else:
            transaction_amount = float(preco_raw)

        print(f"DEBUG MP: Preço convertido para float (transaction_amount): '{transaction_amount}' (Tipo: {type(transaction_amount)})")

        if transaction_amount <= 0:
            print(f"[ERRO MP] Preço do produto inválido ou negativo após conversão: {transaction_amount}. Deve ser um número positivo.")
            return None
    except (ValueError, TypeError) as e:
        print(f"[ERRO MP] Não foi possível converter o preço '{preco_raw}' para um número válido: {e}")
        traceback.print_exc()
        return None

    if transaction_amount is None:
        return None

    payment_data = {
        'transaction_amount': transaction_amount,
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
        'description': f"Venda de produto digital: {produto.get('nome', 'Sem Nome')}",
        'statement_descriptor': 'BOTVENDAS', 
        'additional_info': { 
            "items": [
                {
                    "id": str(produto.get('id', 'N/A')),
                    "title": produto.get('nome', 'Produto'),
                    "description": f"Conteúdo digital: {produto.get('nome', 'Produto')}",
                    "category_id": "digital_content", 
                    "quantity": 1,
                    "unit_price": transaction_amount,
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

    print(f"DEBUG MP: Payload completo enviado ao Mercado Pago: {json.dumps(payment_data, indent=2)}")

    try:
        print(f"DEBUG MP: Chamando sdk.payment().create(payment_data)...")
        payment_response = sdk.payment().create(payment_data)
        payment = payment_response["response"] 
        print(f"DEBUG MP: Resposta COMPLETA do Mercado Pago recebida: {json.dumps(payment, indent=2)}")
        return payment
    except mercadopago.exceptions.MPApiException as e:
        print(f"[ERRO MP - API] Falha ao criar pagamento PIX. Status HTTP: {e.status}")
        if e.response:
            print(f"Detalhes do Erro Mercado Pago (e.response): {json.dumps(e.response, indent=2)}")
        else:
            print(f"Nenhum detalhe de erro da API do Mercado Pago disponível no objeto de exceção 'e.response'.")
        traceback.print_exc() 
        return None
    except Exception as e:
        print(f"[ERRO GERAL MP] Falha ao criar pagamento PIX (Exceção Inesperada): {e}")
        print(f"Tipo da exceção: {type(e)}")
        traceback.print_exc() 
        return None


def verificar_status_pagamento(payment_id):
    global sdk
    if sdk is None:
        print(f"[AVISO MP] SDK do Mercado Pago não inicializado. Tentando inicializar antes de verificar pagamento...")
        try:
            init_mercadopago_sdk()
        except ValueError as e:
            print(f"[ERRO MP] Falha na inicialização do SDK antes de verificar pagamento: {e}")
            traceback.print_exc()
            return None
    try:
        print(f"DEBUG MP: Verificando status do pagamento ID: {payment_id}")
        payment_info = sdk.payment().get(payment_id) 
        status = payment_info['response'].get('status')
        print(f"DEBUG MP: Status do pagamento {payment_id} recebido: {status}")
        return payment_info["response"]
    except mercadopago.exceptions.MPApiException as e:
        print(f"[ERRO MP] Falha ao verificar status do pagamento (API Error). Status HTTP: {e.status}")
        if e.response:
            print(f"Detalhes do Erro Mercado Pago: {e.response}")
        else:
            print(f"Nenhum detalhe de erro da API do Mercado Pago disponível no objeto de exceção.")
        traceback.print_exc()
        return None
    except Exception as e:
        print(f"Erro geral ao verificar status do pagamento: {e}")
        traceback.print_exc()
        return None