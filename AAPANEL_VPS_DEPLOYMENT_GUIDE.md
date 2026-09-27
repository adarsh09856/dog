# aaPanel VPS Production Deployment Guide: Kodewaves Sovereign Voice AI

This guide explains how to install and host **Kodewaves** on your VPS running **aaPanel** without any port conflicts or manual headaches.

---

## 1. Why aaPanel + Kodewaves is the Perfect Setup

In typical deployments, Docker tries to bind directly to ports `80` and `443`. However, on a VPS with aaPanel:
1. aaPanel's built-in Nginx already manages ports `80` and `443` for all your websites.
2. Our **`docker-compose.aapanel.yaml`** binds:
   - **Frontend UI** to `127.0.0.1:3010`
   - **Backend API** to `127.0.0.1:8000`
   - **MinIO Audio Storage** to `127.0.0.1:9000`
   - **Postgres** to `127.0.0.1:5432`
   - **Redis** to `127.0.0.1:6379`
3. aaPanel manages the **Domain**, **Free Auto-Renewing SSL (Let's Encrypt)**, and **Reverse Proxy** with zero port collisions!

---

## 2. Server Requirements

- **VPS Specifications**:
  - Minimum: 4 GB RAM, 2 vCPUs (e.g. Hostinger KVM 2 / DigitalOcean / Hetzner).
  - Recommended: 8 GB RAM, 4 vCPUs (for handling multiple concurrent voice calls).
- **Operating System**: Ubuntu 20.04 / 22.04 / 24.04 LTS, Debian 11 / 12, or AlmaLinux.
- **Control Panel**: aaPanel installed and running.

---

## 3. Step 1: Open Firewall Ports in aaPanel

Log in to your aaPanel dashboard, navigate to the **Security** tab in the left sidebar, and ensure the following ports are open in the firewall:

| Port | Protocol | Purpose |
| :--- | :--- | :--- |
| **80** | TCP | HTTP / Let's Encrypt Verification |
| **443** | TCP | HTTPS Web Traffic |
| **3478** | UDP & TCP | WebRTC STUN / TURN Server |
| **5349** | UDP & TCP | WebRTC TLS TURN Server |
| **49152:49200** | UDP | WebRTC Audio Media Relays |

*(If your VPS also has an external cloud firewall like AWS Security Groups, Hetzner Firewall, or Hostinger Firewall, open the same ports there).*

---

## 4. Step 2: Clone the Repository to your VPS

Connect to your VPS via SSH as `root`:

```bash
# Navigate to the web directory or /opt
cd /www/wwwroot   # or cd /opt

# Clone the repository
git clone https://github.com/adarsh09856/dog.git kodewaves
cd kodewaves
```

---

## 5. Step 3: Run the Automated Installer (or Manual Config)

### Option A: Turnkey Automated Installer (Recommended)
We provided an automated script `install.sh` that detects Docker, prompts for your domain, generates cryptographic secrets, starts the containers, and runs Alembic migrations:

```bash
chmod +x install.sh deploy.sh
sudo bash install.sh
```

During execution:
1. It prompts you for your domain name (e.g., `voice.yourdomain.com`) and optional Superadmin email/password.
2. It auto-generates secure random credentials for PostgreSQL, Redis, MinIO, JWT, and the **AES-256 Fernet Master Key**, writing them directly to `.env`.
3. It launches the PostgreSQL 17 database container (which auto-initializes the database cluster).
4. It executes Alembic migrations (`python -m alembic upgrade head`) to auto-create all database tables.
5. It auto-creates the Superadmin account and prints your Admin login credentials.

### Option B: Manual Environment Setup (.env)
If you prefer configuring `.env` manually:
```bash
# 1. Copy the production template
cp .env.production.example .env

# 2. Edit domain, admin credentials, and database password in .env
nano .env

# 3. Launch containers (auto-initializes PostgreSQL)
docker compose -f docker-compose.aapanel.yaml up -d --build

# 4. Auto-create database tables via Alembic
docker exec kodewaves_api python -m alembic upgrade head

# 5. Auto-create the Superadmin user account
docker exec kodewaves_api python -m scripts.create_superuser
```

---

## 6. Step 4: Configure aaPanel Website & SSL

Once `install.sh` completes:

1. **Add Website in aaPanel**:
   - Go to **Website** in the aaPanel sidebar.
   - Click **Add Site**.
   - **Domain**: Enter your domain (e.g., `voice.yourdomain.com`).
   - **Database**: Select *None* (Kodewaves manages its own containerized PostgreSQL).
   - **PHP Version**: *Pure Static* (or any default).
   - Click **Submit**.

2. **Enable Free SSL (Let's Encrypt)**:
   - In the Website list, click on your domain name to open **Site Settings**.
   - Click the **SSL** tab on the left.
   - Select **Let's Encrypt**.
   - Check your domain checkbox and click **Apply**.
   - Toggle **Force HTTPS** to ON.

3. **Configure the Reverse Proxy**:
   - In **Site Settings**, click on the **ConfigFile** tab (or **Reverse Proxy** -> **Add reverse proxy**).
   - Add the following location blocks to your Nginx configuration:

```nginx
    # 1. Backend API & Long-Lived WebSockets (Audio Streaming)
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering off;
        client_max_body_size 100M;
    }

    # 2. Sovereign Audio Recordings (MinIO Storage)
    location /voice-audio/ {
        proxy_pass http://127.0.0.1:9000/voice-audio/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        client_max_body_size 100M;
    }

    # 3. Next.js 15 Frontend UI
    location / {
        proxy_pass http://127.0.0.1:3010;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 3600s;
    }
```

4. Click **Save** in aaPanel.

---

## 7. Step 5: Access Your Platform & Superadmin

Open your browser and visit:
- **Application**: `https://voice.yourdomain.com`
- **Sovereign Admin Panel**: `https://voice.yourdomain.com/admin`

The first account registered automatically has full Superadmin access to input master keys, create SaaS plans, and manage users.

---

## 8. Updating the Application in the Future

Whenever you push code updates or improvements, simply log in to your VPS and run:

```bash
cd /www/wwwroot/kodewaves
./deploy.sh
```

This single command pulls the latest git commits, rebuilds modified containers, runs any new database migrations, and restarts services with zero downtime.
