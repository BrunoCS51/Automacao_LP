# === BIBLIOTECAS UTILIZADAS ===
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
import unicodedata
from asyncio import run_coroutine_threadsafe
import time


# === CONFIGURAÇÕES DE VARIAVEIS DE AMBIENTE ===
# Captura das variáveis de ambiente necessárias para o funcionamento do bot
TOKEN = os.getenv('TOKEN')                   # Token do bot Telegram
CHAT_ID = os.getenv('CHAT_ID')               # ID do chat onde as mensagens automáticas serão enviadas
openai.api_key = os.getenv('OPENAI_API_KEY') # Chave de API da OpenAI
MONGO_URI = os.getenv('MONGO_URI')           # URI de conexão com o MongoDB


# === CONEXAO COM BANCO DE DADOS ===
# Tenta se conectar ao banco MongoDB utilizando a URI fornecida.
# Caso ocorra erro, a coleção será definida como None para evitar falhas no código.
try:
    client = MongoClient(MONGO_URI)
    db = client["frases_motivacionais"]       # Nome do banco de dados
    colecao = db["mensagens"]                 # Nome da coleção usada para armazenar as frases
except Exception as e:
    print("Erro ao conectar ao MongoDB:", e)
    colecao = None


# === FUNÇÃO PARA SALVAR NO BANCO DE DADOS ===
def salvar_frase(frase, modelo):
    # Verifica se a conexão com o banco foi bem-sucedida
    if colecao is None:
        print("⚠️ Banco de dados indisponível, não foi possível salvar a frase.")
        return
    # Cria um documento com data/hora (ajustada para o fuso de Brasília),
    # o tipo de origem (Automático ou Botão) e a frase gerada
    documento = {
        "data_hora": datetime.now() - timedelta(hours=3),  # Ajuste para UTC-3 - Devido Servidor Railway
        "modelo": modelo,                                  # "Automático" ou "Botão"
        "frase": frase
    }
    # Insere o documento na coleção do MongoDB
    colecao.insert_one(documento)
    print(f"💾 Frase [{modelo}] salva no banco às {documento['data_hora'].strftime('%d/%m/%Y %H:%M')}: {frase}")


# === GERADOR DE FRASE COM CHATGPT  - IA ===
async def gerar_frase_motivacional():
    try:
         # Inicializa o cliente assíncrono da OpenAI com a chave da API
        client = openai.AsyncOpenAI(api_key=openai.api_key)
        
        # Envia uma requisição para o modelo GPT-3.5 com instruções específicas
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",                        # Modelo utilizado
            messages=[
                {"role": "system", "content": "Você é um gerador de frases motivacionais curtas."},
                {"role": "user", "content": "Me envie uma frase motivacional simples, curta e positiva."}
            ],
            temperature=0.7,                              # Grau de criatividade - 0 - Direto 1 - Criatvo 
            max_tokens=60                                 # Limite de palavras/tamanho da resposta
        )
        # Extrai apenas o conteúdo da resposta e remove espaços extras
        frase = response.choices[0].message.content.strip()
        print("✨ Frase gerada com sucesso:", frase)
        return frase
        
    except Exception as e:
        # Em caso de erro na API, exibe mensagem e retorna uma frase padrão
        print("X Erro ao Gerar Frases: ", e)
        return "Não Desista de Tentar!"


# === RESPONDER COM O BOTÃO NO TELEGRAM ===
async def responder_com_botao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Define um teclado com dois botões: um para gerar frase e outro para histórico
    teclado = [
        [InlineKeyboardButton("Seja Motivado!!!", callback_data="Motivar")],
        [InlineKeyboardButton("📜 Ver Histórico", callback_data="Historico")]
    ]

    # Cria a estrutura visual com os botões
    reply_markup = InlineKeyboardMarkup(teclado)

    # Envia uma mensagem de resposta com os botões para o usuário
    await update.message.reply_text(
        "Seja Motivado!!! - Escolha uma opção abaixo:",
        reply_markup=reply_markup
    )
    print("📩 Mensagem recebida - botões exibidos ao usuário.")


# === TRATAR O BOTÃO NO TELEGRAM ===
async def tratar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()     # Confirma para o Telegram que o clique foi processado

    # Se o botão clicado for "Motivar", gera e envia uma nova frase
    if query.data == "Motivar":
        print("🔘 Botão [Motivar] clicado")
        frase = await gerar_frase_motivacional()       # Chama a função da OpenAI
        await query.message.reply_text(frase)          # Responde com a frase gerada
        salvar_frase(frase, "Botão")                   # Salva no banco com origem "Botão"

    # Se o botão clicado for "Histórico", gera um PDF com as últimas frases
    elif query.data == "Historico":
        print("🔘 Botão [Histórico] clicado")
        if colecao is not None:
            # Busca as 30 últimas frases ordenadas pela data mais recente
            frases = list(colecao.find().sort("data_hora", -1).limit(30))
            if not frases:
                await query.message.reply_text("Nenhuma frase encontrada no histórico.")
                return
            # Gera o PDF e envia como documento no chat
            caminho_pdf = gerar_pdf_frases(frases)
            await query.message.reply_document(document=open(caminho_pdf, "rb"))
            print("📄 PDF com histórico enviado com sucesso!")
        else:
            await query.message.reply_text("Erro: banco de dados não está conectado.")
            print("⚠️ Erro: tentativa de acessar o histórico sem banco conectado.")


