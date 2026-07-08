import os
import json
import logging
from flask import Flask, request, jsonify
from openai import OpenAI
import requests

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UAZAPI_URL = os.environ.get("UAZAPI_URL")
UAZAPI_TOKEN = os.environ.get("UAZAPI_TOKEN")
UAZAPI_INSTANCE = os.environ.get("UAZAPI_INSTANCE")

SYSTEM_PROMPT = """Você é a Isabela, recepcionista virtual da clínica Especialidades Odontológicas Dr. Thiago Canuto. Você atende pelo WhatsApp central da clínica.

## CLÍNICAS E CONTATOS

- Clínica Bom Jesus → WhatsApp: 5538999720229
- Clínica Largo Dom João → WhatsApp: 5538997234680
- Clínica Palha → WhatsApp: 5538998089805
- Clínica Rio Grande → WhatsApp: 5538998096248

## EQUIPE E ESPECIALIDADES

- Dra. Luisa Braga → Prótese Dentária e Bichectomia
- Dra. Priscila Mourão → Odontopediatria e Clareamento Dental
- Dr. Thiago Canuto → Ortodontia e Lipo de Papada
- Dr. Rafael Souza → Endodontia (Tratamento de Canal)

## FLUXO DE ATENDIMENTO

### 1. BOAS-VINDAS
Cumprimente o paciente de acordo com o horário (bom dia, boa tarde, boa noite), apresente-se e pergunte em que pode ajudar.

Exemplo: "Bom dia! 😊 Eu sou a Isabela, recepcionista virtual da clínica Especialidades Odontológicas Dr. Thiago Canuto. Em que posso te ajudar hoje?"

### 2. IDENTIFICAR A NECESSIDADE
Ouça o que o paciente precisa e identifique a especialidade. Com base nisso, indique o profissional mais adequado.

### 3. PERGUNTAR A CLÍNICA
Após entender a necessidade, pergunte qual unidade é mais conveniente para o paciente:

"Ótimo! Para encaminhar você ao profissional certo, qual das nossas unidades fica mais perto de você?

1️⃣ Clínica Bom Jesus
2️⃣ Clínica Largo Dom João
3️⃣ Clínica Palha
4️⃣ Clínica Rio Grande"

### 4. TRANSFERIR PARA A SECRETÁRIA
Informe que vai transferir para a secretária da unidade escolhida para realizar o agendamento.
Use exatamente este formato na sua resposta para indicar a transferência (o sistema vai processar):
TRANSFERIR:[numero_whatsapp]

Números para transferência:
- Bom Jesus: TRANSFERIR:5538999720229
- Largo Dom João: TRANSFERIR:5538997234680
- Palha: TRANSFERIR:5538998089805
- Rio Grande: TRANSFERIR:5538998096248

Depois de indicar a transferência, envie esta mensagem ao paciente:
"Perfeito! Vou te transferir agora para a secretária da Clínica [nome da clínica] para realizar o seu agendamento. Em instantes ela entrará em contato com você! 😊🦷"

## REGRAS
- Seja simpática e acolhedora
- Use emojis com moderação
- Faça UMA pergunta por vez
- Se receber áudio ou imagem, responda: Olá! No momento só consigo receber mensagens de texto. Pode me escrever? 😊
- Nunca invente preços, horários ou disponibilidade
- O agendamento é feito pela secretária — não tente agendar você mesmo"""

historico = {}

def extrair_texto_puro(valor):
    if not valor:
        return ""
    if isinstance(valor, str):
        return valor.strip()
    if isinstance(valor, dict):
        if "text" in valor:
            return str(valor["text"]).strip()
        for campo in ("body", "caption", "conversation"):
            if campo in valor:
                return str(valor[campo]).strip()
    return str(valor).strip()

def sanitizar_historico(msgs):
    resultado = []
    for m in msgs:
        content = m.get("content", "")
        resultado.append({"role": m["role"], "content": extrair_texto_puro(content) or ""})
    return resultado

