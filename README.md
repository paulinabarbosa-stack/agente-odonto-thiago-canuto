# 🦷 Agente Isabela — Especialidades Odontológicas Dr. Thiago Canuto

Agente de atendimento via WhatsApp com IA, desenvolvido com Python + Flask + Gemini.

---

## 📁 Estrutura do projeto

```
agente-thiago-canuto/
├── app.py               # Código principal do agente
├── requirements.txt     # Dependências Python
├── Procfile             # Configuração para Railway
├── .env.example         # Exemplo de variáveis de ambiente
└── README.md
```

---

## ⚙️ Variáveis de ambiente (Railway)

Configure no painel do Railway as seguintes variáveis:

| Variável | Descrição |
|---|---|
| `GEMINI_API_KEY` | Chave da API do Google Gemini |
| `UAZAPI_URL` | URL da sua instância UAZAPI |
| `UAZAPI_TOKEN` | Token de autenticação UAZAPI |
| `UAZAPI_INSTANCE` | Nome da instância UAZAPI |

---

## 🚀 Deploy no Railway

1. Suba o projeto para o GitHub
2. Crie um novo projeto no Railway e conecte o repositório
3. Configure as variáveis de ambiente
4. Railway fará o deploy automaticamente

---

## 🔗 Webhook

Após o deploy, configure o webhook na UAZAPI com a URL:

```
https://seu-projeto.up.railway.app/webhook
```

---

## 🦷 Especialidades atendidas

- **Dra. Luisa Braga** → Prótese Dentária e Bichectomia
- **Dra. Priscila Mourão** → Odontopediatria e Clareamento Dental
- **Dr. Thiago Canuto** → Ortodontia e Lipo de Papada
- **Dr. Rafael Souza** → Endodontia (Tratamento de Canal)

---

Desenvolvido por **Inova IA Soluções** 🤖
