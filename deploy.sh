#!/usr/bin/env bash
# deploy.sh — full server setup for interview-questions
# Run as root or with sudo: sudo bash deploy.sh
set -euo pipefail

# ── Colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "${GREEN}  ✔ ${1}${RESET}"; }
info() { echo -e "${CYAN}  → ${1}${RESET}"; }
warn() { echo -e "${YELLOW}  ⚠ ${1}${RESET}"; }
die()  { echo -e "${RED}  ✘ ${1}${RESET}"; exit 1; }
header() { echo -e "\n${BOLD}${CYAN}▸ ${1}${RESET}"; }

# ── Root check ─────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && die "Run as root: sudo bash deploy.sh"

# ── Banner ─────────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   Interview Questions — Deploy Script    ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${RESET}"

# ── Configuration prompts ──────────────────────────────────────────────────────
header "Configuration"

read -rp "  Domain name (e.g. interview.example.com): " DOMAIN
[[ -z "$DOMAIN" ]] && die "Domain name is required."

read -rp "  App directory [/var/www/interview-questions]: " APP_DIR
APP_DIR="${APP_DIR:-/var/www/interview-questions}"

read -rp "  Gunicorn port [5001]: " APP_PORT
APP_PORT="${APP_PORT:-5001}"

read -rp "  App user [www-data]: " APP_USER
APP_USER="${APP_USER:-www-data}"

read -rp "  Set up Let's Encrypt SSL? (y/n) [y]: " USE_CERTBOT
USE_CERTBOT="${USE_CERTBOT:-y}"

read -rp "  Git repo URL [https://github.com/geeteq/interview-questions.git]: " REPO_URL
REPO_URL="${REPO_URL:-https://github.com/geeteq/interview-questions.git}"

echo ""
echo -e "${BOLD}  Summary:${RESET}"
echo "    Domain     : $DOMAIN"
echo "    App dir    : $APP_DIR"
echo "    Port       : $APP_PORT"
echo "    User       : $APP_USER"
echo "    SSL        : $USE_CERTBOT"
echo "    Repo       : $REPO_URL"
echo ""
read -rp "  Proceed? (y/n) [y]: " CONFIRM
[[ "${CONFIRM:-y}" =~ ^[Nn] ]] && { echo "Aborted."; exit 0; }

# ── 1 — System packages ────────────────────────────────────────────────────────
header "1/8 — System packages"

apt-get update -qq
PACKAGES=(python3 python3-venv python3-pip apache2 git)
[[ "$USE_CERTBOT" =~ ^[Yy] ]] && PACKAGES+=(certbot python3-certbot-apache)

for pkg in "${PACKAGES[@]}"; do
  if dpkg -s "$pkg" &>/dev/null; then
    info "$pkg already installed"
  else
    info "Installing $pkg…"
    apt-get install -y -qq "$pkg"
    ok "$pkg installed"
  fi
done

# ── 2 — App directory & code ───────────────────────────────────────────────────
header "2/8 — App directory & code"

if [[ -d "$APP_DIR/.git" ]]; then
  info "Repo already exists — pulling latest…"
  git -C "$APP_DIR" pull --ff-only
  ok "Code updated"
else
  info "Cloning $REPO_URL → $APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
  ok "Code cloned"
fi

# ── 3 — Python virtualenv & dependencies ──────────────────────────────────────
header "3/8 — Python environment"

VENV="$APP_DIR/venv"
if [[ ! -d "$VENV" ]]; then
  info "Creating virtualenv…"
  python3 -m venv "$VENV"
  ok "Virtualenv created"
else
  info "Virtualenv exists — skipping creation"
fi

info "Installing Python dependencies…"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
ok "Dependencies installed"

# ── 4 — Database ───────────────────────────────────────────────────────────────
header "4/8 — Database"

DB="$APP_DIR/interview.db"
if [[ -f "$DB" ]]; then
  warn "Database already exists — skipping init (data preserved)"
else
  info "Initialising database…"
  (cd "$APP_DIR" && "$VENV/bin/python" init_db.py)
  ok "Database initialised with sample questions"
fi

# ── 5 — Permissions ────────────────────────────────────────────────────────────
header "5/8 — File permissions"

chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod -R 750 "$APP_DIR"
chmod 640 "$DB" 2>/dev/null || true
ok "Ownership → $APP_USER, permissions set"

# ── 6 — Systemd service ────────────────────────────────────────────────────────
header "6/8 — Systemd service"

LOG_DIR="/var/log/interview-questions"
mkdir -p "$LOG_DIR"
chown "$APP_USER:$APP_USER" "$LOG_DIR"

WORKER_COUNT=$(( $(nproc) * 2 + 1 ))
[[ $WORKER_COUNT -gt 9 ]] && WORKER_COUNT=9   # cap at 9

