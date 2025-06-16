import os
import mercadopago

# --- CONFIGURAÇÃO ATUALIZADA ---
# Lendo as chaves diretamente das Variáveis de Ambiente
MERCADOPAGO_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
BASE_URL = os.getenv('BASE_URL')

sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN)

def criar_pagamento_pix(produto, user, venda_id):
    """
    Cria um pagamento PIX no Mercado Pago com todos os campos de qualidade recomendados.
    """
    if not BASE_URL:
        print("[ERRO] A variável de ambiente BASE_URL não está definida.")
        return None
        
    notification_url = f"{BASE_URL}/webhook/mercado-pago"
    
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
    try:
        payment_info = sdk.payment().get(payment_id)
        return payment_info["response"]
    except Exception as e:
        print(f"Erro ao verificar status do pagamento: {e}")
        return None