def obter_resposta_openai(telefone, mensagem_usuario):
    try:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        if telefone not in historico:
            historico[telefone] = []
        historico[telefone].append({"role": "user", "content": str(mensagem_usuario)})
        msgs_limpas = sanitizar_historico(historico[telefone])
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + msgs_limpas
        )
        resposta = response.choices[0].message.content
        historico[telefone].append({"role": "assistant", "content": resposta})
        return resposta
    except Exception as e:
        logger.error(f"Erro OpenAI: {e}")
        return "Desculpe, tive um probleminha. Pode repetir? 😊"

def enviar_mensagem_whatsapp(telefone, mensagem):
    try:
        url = f"{UAZAPI_URL}/send/text"
        headers = {"Content-Type": "application/json", "token": UAZAPI_TOKEN}
        numero_limpo = telefone.replace("+", "").replace(" ", "").replace("-", "").strip()
        payload = {"number": numero_limpo, "text": mensagem, "instance": UAZAPI_INSTANCE}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        logger.info(f"Enviado para {numero_limpo}: {response.status_code}")
    except Exception as e:
        logger.error(f"Erro ao enviar: {e}")

def processar_transferencia(resposta, telefone_paciente):
    if "TRANSFERIR:" not in resposta:
        return resposta

    linhas = resposta.split("\n")
    mensagem_limpa = []
    numero_secretaria = None

    for linha in linhas:
        if linha.strip().startswith("TRANSFERIR:"):
            numero_secretaria = linha.strip().replace("TRANSFERIR:", "").strip()
        else:
            mensagem_limpa.append(linha)

    if numero_secretaria:
        aviso = (
            f"📋 *Nova solicitação de agendamento*\n\n"
            f"Paciente: {telefone_paciente}\n"
            f"O paciente foi informado que a secretária entrará em contato para realizar o agendamento."
        )
        enviar_mensagem_whatsapp(numero_secretaria, aviso)
        logger.info(f"Secretária notificada: {numero_secretaria}")

    return "\n".join(mensagem_limpa).strip()

def limpar_numero(n):
    return str(n or "").replace("@s.whatsapp.net", "").replace("@c.us", "").replace("+", "").replace(" ", "").replace("-", "").strip()

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Agente Isabela online 🦷"})

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        logger.info(f"Webhook RAW: {json.dumps(data, ensure_ascii=False)[:1000]}")

        if data.get("fromMe") is True or data.get("wasSentByApi") is True:
            return jsonify({"status": "ignorado"}), 200

        owner = limpar_numero(data.get("owner") or "")

        candidatos = [
            data.get("phone"),
            data.get("sender"),
            data.get("sender_pn"),
            data.get("from"),
            (data.get("key") or {}).get("remoteJid"),
            (data.get("key") or {}).get("participant"),
            (data.get("chat") or {}).get("phone"),
            (data.get("contact") or {}).get("phone"),
            (data.get("contact") or {}).get("id"),
        ]

        telefone = ""
        for c in candidatos:
            n = limpar_numero(c)
            if n and n != owner and n.isdigit() and len(n) >= 10:
                telefone = n
                break

        if not telefone:
            chat_id = limpar_numero((data.get("chat") or {}).get("id") or "")
            if chat_id.isdigit() and len(chat_id) >= 10 and chat_id != owner:
                telefone = chat_id

        logger.info(f"owner={owner} | telefone={telefone}")

        if not telefone:
            return jsonify({"status": "ignorado"}), 200

        texto_raw = (
            data.get("text") or
            data.get("body") or
            (data.get("message") or {}).get("content") or
            (data.get("message") or {}).get("conversation") or
            ""
        )
        texto = extrair_texto_puro(texto_raw)
        tipo = (data.get("messageType") or data.get("type") or "").lower()

        logger.info(f"tel={telefone} | txt={texto} | tipo={tipo}")

        if not texto:
            if tipo not in ("conversation", "text", "extendedtextmessage"):
                enviar_mensagem_whatsapp(telefone, "Olá! No momento só consigo receber mensagens de texto. Pode me escrever? 😊")
            return jsonify({"status": "ok"}), 200

        resposta = obter_resposta_openai(telefone, texto)
        resposta_final = processar_transferencia(resposta, telefone)
        logger.info(f"Resposta: {resposta_final[:100]}")
        enviar_mensagem_whatsapp(telefone, resposta_final)
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logger.error(f"Erro webhook: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
