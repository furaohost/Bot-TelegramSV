# bot/handlers/subscriptions.py

from telebot import types
from database import get_db_connection
import pagamentos
import traceback

def register_subscription_handlers(bot):
    """Registra todos os handlers relacionados a assinaturas."""

    @bot.message_handler(commands=['planos'])
    def handle_show_plans(message):
        """
        Exibe os planos de assinatura ativos para o usuário.
        """
        chat_id = message.chat.id
        print(f"DEBUG: Comando /planos recebido do chat {chat_id}")
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM subscription_plans WHERE is_active = TRUE ORDER BY price ASC")
                plans = cur.fetchall()

            if not plans:
                bot.send_message(chat_id, "😕 Nenhum plano de assinatura disponível no momento.")
                return

            bot.send_message(chat_id, "✨ Conheça nossos planos de assinatura:")
            
            for plan in plans:
                # Monta a descrição do plano
                plan_description = (
                    f"*{plan['name']}*\n"
                    f"_{plan['description'] or 'Acesso exclusivo.'}_\n\n"
                    f"💰 *Preço:* R$ {plan['price']:.2f}\n"
                    f"🔄 *Recorrência:* a cada {plan['frequency']} "
                    f"{'Mês' if plan['frequency_type'] == 'months' else 'Dia'}"
                    f"{'es' if plan['frequency'] > 1 and plan['frequency_type'] == 'months' else 's' if plan['frequency'] > 1 else ''}"
                )
                
                # Cria o botão de assinatura
                markup = types.InlineKeyboardMarkup()
                # O callback_data conterá o prefixo 'subscribe_' e o ID do plano
                subscribe_button = types.InlineKeyboardButton("Assinar Agora", callback_data=f"subscribe_{plan['id']}")
                markup.add(subscribe_button)
                
                bot.send_message(chat_id, plan_description, reply_markup=markup, parse_mode='Markdown')

        except Exception as e:
            print(f"ERRO ao mostrar planos: {e}")
            traceback.print_exc()
            bot.send_message(chat_id, "Ocorreu um erro ao buscar os planos. Tente novamente mais tarde.")
        finally:
            if conn:
                conn.close()

    @bot.callback_query_handler(func=lambda call: call.data.startswith('subscribe_'))
    def handle_subscribe_callback(call):
        """
        Processa o clique no botão 'Assinar Agora'.
        """
        chat_id = call.message.chat.id
        user = call.from_user
        plan_id = int(call.data.split('_')[1])
        
        bot.answer_callback_query(call.id, "Gerando seu link de assinatura...")
        print(f"DEBUG: Usuário {user.id} tentando assinar o plano {plan_id}")

        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM subscription_plans WHERE id = %s AND is_active = TRUE", (plan_id,))
                plan = cur.fetchone()

            if not plan:
                bot.send_message(chat_id, "Este plano não está mais disponível.")
                return

            # Gera o link de assinatura no Mercado Pago
            subscription_link_data = pagamentos.criar_link_de_assinatura(plan, user)

            if subscription_link_data and 'init_point' in subscription_link_data:
                subscription_link = subscription_link_data['init_point']
                message_text = (
                    f"✅ Ótima escolha!\n\n"
                    f"Para ativar sua assinatura do plano *{plan['name']}*, "
                    f"clique no botão abaixo e finalize o pagamento. Você será cobrado(a) "
                    f"recorrentemente no valor de R$ {plan['price']:.2f}."
                )
                markup = types.InlineKeyboardMarkup()
                link_button = types.InlineKeyboardButton("Pagar Assinatura", url=subscription_link)
                markup.add(link_button)
                bot.send_message(chat_id, message_text, reply_markup=markup, parse_mode='Markdown')
            else:
                bot.send_message(chat_id, "😕 Desculpe, não foi possível gerar o seu link de assinatura no momento. Tente novamente.")
                print(f"ERRO: Falha ao obter link de assinatura do MP. Resposta: {subscription_link_data}")

        except Exception as e:
            print(f"ERRO no callback de assinatura: {e}")
            traceback.print_exc()
            bot.send_message(chat_id, "Ocorreu um erro inesperado. Nossa equipe já foi notificada.")
        finally:
            if conn:
                conn.close()

