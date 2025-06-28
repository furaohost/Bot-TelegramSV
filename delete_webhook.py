import os
import telebot

# --- ATENÇÃO ---
# Este script serve para remover qualquer configuração de Webhook
# que possa estar ativa no seu bot no servidor do Telegram.
# Rode este script APENAS UMA VEZ para resolver o erro "409 Conflict"
# ou para desativar o webhook antes de mudar para polling (se for o caso).
# ------------------

# Obtém o API_TOKEN das variáveis de ambiente.
# Certifique-se de que esta variável está definida no seu terminal ou .env
API_TOKEN = os.getenv('API_TOKEN')

if not API_TOKEN:
    print("ERRO: A variável de ambiente 'API_TOKEN' não está definida. Não é possível remover o webhook.")
    exit(1)

try:
    # Inicializa o bot com seu token
    bot = telebot.TeleBot(API_TOKEN)

    # Remove o webhook. Isso fará com que o Telegram pare de enviar atualizações para sua URL.
    bot.remove_webhook()

    print("\nWebhook removido com sucesso!")
    print("Agora você pode iniciar seu bot (app.py) novamente, ou configurar um novo webhook/polling.")

except Exception as e:
    print(f"\nOcorreu um erro ao tentar remover o webhook: {e}")
    # import traceback; traceback.exc_info() # Descomente para ver o stack trace completo