SERVICE_FILE="/etc/systemd/system/interview-questions.service"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Interview Questions — Gunicorn
After=network.target

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV}/bin"
ExecStartPre=${VENV}/bin/python init_db.py
ExecStart=${VENV}/bin/gunicorn \\
    --workers ${WORKER_COUNT} \\
    --bind 127.0.0.1:${APP_PORT} \\
    --access-logfile ${LOG_DIR}/access.log \\
    --error-logfile  ${LOG_DIR}/error.log \\
    app:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable interview-questions
systemctl restart interview-questions

# Wait up to 8 s for Gunicorn to bind
for i in {1..8}; do
  if systemctl is-active --quiet interview-questions; then
    ok "Gunicorn running on 127.0.0.1:${APP_PORT} (${WORKER_COUNT} workers)"
    break
  fi
  sleep 1
  [[ $i -eq 8 ]] && die "Gunicorn failed to start — check: journalctl -u interview-questions"
done

# ── 7 — Apache ────────────────────────────────────────────────────────────────
header "7/8 — Apache"

info "Enabling required modules…"
a2enmod proxy proxy_http headers ssl rewrite -q
ok "Modules enabled"

APACHE_CONF="/etc/apache2/sites-available/interview-questions.conf"

# Write HTTP-only config first (certbot needs it to issue the cert)
cat > "$APACHE_CONF" <<EOF
<VirtualHost *:80>
    ServerName ${DOMAIN}

    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "http"
    ProxyPass        / http://127.0.0.1:${APP_PORT}/
    ProxyPassReverse / http://127.0.0.1:${APP_PORT}/

    ErrorLog  /var/log/apache2/interview-questions-error.log
    CustomLog /var/log/apache2/interview-questions-access.log combined
</VirtualHost>
EOF

a2ensite interview-questions.conf -q
apache2ctl configtest 2>/dev/null || die "Apache config syntax error"
systemctl reload apache2
ok "Apache configured and reloaded"

# ── 8 — SSL ────────────────────────────────────────────────────────────────────
header "8/8 — SSL"

if [[ "$USE_CERTBOT" =~ ^[Yy] ]]; then
  info "Requesting Let's Encrypt certificate for ${DOMAIN}…"
  if certbot --apache -d "$DOMAIN" --non-interactive --agree-tos \
       --email "admin@${DOMAIN}" --redirect --quiet; then
    ok "SSL certificate issued and Apache updated by certbot"
  else
    warn "Certbot failed (DNS not pointing here yet?). Site is running over HTTP for now."
    warn "Re-run later: certbot --apache -d ${DOMAIN}"
  fi
else
  info "Skipping Let's Encrypt — generating self-signed certificate…"
  SSL_DIR="/etc/ssl/interview-questions"
  mkdir -p "$SSL_DIR"
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$SSL_DIR/server.key" \
    -out    "$SSL_DIR/server.crt" \
    -subj   "/CN=${DOMAIN}" -quiet

  cat > "$APACHE_CONF" <<EOF
<VirtualHost *:80>
    ServerName ${DOMAIN}
    Redirect permanent / https://${DOMAIN}/
</VirtualHost>

<VirtualHost *:443>
    ServerName ${DOMAIN}

    SSLEngine on
    SSLCertificateFile    ${SSL_DIR}/server.crt
    SSLCertificateKeyFile ${SSL_DIR}/server.key

    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto "https"
    ProxyPass        / http://127.0.0.1:${APP_PORT}/
    ProxyPassReverse / http://127.0.0.1:${APP_PORT}/

    ErrorLog  /var/log/apache2/interview-questions-error.log
    CustomLog /var/log/apache2/interview-questions-access.log combined
</VirtualHost>
EOF

  apache2ctl configtest 2>/dev/null || die "Apache config syntax error after SSL update"
  systemctl reload apache2
  ok "Self-signed certificate configured"
fi

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}  ✔ Deployment complete!${RESET}"
echo ""
echo -e "${BOLD}  URLs${RESET}"
echo "    Candidate  : https://${DOMAIN}/"
echo "    Admin      : https://${DOMAIN}/admin"
echo "    Questions  : https://${DOMAIN}/admin/questions"
echo "    Sessions   : https://${DOMAIN}/admin/sessions"
echo ""
echo -e "${BOLD}  Useful commands${RESET}"
echo "    Status   : systemctl status interview-questions"
echo "    Logs     : journalctl -u interview-questions -f"
echo "    App logs : tail -f ${LOG_DIR}/error.log"
echo "    Restart  : systemctl restart interview-questions"
echo "    Update   : git -C ${APP_DIR} pull && systemctl restart interview-questions"
echo ""
