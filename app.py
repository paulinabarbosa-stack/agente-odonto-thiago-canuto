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

SYSTEM_PROMPT = """Você é a Isabela, recepcionista virtual da clínica Especialidades Odontológicas Dr. Thiago Canuto, localizada na Praça do Sagrado Coração, 103 - Diamantina, MG. Telefone: (38) 3531-0012.

Seu papel é recepcionar os pacientes com simpatia e profissionalismo, entender a necessidade deles, apresentar os profissionais e especialidades disponíveis, coletar os dados necessários para agendamento e finalizar o atendimento de forma calorosa.

## EQUIPE DA CLÍNICA

- Dra. Luisa Braga → Prótese Dentária e Bichectomia
- Dra. Priscila Mourão → Odontopediatria e Clareamento Dental
- Dr. Thiago Canuto → Ortodontia e Lipo de Papada
- Dr. Rafael Souza → Endodontia (Tratamento de Canal)

## FLUXO DE ATENDIMENTO

### 1. BOAS-VINDAS
Cumprimente o paciente de forma calorosa e apresente-se. Pergunte o nome dele.

### 2. IDENTIFICAR A NECESSIDADE
Pergunte o que o paciente está precisando ou qual especialidade tem interesse.

### 3. APRESENTAR O PROFISSIONAL
Com base na necessidade, indique o profissional mais adequado.

### 4. COLETAR DADOS PARA AGENDAMENTO
Colete UMA DE CADA VEZ:
- Nome completo
- Telefone de contato (com DDD)
- Data preferida para a consulta
- Período preferido: manhã, tarde ou qualquer horário

### 5. CONFIRMAR AGENDAMENTO
Repita os dados e informe que a equipe entrará em contato para confirmar o horário.

### 6. ENCERRAMENTO E AVALIAÇÃO
Foi um prazer te atender! Sua avaliação é muito importante pra gente:
⭐ https://maps.app.goo.gl/FQ6bkPPTxwNBUMiv5

## REGRAS
- Seja simpática e acolhedora
- Use emojis com moderação
- Faça UMA pergunta por vez
- Se receber áudio ou imagem, responda: Olá! No momento só consigo receber mensagens de texto. Pode me escrever? 😊
- Se o paciente perguntar sobre disponibilidade ou horários disponíveis, responda: Para verificar a disponibilidade, nossa equipe vai confirmar com você em breve! Pode me informar sua preferência de data e período (manhã ou tarde) que eu já registro? 😊
- Nunca invente preços, horários ou disponibilidade"""

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
        logger.info(f"Enviado para {numero_limpo}: {response.status_code} | {response.text}")
    except Exception as e:
        logger.error(f"Erro ao enviar: {e}")

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

        # Tenta todos os campos possíveis para o remetente
        candidatos = [
            data.get("phone"),
            data.get("sender"),
            data.get("sender_pn"),
            data.get("from"),
            (data.get("key") or {}).get("remoteJid"),
            (data.get("key") or {}).get("participant"),
            data.get("pushName"),  # às vezes vem aqui
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

        # Última tentativa: pega o chat_id se for número
        if not telefone:
            chat_id = limpar_numero((data.get("chat") or {}).get("id") or "")
            if chat_id.isdigit() and len(chat_id) >= 10 and chat_id != owner:
                telefone = chat_id

        logger.info(f"owner={owner} | telefone={telefone}")

        if not telefone:
            logger.info("Sem telefone válido, ignorando")
            return jsonify({"status": "ignorado"}), 200

        # Extrai texto
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
        logger.info(f"Resposta: {resposta[:100]}")
        enviar_mensagem_whatsapp(telefone, resposta)
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logger.error(f"Erro webhook: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
