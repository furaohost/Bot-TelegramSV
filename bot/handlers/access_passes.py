# bot/handlers/access_passes.py

from telebot import types
from database import get_db_connection
import pagamentos  # Reutilizaremos a função de criar PIX
import traceback
import base64 # Para decodificar o QR Code

def register_access_pass_handlers(bot):
    """Registra todos os handlers relacionados aos Passes de Acesso."""

    @bot.message_handler(commands=['passes'])
    def handle_show_passes(message):
        """
        Busca e exibe os passes de acesso ativos para o usuário.
        """
        chat_id = message.chat.id
        print(f"DEBUG: Comando /passes recebido do chat {chat_id}")
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM access_passes WHERE is_active = TRUE ORDER BY price ASC")
                passes = cur.fetchall()

            if not passes:
                bot.send_message(chat_id, "😕 Nenhum passe de acesso disponível no momento.")
                return

            bot.send_message(chat_id, "✨ Nossos Passes de Acesso:")
            
            for pass_item in passes:
                pass_description = (
                    f"*{pass_item['name']}*\n"
                    f"_{pass_item['description'] or 'Acesso exclusivo.'}_\n\n"
                    f"⏳ *Duração:* {pass_item['duration_days']} dias\n"
                    f"💰 *Preço:* R$ {pass_item['price']:.2f}"
                )
                
                markup = types.InlineKeyboardMarkup()
                # O callback_data agora identifica uma compra de passe
                buy_button = types.InlineKeyboardButton("Comprar Passe", callback_data=f"buy_pass_{pass_item['id']}")
                markup.add(buy_button)
                
                bot.send_message(chat_id, pass_description, reply_markup=markup, parse_mode='Markdown')

        except Exception as e:
            print(f"ERRO ao mostrar passes: {e}")
            traceback.print_exc()
            bot.send_message(chat_id, "Ocorreu um erro ao buscar os passes. Tente novamente mais tarde.")
        finally:
            if conn:
                conn.close()

    @bot.callback_query_handler(func=lambda call: call.data.startswith('buy_pass_'))
    def handle_buy_pass_callback(call):
        """
        Processa o clique no botão 'Comprar Passe' e gera um pagamento PIX.
        """
        chat_id = call.message.chat.id
        user = call.from_user
        pass_id = int(call.data.split('_')[1])
        
        bot.answer_callback_query(call.id, "Gerando seu pagamento PIX...")
        print(f"DEBUG: Usuário {user.id} tentando comprar o passe {pass_id}")

        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM access_passes WHERE id = %s AND is_active = TRUE", (pass_id,))
                pass_item = cur.fetchone()

            if not pass_item:
                bot.send_message(chat_id, "Este passe de acesso não está mais disponível.")
                return

            # Criamos uma referência externa única para identificar esta compra no webhook
            external_reference = f"pass_purchase:user_id={user.id}:pass_id={pass_id}"

            # Reutilizamos a função de criar PIX, tratando o passe como um "produto"
            payment_info = pagamentos.criar_pagamento_pix(
                produto=pass_item, 
                user=user, 
                venda_id=external_reference # Usamos nossa referência customizada aqui
            )

            if payment_info and 'point_of_interaction' in payment_info:
                qr_code_base64 = payment_info['point_of_interaction']['transaction_data']['qr_code_base64']
                qr_code_data = payment_info['point_of_interaction']['transaction_data']['qr_code']
                qr_code_image = base64.b64decode(qr_code_base64)

                caption_text = (
                    f"✅ PIX gerado para *{pass_item['name']}*!\n\n"
                    "Escaneie o QR Code acima ou copie o código completo na próxima mensagem."
                )
                bot.send_photo(chat_id, qr_code_image, caption=caption_text, parse_mode='Markdown')
                bot.send_message(chat_id, f"`{qr_code_data}`", parse_mode='Markdown') # Envia o código em um bloco de código
                bot.send_message(chat_id, "Seu acesso será liberado assim que o pagamento for confirmado.")
            else:
                bot.send_message(chat_id, "😕 Desculpe, não foi possível gerar o seu pagamento PIX no momento.")
                print(f"ERRO: Falha ao obter PIX para passe. Resposta: {payment_info}")

        except Exception as e:
            print(f"ERRO no callback de compra de passe: {e}")
            traceback.print_exc()
            bot.send_message(chat_id, "Ocorreu um erro inesperado. Nossa equipe já foi notificada.")
        finally:
            if conn:
                conn.close()
