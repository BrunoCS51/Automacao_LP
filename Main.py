from telegram import Bot
import asyncio
import openai
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import os
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from pymongo import MongoClient

# === CONFIGURAÇÕES ===
TOKEN = os.getenv('TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
openai.api_key = os.getenv('OPENAI_API_KEY')
MONGO_URI = os.getenv("MONGO_URI")

# === CONEXAO COM BANCO DE DADOS ===
client = MongoClient(MONGO_URI)
db = client["frases_motivacionais"]
colecao = db["mensagens"]

# === FUNÇÃO PARA SALVAR NO BANCO DE DADOS ===
def salver_frase(frase,modelo):
    documento = {
        "data_hora": datetime.now(),
        "modelo": modelo,
        "frase": frase
    }
    colecao.insert_one(documento)
    print("Frase salva no banco: ", documento)

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

# === RESPONDER COM O BOTÃO NO TELEGRAM ===
async def responder_com_botao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teclado = [
        [InlineKeyboardButton("Seja Motivado!!!",callback_data="Motivar")]
    ]
    reply_markup = InlineKeyboardMarkup(teclado)
    await update.message.reply_text(
        "Não fique assim, clique abaixo e sinta Motivação.",
        reply_markup=reply_markup
    )

# === TRATAR O BOTÃO NO TELEGRAM ===
async def tratar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    frase = await gerar_frase_motivacional()
    await query.message.reply_text(frase)
    salver_frase(frase,"Botão")

# === ENVIO DA MENSAGEM ===
async def enviar_mensagem():
    bot = Bot(token=TOKEN)
    frase = await gerar_frase_motivacional()
    await bot.send_message(chat_id=CHAT_ID, text=frase)
    salver_frase(frase,"Automático")
    print("✅ Frase enviada:", frase)

async def main():
    scheduler = AsyncIOScheduler()
    hour = int(os.getenv("SEND_HOUR", 8))
    minute = int(os.getenv("SEND_MINUTE", 0))
    scheduler.add_job(enviar_mensagem,'cron',hour=hour, minute=minute)
    scheduler.start()

    # Inicializa o application do Telegram
    application = Application.builder().token(TOKEN).build()

    # Adiciona os handlers para:
    # - Qualquer texto que não é comando → mostrar botão
    # - Clique no botão → gerar frase
    application.add_handler(MessageHandler(filters.TEXT, responder_com_botao))
    application.add_handler(CallbackQueryHandler(tratar_callback))

    # Roda o bot "ouvindo" em background
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    print("Bot agendado para enviar todos os dias")

    while True:
        await asyncio.sleep(60)


# === EXECUÇÃO ===
asyncio.run(main())
