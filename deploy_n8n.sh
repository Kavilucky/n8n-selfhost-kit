#!/usr/bin/env bash
# Разворачивает n8n (self-hosted) на чистом Ubuntu/Debian VPS через Docker Compose:
# сам n8n + Postgres + Caddy (автоматический HTTPS по домену через Let's Encrypt).
# Запуск на сервере (от root или через sudo):
#   chmod +x deploy_n8n.sh
#   ./deploy_n8n.sh
set -euo pipefail

echo "=== Развёртывание n8n (Docker Compose) ==="

if [ "$(id -u)" -ne 0 ]; then
  echo "Нужны права root. Запусти: sudo ./deploy_n8n.sh" >&2
  exit 1
fi

read -rp "Домен для n8n (например n8n.example.com, A-запись уже должна указывать на этот сервер): " N8N_DOMAIN
read -rp "Email для Let's Encrypt (уведомления об истечении сертификата): " LE_EMAIL
read -rp "Логин для базовой авторизации n8n [admin]: " N8N_USER
N8N_USER=${N8N_USER:-admin}
read -rsp "Пароль для базовой авторизации n8n: " N8N_PASSWORD
echo
PG_PASSWORD=$(openssl rand -hex 16)
N8N_ENCRYPTION_KEY=$(openssl rand -hex 24)

if [ -z "$N8N_DOMAIN" ] || [ -z "$LE_EMAIL" ] || [ -z "$N8N_PASSWORD" ]; then
  echo "Домен, email и пароль обязательны." >&2
  exit 1
fi

echo "--- Ставлю Docker и Docker Compose plugin (если ещё не стоят) ---"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
if ! docker compose version >/dev/null 2>&1; then
  apt-get update -y && apt-get install -y docker-compose-plugin
fi

INSTALL_DIR="/opt/n8n"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

echo "--- Пишу docker-compose.yml и .env ---"
cat > .env <<EOF
N8N_DOMAIN=${N8N_DOMAIN}
LE_EMAIL=${LE_EMAIL}
N8N_BASIC_AUTH_USER=${N8N_USER}
N8N_BASIC_AUTH_PASSWORD=${N8N_PASSWORD}
POSTGRES_PASSWORD=${PG_PASSWORD}
N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
EOF
chmod 600 .env

cat > docker-compose.yml <<'EOF'
services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: n8n
      POSTGRES_USER: n8n
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U n8n"]
      interval: 5s
      timeout: 5s
      retries: 10

  n8n:
    image: docker.n8n.io/n8nio/n8n:latest
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DB_TYPE: postgresdb
      DB_POSTGRESDB_HOST: postgres
      DB_POSTGRESDB_DATABASE: n8n
      DB_POSTGRESDB_USER: n8n
      DB_POSTGRESDB_PASSWORD: ${POSTGRES_PASSWORD}
      N8N_HOST: ${N8N_DOMAIN}
      N8N_PROTOCOL: https
      N8N_PORT: 5678
      WEBHOOK_URL: https://${N8N_DOMAIN}/
      N8N_BASIC_AUTH_ACTIVE: "true"
      N8N_BASIC_AUTH_USER: ${N8N_BASIC_AUTH_USER}
      N8N_BASIC_AUTH_PASSWORD: ${N8N_BASIC_AUTH_PASSWORD}
      N8N_ENCRYPTION_KEY: ${N8N_ENCRYPTION_KEY}
      GENERIC_TIMEZONE: Europe/Moscow
    volumes:
      - n8n_data:/home/node/.n8n
    expose:
      - "5678"

  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    depends_on:
      - n8n
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config

volumes:
  postgres_data:
  n8n_data:
  caddy_data:
  caddy_config:
EOF

cat > Caddyfile <<EOF
${N8N_DOMAIN} {
    reverse_proxy n8n:5678
    tls ${LE_EMAIL}
}
EOF

echo "--- Поднимаю контейнеры ---"
docker compose up -d

echo
echo "=== Готово ==="
echo "n8n будет доступен на https://${N8N_DOMAIN}/ через 30-60 секунд (выпуск сертификата)."
echo "Логин: ${N8N_USER}"
echo "Пароль: (тот, что ты ввёл)"
echo "Файл .env с ключами лежит в ${INSTALL_DIR}/.env - сохрани его отдельно, это единственная копия."
echo
echo "Полезные команды на сервере:"
echo "  cd ${INSTALL_DIR} && docker compose logs -f n8n   # логи"
echo "  cd ${INSTALL_DIR} && docker compose down           # остановить"
echo "  cd ${INSTALL_DIR} && docker compose pull && docker compose up -d   # обновить n8n"
