#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/auditmem"
REPO_URL="https://github.com/singulAI/auditmem.git"
BRANCH="copilot/auditoria-cobranca-m2m"
SERVICE_NAME="auditoria-m2m"
NGINX_SITE="auditoria.anadm.site"

echo "[1/8] Instalando dependencias do sistema"
apt update
apt install -y python3-venv python3-pip nginx git

echo "[2/8] Preparando diretorio da aplicacao"
if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone -b "$BRANCH" "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" fetch origin
  git -C "$APP_DIR" checkout "$BRANCH"
  git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
fi

echo "[3/8] Criando ambiente virtual"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "[4/8] Aplicando permissao segura"
chown -R www-data:www-data "$APP_DIR"

echo "[5/8] Instalando unit systemd"
cp "$APP_DIR/deploy/systemd/auditoria-m2m.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo "[6/8] Instalando configuracao Nginx isolada"
cp "$APP_DIR/deploy/nginx/auditoria.anadm.site.conf" "/etc/nginx/sites-available/${NGINX_SITE}"
ln -sf "/etc/nginx/sites-available/${NGINX_SITE}" "/etc/nginx/sites-enabled/${NGINX_SITE}"
nginx -t
systemctl reload nginx

echo "[7/8] Validando servico"
systemctl --no-pager --full status "$SERVICE_NAME" | head -n 20
ss -ltnp | grep -E '(:80|:8502)' || true

echo "[8/8] Concluido"
echo "Aplicacao local: http://127.0.0.1:8502"
echo "Dominio: http://auditoria.anadm.site"
echo "Para HTTPS execute: certbot --nginx -d auditoria.anadm.site"
