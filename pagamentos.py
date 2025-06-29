import os
import mercadopago # SDK oficial do Mercado Pago
import json # Usado para serializar/deserializar JSON, especialmente para logs
import traceback # Para imprimir o stack trace completo em caso de erro

# --- Variáveis Globais para o SDK e URL do Webhook ---
# É crucial que estas variáveis sejam inicializadas via init_mercadopago_sdk()
# antes de qualquer operação de pagamento.
sdk = None
BASE_URL_FOR_MP_WEBHOOK = None


def init_mercadopago_sdk():
    """
    Inicializa o SDK do Mercado Pago e define a BASE_URL global para o webhook do MP.
    Esta função deve ser chamada UMA VEZ na inicialização da aplicação (ex: no main do app.py)
    para garantir que as variáveis de ambiente já foram carregadas.
    """
    global sdk, BASE_URL_FOR_MP_WEBHOOK

    # Obtém o token de acesso do Mercado Pago das variáveis de ambiente
    access_token = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
    # Obtém a URL base da aplicação (onde o webhook será recebido)
    base_url_env = os.getenv('BASE_URL')

    # Validações essenciais
    if access_token is None or access_token == "":
        print("[ERRO FATAL MP] MERCADOPAGO_ACCESS_TOKEN não está definida ou está vazia.")
        raise ValueError("MERCADOPAGO_ACCESS_TOKEN é obrigatória e não foi definida corretamente.")

    if base_url_env is None or base_url_env == "":
        print("[ERRO FATAL MP] BASE_URL não está definida ou está vazia para o webhook do Mercado Pago.")
        raise ValueError("BASE_URL é obrigatória para configurar o webhook do Mercado Pago.")

    try:
        # Inicializa o SDK do Mercado Pago com o token de acesso
        sdk = mercadopago.SDK(access_token)
        # Define a URL base para ser usada na construção da notification_url dos pagamentos
        BASE_URL_FOR_MP_WEBHOOK = base_url_env
        print("DEBUG MP: SDK do Mercado Pago inicializado com sucesso e BASE_URL para webhook definida.")
    except Exception as e:
        print(f"[ERRO FATAL MP] Erro ao inicializar SDK do Mercado Pago: {e}")
        traceback.print_exc() # Imprime o stack trace completo
        raise # Re-levanta a exceção para impedir que a aplicação continue com SDK não inicializado