# === ENVIO DA MENSAGEM AGENDADA ===
async def enviar_mensagem():
    bot = Bot(token=TOKEN)      # Cria uma instância do bot com o token
    frase = await gerar_frase_motivacional()    # Gera uma nova frase via OpenAI
    await bot.send_message(chat_id=CHAT_ID, text=frase)   # Envia a frase ao chat especificado
    salvar_frase(frase, "Automático")    # Salva a frase no banco com o modelo "Automático"
    print("✅ Frase enviada automaticamente:", frase)   # Confirma o envio nos logs


# === AGENDAR ENVIO DIÁRIO ===
async def agendar_envio_diario(application):
    scheduler = AsyncIOScheduler()    # Cria o agendador assíncrono

    # Recupera as variáveis de ambiente com horário e minuto do envio
    hour = int(os.getenv("SEND_HOUR", 8))      # Horário padrão: 8h
    minute = int(os.getenv("SEND_MINUTE", 0))  # Minuto padrão: 0

    # Obtém o loop de eventos atual para agendar a execução assíncrona
    loop = asyncio.get_event_loop()

    # Adiciona o job ao agendador com o horário definido
    scheduler.add_job(
        lambda: run_coroutine_threadsafe(enviar_mensagem(), loop), # Executa a função enviar_mensagem() de forma segura no loop
        'cron',                                                    # Tipo de agendamento diário com hora/minuto fixos
        hour=hour,
        minute=minute
    )
    scheduler.start() # Inicia o agendador
    print("🕗 Envio diário agendado para {:02d}:{:02d}!".format(hour, minute))  # Mostra no log o horário agendado


# === REMOVENDO EMOJI DO PDF ===
def remover_emojis(texto):
    # Remove caracteres gráficos e emojis usando a categoria Unicode "So" (Symbol, Other)
    texto_sem_emojis = ''.join(
        c for c in texto
        if not unicodedata.category(c).startswith('So')
    )
    return texto_sem_emojis # Retorna o texto limpo sem emojis

# === GERAR PDF DO HISTORICO ===
def gerar_pdf_frases(frases):
    # Inicializa o PDF, adiciona uma página e define o cabeçalho com formatação
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, txt="Histórico de Frases Motivacionais", ln=True, align="C")
    pdf.ln(8)
    pdf.set_font("Arial", size=11)

    for i, frase in enumerate(frases):
        # Trata o campo data_hora, aceitando tanto datetime quanto string
        data_raw = frase["data_hora"]
        if isinstance(data_raw, datetime):
            data_formatada = data_raw.strftime('%d/%m/%Y %H:%M')
        elif isinstance(data_raw, str):
            try:
                # Tenta formatar sem microsegundos primeiro
                data_formatada = datetime.fromisoformat(data_raw.split(".")[0]).strftime('%d/%m/%Y %H:%M')
            except:
                data_formatada = data_raw  # Caso falhe a conversão, exibe o original
        else:
            data_formatada = "Data inválida"

        # Remove emojis da frase
        frase_limpa = remover_emojis(frase["frase"])
        
        # Monta a linha no formato: data - [modelo] frase
        linha = f"{data_formatada} - [{frase['modelo']}] {frase_limpa}"

        pdf.multi_cell(0, 10, linha)
        pdf.ln(3)

        # A cada 5 frases, insere uma linha separadora para facilitar a leitura
        if (i + 1) % 5 == 0:
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(3)

    # Cria um arquivo PDF temporário para envio
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(temp.name)
    return temp.name # Retorna o caminho do arquivo gerado

# === FUNÇÃO PRINCIPAL ===
def main():
    time.sleep(20)      # Aguarda 20 segundos para evitar conflito durante o deploy (Railway)

    # Inicializa a aplicação do bot com o token e agenda o envio automático
    application = Application.builder().token(TOKEN).post_init(agendar_envio_diario).build()

    # Adiciona o handler para responder a mensagens de texto (sem comandos)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder_com_botao))

    # Adiciona o handler para tratar os botões clicados no Telegram
    application.add_handler(CallbackQueryHandler(tratar_callback))

    print("🤖 Bot rodando com polling + agendamento")

    # Inicia o polling (escuta contínua por mensagens e interações)
    application.run_polling()

# === EXECUÇÃO ===
# Verifica se este arquivo está sendo executado diretamente
# Se sim, chama a função principal para iniciar o bot
if __name__ == "__main__":
    main()
