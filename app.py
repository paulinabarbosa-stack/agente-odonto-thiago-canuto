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
1. Cumprimente o paciente e pergunte o nome dele.
2. Pergunte o que precisa ou qual especialidade tem interesse.
3. Indique o profissional mais adequado.
4. Colete UMA informação por vez: nome completo, telefone, data preferida, período (manhã/tarde).
5. Confirme os dados e informe que a equipe entrará em contato.
6. Ao finalizar: "Foi um prazer te atender! 🦷✨ Sua avaliação é muito importante: ⭐ https://maps.app.goo.gl/FQ6bkPPTxwNBUMiv5"

## REGRAS
- Seja simpática e acolhedora
- Use emojis com moderação
- Faça UMA pergunta por vez
- Se receber áudio ou imagem: "Olá! No momento só consigo receber mensagens de texto. Pode me escrever? 😊"
- Nunca invente preços, horários ou disponibilidade"""

historico = {}

def obter_resposta_openai(telefone: str, mensagem_usuario: str) -> str:
    try:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        if telefone not in historico:
            historico[telefone] = []

        historico[telefone].append({"role": "user", "content": str(mensagem_usuario)})

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in historico[telefone]:
            messages.append({"role": msg["role"], "content": str(msg["content"])})

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )

        resposta = response.choices[0].message.content
        historico[telefone].append({"role": "assistant", "content": str(resposta)})
        return resposta

    except Exception as e:
        logger.error(f"Erro OpenAI: {e}")
        return "Desculpe, tive um probleminha. Pode repetir? 😊"


def enviar_mensagem_whatsapp(telefone: str, mensagem: str):
    try:
        url = f"{UAZAPI_URL}/send/text"
        headers = {"Content-Type": "application/json", "token": UAZAPI_TOKEN}
        numero_limpo = telefone.replace("+", "").replace(" ", "").replace("-", "").strip()
        payload = {"number": numero_limpo, "text": mensagem, "instance": UAZAPI_INSTANCE}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        logger.info(f"Enviado para {numero_limpo}: {response.status_code}")
    except Exception as e:
        logger.error(f"Erro ao enviar: {e}")


def extrair_mensagem(data: dict):
    try:
        # Ignora mensagens enviadas pelo bot
        if data.get("fromMe") is True:
            return None, None
        if str(data.get("wasSentByApi", "")).lower() == "true":
            return None, None

        # Pega o número do remetente — prioriza sender_pn que tem o número limpo
        sender_pn = str(data.get("sender_pn", "")).replace("@s.whatsapp.net", "").replace("+", "").replace(" ", "").replace("-", "").strip()
        sender = str(data.get("sender", "")).replace("@s.whatsapp.net", "").replace("+", "").replace(" ", "").replace("-", "").strip()
        phone = str(data.get("phone", "")).replace("+", "").replace(" ", "").replace("-", "").strip()

        # Usa o menor número válido (sender_pn costuma ter o número correto)
        telefone = sender_pn or sender or phone

        if not telefone or telefone == "None":
            return None, None

        # Pega o texto
        texto = (
            data.get("text") or
            data.get("body") or
            (data.get("message") or {}).get("content") or
            (data.get("message") or {}).get("conversation") or
            ""
        )

        # Se texto for objeto, converte para string
        if isinstance(texto, dict):
            texto = str(texto)

        tipo = str(data.get("messageType") or data.get("type") or "").lower()

        if not texto:
            if tipo not in ("conversation", "text", "extendedtextmessage"):
                return telefone, "__MIDIA__"
            return None, None

        return telefone, str(texto)

    except Exception as e:
        logger.error(f"Erro ao extrair: {e}")
        return None, None


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Agente Isabela online 🦷"})


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        logger.info(f"Webhook: fromMe={data.get('fromMe')} | wasSentByApi={data.get('wasSentByApi')} | sender_pn={data.get('sender_pn')} | phone={data.get('phone')}")

        telefone, texto = extrair_mensagem(data)
        logger.info(f"Extraido -> tel: {telefone} | txt: {texto}")

        if not telefone:
            return jsonify({"status": "ignorado"}), 200

        if texto == "__MIDIA__":
            enviar_mensagem_whatsapp(telefone, "Olá! No momento só consigo receber mensagens de texto. Pode me escrever? 😊")
            return jsonify({"status": "ok"}), 200

        if not texto:
            return jsonify({"status": "ignorado"}), 200

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