def criar_pagamento_pix(produto, user, venda_id):
    """
    Cria um pagamento PIX no Mercado Pago com base nos detalhes do produto e usuário.
    Inclui campos de qualidade recomendados e a URL de notificação do webhook.
    Args:
        produto (dict): Dicionário com detalhes do produto (id, nome, preco).
        user (telebot.types.User): Objeto de usuário do Telegram (id, first_name, last_name).
        venda_id (int/str): ID da venda no seu sistema, usado como 'external_reference'.
    Returns:
        dict or None: A resposta completa do Mercado Pago se o pagamento for criado com sucesso,
                      ou None em caso de falha.
    """
    global sdk, BASE_URL_FOR_MP_WEBHOOK

    # Log inicial para depuração do fluxo
    print(f"DEBUG MP (INICIO FUNCAO): Entrando em criar_pagamento_pix. SDK={'Inicializado' if sdk else 'NULO'}, BASE_URL={'Definida' if BASE_URL_FOR_MP_WEBHOOK else 'INDDEFINIDA'}.")

    # Garante que o SDK e a BASE_URL do webhook estão inicializados.
    # Se não estiverem, tenta inicializar (pode acontecer em ambientes de teste unitário, por exemplo).
    if sdk is None or BASE_URL_FOR_MP_WEBHOOK is None:
        print("[AVISO MP] SDK do Mercado Pago não inicializado ou BASE_URL_FOR_MP_WEBHOOK não definida. Tentando inicializar...")
        try:
            init_mercadopago_sdk()
        except ValueError as e:
            print(f"[ERRO MP] Falha na inicialização do SDK antes de criar pagamento: {e}")
            traceback.print_exc() # Imprime o stack trace completo para depuração
            return None

    # Constrói a URL completa para o webhook de notificação do Mercado Pago
    # Esta URL deve ser acessível publicamente pelo Mercado Pago.
    notification_url = f"{BASE_URL_FOR_MP_WEBHOOK}/webhook/mercado-pago"

    print(f"DEBUG MP: Montando payload de pagamento para o produto '{produto.get('nome', 'N/A')}' (ID: {produto.get('id', 'N/A')}).")
    print(f"DEBUG MP: Notification URL para MP: {notification_url}")

    # Validação do preço do produto para evitar erros na API do Mercado Pago
    if not isinstance(produto.get('preco'), (int, float)) or float(produto.get('preco', 0)) <= 0:
        print(f"[ERRO MP] Preço do produto inválido ou negativo: {produto.get('preco')}. Deve ser um número positivo.")
        return None

    # Converte o preço para float para garantir o formato correto exigido pelo Mercado Pago
    transaction_amount = float(produto['preco'])

    # Dados do pagamento conforme a documentação do Mercado Pago (para PIX)
    # Inclui informações do pagador e do item para melhor qualidade da transação.
    payment_data = {
        'transaction_amount': transaction_amount,
        'payment_method_id': 'pix',
        'payer': {
            # Email é obrigatório; usa um placeholder se o usuário não tiver um.
            'email': f"user_{user.id}@email.com",
            'first_name': user.first_name or "Comprador",
            'last_name': user.last_name or "Bot",
            'identification': {
                'type': 'OTHER', # Tipo de documento, 'CPF'/'CNPJ' seriam mais ideais se você coletasse esses dados.
                'number': str(user.id) # Usa o ID do Telegram como um identificador para testes
            }
        },
        'notification_url': notification_url, # URL para o Mercado Pago enviar notificações de status
        'external_reference': str(venda_id), # ID da sua venda para rastreamento
        'description': f"Venda de produto digital: {produto.get('nome', 'Sem Nome')}",
        'statement_descriptor': 'BOTVENDAS', # Texto que aparece na fatura/extrato do cliente
        'additional_info': { # Informações adicionais para melhorar a transação
            "items": [
                {
                    "id": str(produto.get('id', 'N/A')),
                    "title": produto.get('nome', 'Produto'),
                    "description": f"Conteúdo digital: {produto.get('nome', 'Produto')}",
                    "category_id": "digital_content", # Categoria do produto
                    "quantity": 1,
                    "unit_price": transaction_amount,
                }
            ],
            "payer": { # Informações detalhadas do pagador
                "first_name": user.first_name or "Comprador",
                "last_name": user.last_name or "Bot",
                "phone": { # Telefone é opcional, mas melhora a qualidade da transação.
                    "area_code": "11", # Exemplo
                    "number": "999999999" # Exemplo
                }
            },
        }
    }

    print(f"DEBUG MP: Payload completo enviado ao Mercado Pago: {json.dumps(payment_data, indent=2)}")

    try:
        print("DEBUG MP: Chamando sdk.payment().create(payment_data)...")
        payment_response = sdk.payment().create(payment_data)
        payment = payment_response["response"] # A resposta útil está na chave 'response'
        print(f"DEBUG MP: Resposta COMPLETA do Mercado Pago recebida: {json.dumps(payment, indent=2)}")
        return payment
    except mercadopago.exceptions.MPApiException as e:
        # Erros específicos da API do Mercado Pago (HTTP 4xx/5xx)
        print(f"[ERRO MP - API] Falha ao criar pagamento PIX. Status HTTP: {e.status}")
        if e.response:
            print(f"Detalhes do Erro Mercado Pago (e.response): {json.dumps(e.response, indent=2)}")
        else:
            print(f"Nenhum detalhe de erro da API do Mercado Pago disponível no objeto de exceção 'e.response'.")
        traceback.print_exc() # Imprime o stack trace completo
        return None
    except Exception as e:
        # Captura qualquer outra exceção inesperada durante o processo
        print(f"[ERRO GERAL MP] Falha ao criar pagamento PIX (Exceção Inesperada): {e}")
        print(f"Tipo da exceção: {type(e)}")
        traceback.print_exc() # Imprime o stack trace completo
        return None


def verificar_status_pagamento(payment_id):
    """
    Verifica o status de um pagamento específico no Mercado Pago usando o SDK.
    Args:
        payment_id (str): O ID do pagamento no Mercado Pago.
    Returns:
        dict or None: Um dicionário com a resposta do status do pagamento, ou None em caso de falha.
    """
    global sdk
    # Garante que o SDK esteja inicializado antes de fazer a consulta
    if sdk is None:
        print("[AVISO MP] SDK do Mercado Pago não inicializado. Tentando inicializar antes de verificar pagamento...")
        try:
            init_mercadopago_sdk()
        except ValueError as e:
            print(f"[ERRO MP] Falha na inicialização do SDK antes de verificar pagamento: {e}")
            traceback.print_exc()
            return None
    try:
        print(f"DEBUG MP: Verificando status do pagamento ID: {payment_id}")
        payment_info = sdk.payment().get(payment_id) # Faz a chamada à API
        # A resposta útil está na chave 'response'
        status = payment_info['response'].get('status')
        print(f"DEBUG MP: Status do pagamento {payment_id} recebido: {status}")
        return payment_info["response"]
    except mercadopago.exceptions.MPApiException as e:
        # Erros específicos da API do Mercado Pago
        print(f"[ERRO MP] Falha ao verificar status do pagamento (API Error). Status HTTP: {e.status}")
        if e.response:
            print(f"Detalhes do Erro Mercado Pago: {e.response}")
        else:
            print(f"Nenhum detalhe de erro da API do Mercado Pago disponível no objeto de exceção.")
        traceback.print_exc()
        return None
    except Exception as e:
        # Captura qualquer outra exceção inesperada
        print(f"Erro geral ao verificar status do pagamento: {e}")
        traceback.print_exc()
        return None