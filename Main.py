from telegram import Bot
import asyncio
import openai
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import os
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from pymongo import MongoClient
from fpdf import FPDF
import tempfile
import re
import unicodedata
from asyncio import run_coroutine_threadsafe

# === CONFIGURAÇÕES ===
TOKEN = os.getenv('TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
openai.api_key = os.getenv('OPENAI_API_KEY')
MONGO_URI = os.getenv('MONGO_URI')

# === CONEXAO COM BANCO DE DADOS ===
try:
    client = MongoClient(MONGO_URI)
    db = client["frases_motivacionais"]
    colecao = db["mensagens"]
except Exception as e:
    print("Erro ao conectar ao MongoDB:", e)
    colecao = None

# === FUNÇÃO PARA SALVAR NO BANCO DE DADOS ===
def salvar_frase(frase, modelo):
    if colecao is None:
        print("⚠️ Banco de dados indisponível, não foi possível salvar a frase.")
        return
    documento = {
        "data_hora": datetime.now() - timedelta(hours=3),
        "modelo": modelo,
        "frase": frase
    }
    colecao.insert_one(documento)
    print("💾 Frase salva no banco: ", documento)

# === GERADOR DE FRASE COM CHATGPT ===
async def gerar_frase_motivacional():
    try:
        client = openai.AsyncOpenAI(api_key=openai.api_key)
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um gerador de frases motivacionais curtas."},
                {"role": "user", "content": "Me envie uma frase motivacional simples, curta e positiva."}
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
        [InlineKeyboardButton("Seja Motivado!!!", callback_data="Motivar")],
        [InlineKeyboardButton("📜 Ver Histórico", callback_data="Historico")]
    ]
    reply_markup = InlineKeyboardMarkup(teclado)
    await update.message.reply_text(
        "Seja Motivado!!! - Escolha uma opção abaixo:",
        reply_markup=reply_markup
    )

# === TRATAR O BOTÃO NO TELEGRAM ===
async def tratar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "Motivar":
        frase = await gerar_frase_motivacional()
        await query.message.reply_text(frase)
        salvar_frase(frase, "Botão")

    elif query.data == "Historico":
        if colecao is not None:
            frases = list(colecao.find().sort("data_hora", -1).limit(30))  # últimas 30 frases
            if not frases:
                await query.message.reply_text("Nenhuma frase encontrada no histórico.")
                return
            caminho_pdf = gerar_pdf_frases(frases)
            await query.message.reply_document(document=open(caminho_pdf, "rb"))
        else:
            await query.message.reply_text("Erro: banco de dados não está conectado.")

# === ENVIO DA MENSAGEM AGENDADA ===
async def enviar_mensagem():
    bot = Bot(token=TOKEN)
    frase = await gerar_frase_motivacional()
    await bot.send_message(chat_id=CHAT_ID, text=frase)
    salvar_frase(frase, "Automático")
    print("✅ Frase enviada:", frase)

# === AGENDAR ENVIO DIÁRIO ===
async def agendar_envio_diario(application):
    scheduler = AsyncIOScheduler()
    hour = int(os.getenv("SEND_HOUR", 8))
    minute = int(os.getenv("SEND_MINUTE", 0))
    loop = asyncio.get_event_loop()
    scheduler.add_job(
        lambda: run_coroutine_threadsafe(enviar_mensagem(), loop),
        'cron',
        hour=hour,
        minute=minute
    )
    scheduler.start()
    print("🕗 Envio diário agendado!")

# === REMOVENDO EMOJI DO PDF ===
def remover_emojis(texto):
    texto_sem_emojis = ''.join(
        c for c in texto
        if not unicodedata.category(c).startswith('So')  # Remove somente símbolos gráficos e emojis
    )
    return texto_sem_emojis

# === GERAR PDF DO HISTORICO ===
def gerar_pdf_frases(frases):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial",size=12)
    pdf.cell(200,10,txt="Histórico de Frases Motivacionais", ln=True, align="C")
    pdf.ln(10)

    for frase in frases:
        frase_limpa = remover_emojis(frase['frase'])
        linha = f"{frase['data_hora'].strftime('%d/%m/%Y %H:%M')} - [{frase['modelo']}] {frase_limpa}"
        linha = linha.encode("latin-1", "ignore").decode("latin-1")  # Ignora qualquer caractere não suportado
        pdf.multi_cell(0, 10, linha)
        pdf.ln(2)

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(temp.name)
    return temp.name

# === FUNÇÃO PRINCIPAL ===
def main():
    application = Application.builder().token(TOKEN).post_init(agendar_envio_diario).build()

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder_com_botao))
    application.add_handler(CallbackQueryHandler(tratar_callback))

    print("🤖 Bot rodando com polling + agendamento")
    application.run_polling()

main()
