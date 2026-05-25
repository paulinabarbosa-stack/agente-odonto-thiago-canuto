import os
import json
import logging
from flask import Flask, request, jsonify
import google.generativeai as genai
import requests

# ─── Configuração ───────────────────────────────────────────────────────────
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

UAZAPI_URL = os.environ.get("UAZAPI_URL")          # Ex: https://sua-instancia.uazapi.com
UAZAPI_TOKEN = os.environ.get("UAZAPI_TOKEN")
UAZAPI_INSTANCE = os.environ.get("UAZAPI_INSTANCE") # Nome da instância

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
Pergunte o que o paciente está precisando ou qual especialidade tem interesse. Se ele não souber, apresente as opções de forma clara e amigável.

### 3. APRESENTAR O PROFISSIONAL
Com base na necessidade, indique o profissional mais adequado e explique brevemente a especialidade.

### 4. COLETAR DADOS PARA AGENDAMENTO
Colete as seguintes informações UMA DE CADA VEZ:
- Nome completo
- Telefone de contato (com DDD)
- Data preferida para a consulta
- Período preferido: manhã, tarde ou qualquer horário

### 5. CONFIRMAR AGENDAMENTO
Repita todos os dados coletados e confirme com o paciente. Informe que a equipe entrará em contato para confirmar o horário exato.

### 6. ENCERRAMENTO E AVALIAÇÃO
Ao finalizar, agradeça e convide para avaliar no Google:
"Foi um prazer te atender, [Nome]! 🦷✨
Caso queira compartilhar sua experiência, sua avaliação é muito importante pra gente:
⭐ https://maps.app.goo.gl/FQ6bkPPTxwNBUMiv5"

## REGRAS IMPORTANTES

- Seja sempre simpática, acolhedora e use linguagem acessível
- Use emojis com moderação
- Faça UMA pergunta por vez
- Se receber áudio ou imagem, responda: "Olá! No momento só consigo receber mensagens de texto por aqui. Pode me escrever o que você precisa? 😊"
- Nunca invente preços, horários ou disponibilidade
- Mantenha o contexto da conversa para não repetir perguntas"""

# ─── Histórico de conversas em memória ──────────────────────────────────────
# Formato: { "numero_telefone": [ {"role": "user/model", "parts": ["texto"]} ] }
historico = {}

# ─── Funções auxiliares ──────────────────────────────────────────────────────

def obter_resposta_gemini(telefone: str, mensagem_usuario: str) -> str:
    """Envia mensagem para o Gemini mantendo histórico da conversa."""
    try:
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=SYSTEM_PROMPT
        )

        # Inicializa histórico se for novo contato
        if telefone not in historico:
            historico[telefone] = []

        # Inicia chat com histórico existente
        chat = model.start_chat(history=historico[telefone])

        # Envia a mensagem
        response = chat.send_message(mensagem_usuario)
        resposta = response.text

        # Atualiza o histórico
        historico[telefone] = chat.history

        return resposta

    except Exception as e:
        logger.error(f"Erro ao chamar Gemini: {e}")
        return "Desculpe, tive um probleminha aqui. Pode repetir sua mensagem? 😊"


def enviar_mensagem_whatsapp(telefone: str, mensagem: str):
    """Envia mensagem de texto via UAZAPI."""
    try:
        url = f"{UAZAPI_URL}/send/text"
        headers = {
            "Content-Type": "application/json",
            "token": UAZAPI_TOKEN
        }
        numero_limpo = telefone.replace("@s.whatsapp.net", "").replace(" ", "").strip()
        payload = {
            "number": numero_limpo,
            "text": mensagem,
            "instance": UAZAPI_INSTANCE
        }
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        logger.info(f"Mensagem enviada para {telefone}: {response.status_code}")
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem WhatsApp: {e}")


def extrair_mensagem(data: dict):
    """Extrai o número e o texto da mensagem recebida pelo webhook da UAZAPI."""
    try:
        # Ignora mensagens enviadas pelo próprio bot
        if data.get("fromMe") or data.get("wasSentByApi"):
            return None, None

        # Telefone: limpa +, espaços e hífens
        telefone_raw = (
            data.get("phone") or
            data.get("sender", "").replace("@s.whatsapp.net", "") or
            data.get("from", "").replace("@s.whatsapp.net", "")
        )
        telefone = telefone_raw.replace("+", "").replace(" ", "").replace("-", "").strip()

        if not telefone:
            return None, None

        # Texto pode vir em vários lugares
        texto = (
            data.get("text") or
            data.get("body") or
            data.get("message", {}).get("content") or
            data.get("message", {}).get("conversation") or
            ""
        )

        # Tipo da mensagem
        tipo = (data.get("messageType") or data.get("type") or "").lower()

        # Se não tem texto, é mídia
        if not texto:
            if tipo not in ("conversation", "text", "extendedtextmessage"):
                return telefone, "__MIDIA__"
            return None, None

        return telefone, texto

    except Exception as e:
        logger.error(f"Erro ao extrair mensagem: {e}")
        return None, None


# ─── Rotas Flask ─────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Agente Isabela online 🦷"})


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        logger.info(f"Webhook recebido: {json.dumps(data, ensure_ascii=False)}")

        telefone, texto = extrair_mensagem(data)

        if not telefone:
            return jsonify({"status": "ignorado"}), 200

        # Mensagem de mídia (áudio, imagem, etc.)
        if texto == "__MIDIA__":
            resposta = "Olá! No momento só consigo receber mensagens de texto por aqui. Pode me escrever o que você precisa? 😊"
            enviar_mensagem_whatsapp(telefone, resposta)
            return jsonify({"status": "ok"}), 200

        if not texto:
            return jsonify({"status": "ignorado"}), 200

        # Gera resposta com Gemini
        resposta = obter_resposta_gemini(telefone, texto)

        # Envia resposta via WhatsApp
        enviar_mensagem_whatsapp(telefone, resposta)

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return jsonify({"error": str(e)}), 500


# ─── Inicialização ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
