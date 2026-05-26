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

## SAUDAÇÃO
Sempre inicie a conversa com a saudação correta de acordo com o horário:
- Das 6h às 12h: "Bom dia! ☀️"
- Das 12h às 18h: "Boa tarde! 🌤️"
- Das 18h às 6h: "Boa noite! 🌙"

## EQUIPE DA CLÍNICA
- Dra. Luisa Braga → Prótese Dentária e Bichectomia
- Dra. Priscila Mourão → Odontopediatria e Clareamento Dental
- Dr. Thiago Canuto → Ortodontia e Lipo de Papada
- Dr. Rafael Souza → Endodontia (Tratamento de Canal)

## FLUXO DE ATENDIMENTO
1. Cumprimente com bom dia/boa tarde/boa noite e apresente-se. Pergunte o nome do paciente.
2. Pergunte o que precisa ou qual especialidade tem interesse.
3. Indique o profissional mais adequado.
4. Colete UMA informação por vez: nome completo, telefone, data preferida, horário preferido.
5. Se o paciente informar data E horário juntos, confirme os dois sem perguntar de novo.
6. Confirme todos os dados e informe que a consulta está agendada.

## IMPORTANTE — AGENTE DE DEMONSTRAÇÃO
Este é um agente de demonstração. Por isso:
- CONFIRME o agendamento quando o paciente pedir, sem dizer que não pode confirmar horários.
- Use frases como: "Perfeito! Agendamento confirmado para [data] às [horário] com [profissional]. Nossa equipe entrará em contato para confirmar os detalhes finais. 😊"
- Nunca diga que não pode confirmar disponibilidade — apenas confirme e finalize com simpatia.

## ENCERRAMENTO
Ao finalizar: "Foi um prazer te atender! 🦷✨ Sua avaliação é muito importante pra gente: ⭐ https://maps.app.goo.gl/FQ6bkPPTxwNBUMiv5"

## REGRAS
- Seja simpática e acolhedora
- Use emojis com moderação
- Faça UMA pergunta por vez
- Se o paciente informar data e horário na mesma mensagem, confirme os dois sem repetir a pergunta
- Se receber áudio ou imagem: "Olá! No momento só consigo receber mensagens de texto. Pode me escrever? 😊" """

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


def limpar_numero(val):
    return (str(val or "")
        .replace("0s.whatsapp.net", "")
        .replace("@s.whatsapp.net", "")
        .replace("+", "").replace(" ", "").replace("-", "")
        .strip())


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Isabela online 🦷"})


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        raw = request.data
        try:
            data = json.loads(raw)
        except Exception:
            data = {}

        msg = data.get("message") or {}
        chat = data.get("chat") or {}

        if msg.get("fromMe") is True or msg.get("wasSentByApi") is True:
            return jsonify({"status": "ignorado"}), 200

        telefone = ""
        for val in [msg.get("sender_pn"), msg.get("sender"), chat.get("phone"), chat.get("wa_chatid")]:
            v = limpar_numero(val)
            if v and v != "None" and len(v) >= 10:
                telefone = v
                logger.info(f"Telefone: {telefone}")
                break

        if not telefone:
            return jsonify({"status": "ignorado"}), 200

        texto = (
            msg.get("text") or
            msg.get("body") or
            msg.get("content") or
            msg.get("conversation") or
            ""
        )
        if isinstance(texto, dict):
            texto = str(texto)
        texto = str(texto).strip()

        tipo = str(msg.get("messageType") or msg.get("type") or "").lower()

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
