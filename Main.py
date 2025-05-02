from telegram import Bot
import asyncio
import openai
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import os

# === CONFIGURAÇÕES ===
TOKEN = os.getenv('TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
openai.api_key = os.getenv('OPENAI_API_KEY')

# === GERADOR DE FRASE COM CHATGPT ===
async def gerar_frase_motivacional():
    try:
        client = openai.AsyncOpenAI(api_key=openai.api_key)
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system","content":"Você é um gerador de frases motivacionais curtas."},
                {"role": "user","content":"Me envie uma frase motivacial simples, curta e positiva."}
            ],
            temperature=0.7,
            max_tokens=60
        )
        frase = response.choices[0].message.content.strip()
        return frase

    except Exception as e:
        print("X Erro ao Gerar Frases: ", e)
        return "Não Desista de Tentar!"

# === ENVIO DA MENSAGEM ===
async def enviar_mensagem():
    bot = Bot(token=TOKEN)
    frase = await gerar_frase_motivacional()
    await bot.send_message(chat_id=CHAT_ID, text=frase)
    print("✅ Frase enviada:", frase)

async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(enviar_mensagem,'cron',hour=8,minute=0)
    scheduler.start()

    print("Bot agendado para enviar todos os dias")

    while True:
        await asyncio.sleep(60)


# === EXECUÇÃO ===
asyncio.run(main())