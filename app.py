import os
import json
import logging
from flask import Flask, request, jsonify
from openai import OpenAI
import requests

# ─── Configuração ───────────────────────────────────────────────────────────
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UAZAPI_URL = os.environ.get("UAZAPI_URL")
UAZAPI_TOKEN = os.environ.get("UAZAPI_TOKEN")
UAZAPI_INSTANCE = os.environ.get("UAZAPI_INSTANCE")

# ─── Prompt do Agente ────────────────────────────────────────────────────────
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

# ─── Histórico em memória ────────────────────────────────────────────────────
historico = {}

# ─── Funções ─────────────────────────────────────────────────────────────────

def sanitizar_historico(msgs):
    resultado = []
    for m in msgs:
        content = m.get("content", "")
        if isinstance(content, str):
            resultado.append({"role": m["role"], "content": content})
        elif isinstance(content, list):
            texto = " ".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
            resultado.append({"role": m["role"], "content": texto})
        else:
            resultado.append({"role": m["role"], "content": str(content)})
    return resultado


def obter_resposta_openai(telefone: str, mensagem_usuario: str) -> str:
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


def enviar_mensagem_whatsapp(telefone: str, mensagem: str):
    try:
        url = f"{UAZAPI_URL}/send/text"
        headers = {"Content-Type": "application/json", "token": UAZAPI_TOKEN}
        numero_limpo = telefone.replace("+", "").replace(" ", "").replace("-", "").strip()
        payload = {"number": numero_limpo, "text": mensagem, "instance": UAZAPI_INSTANCE}
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        logger.info(f"Enviado para {numero_limpo}: {response.status_code} | {response.text}")
    except Exception as e:
        logger.error(f"Erro ao enviar: {e}")


def extrair_mensagem(data: dict):
    try:
        if data.get("fromMe") is True or data.get("wasSentByApi") is True:
            return None, None

        telefone_raw = (
            data.get("phone") or
            data.get("sender_pn") or
            data.get("sender", "").replace("@s.whatsapp.net", "") or
            data.get("from", "").replace("@s.whatsapp.net", "") or
            data.get("owner", "")
        )
        telefone = telefone_raw.replace("+", "").replace(" ", "").replace("-", "").strip()

        if not telefone:
            return None, None

        texto = (
            data.get("text") or
            data.get("body") or
            (data.get("message") or {}).get("content") or
            (data.get("message") or {}).get("conversation") or
            ""
        )

        # Garante que texto seja sempre string
        if isinstance(texto, dict):
            texto = json.dumps(texto, ensure_ascii=False)
        texto = str(texto).strip() if texto else ""

        tipo = (data.get("messageType") or data.get("type") or "").lower()

        if not texto:
            if tipo not in ("conversation", "text", "extendedtextmessage"):
                return telefone, "__MIDIA__"
            return None, None

        return telefone, texto

    except Exception as e:
        logger.error(f"Erro ao extrair: {e}")
        return None, None


# ─── Rotas ───────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Agente Isabela online 🦷"})


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        logger.info(f"Webhook: {json.dumps(data, ensure_ascii=False)[:500]}")

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
