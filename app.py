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

def obter_resposta_openai(telefone, texto):
    try:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        if telefone not in historico:
            historico[telefone] = []
        historico[telefone].append({"role": "user", "content": str(texto)})
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + historico[telefone]
        response = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
        resposta = response.choices[0].message.content
        historico[telefone].append({"role": "assistant", "content": str(resposta)})
        return resposta
    except Exception as e:
        logger.error(f"Erro OpenAI: {e}")
        return "Desculpe, tive um probleminha. Pode repetir? 😊"


def enviar_mensagem_whatsapp(telefone, mensagem):
    try:
        numero = telefone.replace("+","").replace(" ","").replace("-","").strip()
        url = f"{UAZAPI_URL}/send/text"
        headers = {"Content-Type": "application/json", "token": UAZAPI_TOKEN}
        payload = {"number": numero, "text": mensagem, "instance": UAZAPI_INSTANCE}
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        logger.info(f"Enviado para {numero}: {r.status_code}")
    except Exception as e:
        logger.error(f"Erro envio: {e}")


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Isabela online 🦷"})


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        # Lê o body de qualquer formato
        raw = request.data
        logger.info(f"RAW BODY: {raw[:500]}")

        try:
            data = json.loads(raw)
        except Exception:
            data = request.form.to_dict()

        logger.info(f"DATA KEYS: {list(data.keys())}")

        # Ignora mensagens do próprio bot
        if data.get("fromMe") is True or data.get("wasSentByApi") is True:
            logger.info("Ignorado: fromMe ou wasSentByApi")
            return jsonify({"status": "ignorado"}), 200

        # Extrai telefone — tenta vários campos
        telefone = ""
        for campo in ["sender_pn", "phone", "sender", "from"]:
            val = str(data.get(campo) or "")
            # Limpa sufixos do WhatsApp
            val = val.replace("0s.whatsapp.net", "").replace("@s.whatsapp.net", "")
            val = val.replace("+", "").replace(" ", "").replace("-", "").strip()
            if val and val != "None" and len(val) >= 10:
                telefone = val
                logger.info(f"Telefone [{campo}]: {telefone}")
                break

        if not telefone:
            logger.info(f"Sem telefone. Campos: phone={data.get('phone')} sender_pn={data.get('sender_pn')} sender={data.get('sender')}")
            return jsonify({"status": "ignorado"}), 200

        # Extrai texto
        texto = (
            data.get("text") or
            data.get("body") or
            (data.get("message") or {}).get("content") or
            (data.get("message") or {}).get("conversation") or
            ""
        )
        if isinstance(texto, dict):
            texto = str(texto)
        texto = str(texto).strip()

        tipo = str(data.get("messageType") or data.get("type") or "").lower()
        logger.info(f"Texto: '{texto}' | Tipo: '{tipo}'")

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
