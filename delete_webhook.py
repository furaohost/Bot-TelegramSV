import telebot
import config # Importa seu arquivo de configuração para pegar o token

# ATENÇÃO:
# Este script serve para remover qualquer configuração de Webhook
# que possa estar ativa no seu bot no servidor do Telegram.
# Rode este script APENAS UMA VEZ para resolver o erro "409 Conflict".

try:
    # Inicializa o bot com seu token
    bot = telebot.TeleBot(config.API_TOKEN)

    # Remove o webhook
    bot.remove_webhook()

    print("Webhook removido com sucesso!")
    print("Agora você pode iniciar seu bot.py novamente.")

except Exception as e:
    print(f"Ocorreu um erro ao tentar remover o webhook: {e}")

