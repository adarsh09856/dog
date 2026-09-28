# Kodewaves — Sovereign Voice AI Platform

**Kodewaves** is a sovereign voice AI platform designed for building, testing, and deploying conversational AI voice agents with telephony and WebRTC support. It features self-contained master credentials encryption, multi-provider model routing (Indian and global LLM, STT, and TTS engines), sovereign CRM, and turnkey deployment.

---

## 🚀 Quick Start (VPS & aaPanel)

### 1. Installation

Connect to your VPS via SSH as `root` and run:

```bash
# Clone the repository
git clone https://github.com/adarsh09856/dog.git kodewaves
cd kodewaves

# Run the turnkey installer
sudo bash install.sh
```

The installer will:
- Check for host port availability (detecting conflicts with existing host services).
- Configure your domain and generate secure master keys (`.env`).
- Launch PostgreSQL, Redis, MinIO, Backend API, and Next.js UI via Docker Compose.
- Initialize database tables and create your initial Superadmin account.
- Print your Nginx reverse proxy configuration for aaPanel.

### 2. Updating Kodewaves

To deploy future updates and run new database migrations:

```bash
cd kodewaves
sudo bash deploy.sh
```

---

## 🌟 Key Features

### 🎙️ Conversational Voice Engine
- Visual node-based workflow builder with stateful branching, tool calling, and guardrails.
- WebRTC real-time browser audio testing ("Test Agent").
- Support for telephony media streams (Twilio, Plivo, Exotel, Asterisk).

### 🛡️ Sovereign Master Credentials Vault
- AES-256 Fernet encrypted key storage for all platform-wide provider credentials.
- Zero dependencies on third-party cloud licensing servers.
- Admin-controlled Bring-Your-Own-Key (BYOK) toggle per organization.

### 🇮🇳 Multi-Provider AI Model Support
- **LLM**: OpenAI, Anthropic, Groq, Together, Sarvam, Sambanova, Novita, Ollama / vLLM.
- **Speech-to-Text (STT)**: Deepgram, Sarvam AI (Indian languages), Whisper, Speechmatics, Azure.
- **Text-to-Speech (TTS)**: ElevenLabs, Cartesia, Sarvam AI (Bulbul), MiniMax, Azure Speech, Smallest.

### 💼 Integrated Business Suite
- **CRM System**: Lead management, call history, status pipelines, and customer tagging.
- **Calendar & Appointments**: Live slot booking during calls, automated rescheduling, and webhook triggers.
- **Custom Web Widgets**: Embeddable website voice chat widgets with customizable colors and avatars.
- **Interactive Forms**: Structured data collection nodes during calls.
- **Sovereign Token Billing**: Credit package bundles, usage ledger, and quota enforcement.

---

## 📁 Project Architecture

```
kodewaves/
├── api/                  # FastAPI backend application
│   ├── routes/admin/     # Sovereign admin panel API endpoints
│   ├── services/         # Audio processing, pipelines, credentials vault
│   └── db/               # PostgreSQL models & Alembic migrations
├── ui/                   # Next.js 15 frontend application
│   ├── src/app/admin/    # Sovereign Admin Panel dashboard
│   └── src/components/   # Voice agent canvas & workflow nodes
├── pipecat/              # Embedded real-time voice pipeline framework
├── docker-compose.aapanel.yaml # Multi-site production compose
├── install.sh            # Turnkey automated installer
└── deploy.sh             # Fast production update script
```

---

## 🔒 Security & Privacy

- **Data Residency**: All call recordings, audio snippets, and transcripts remain inside your private PostgreSQL and MinIO instances.
- **Encryption at Rest**: Master API provider keys are encrypted using AES-256 (Fernet) before writing to the database.
- **Authentication**: Stateless, local JWT authentication tokens signed with cryptographically secure server secrets.

---

## 📄 License

This software is licensed under the BSD 2-Clause License. See [LICENSE](LICENSE) for details.
