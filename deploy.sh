#!/usr/bin/env bash
# deploy.sh — full server setup for interview-questions
# Runs everything under the dedicated 'interview' system user.
# Usage: sudo bash deploy.sh
set -euo pipefail

# ── Colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()     { echo -e "${GREEN}  ✔ ${1}${RESET}"; }
info()   { echo -e "${CYAN}  → ${1}${RESET}"; }
warn()   { echo -e "${YELLOW}  ⚠ ${1}${RESET}"; }
die()    { echo -e "${RED}  ✘ ${1}${RESET}"; exit 1; }
header() { echo -e "\n${BOLD}${CYAN}▸ ${1}${RESET}"; }

# run a command as the interview user
as_interview() { sudo -u "$APP_USER" "$@"; }

# ── Hardcoded identity — everything lives under /home/interview ────────────────
APP_USER="interview"
APP_HOME="/home/interview"
APP_DIR="$APP_HOME/interview-questions"
LOG_DIR="$APP_HOME/logs"
VENV="$APP_DIR/venv"
DB="$APP_DIR/interview.db"

# ── Root check ─────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && die "Run as root: sudo bash deploy.sh"

# ── Banner ─────────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   Interview Questions — Deploy Script    ║"
echo "  ║   User: interview  ~${APP_HOME}          ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${RESET}"

# ── Configuration prompts ──────────────────────────────────────────────────────
header "Configuration"

read -rp "  Domain name (e.g. interview.example.com): " DOMAIN
[[ -z "$DOMAIN" ]] && die "Domain name is required."

read -rp "  Gunicorn port [5001]: " APP_PORT
APP_PORT="${APP_PORT:-5001}"

read -rp "  Set up Let's Encrypt SSL? (y/n) [y]: " USE_CERTBOT
USE_CERTBOT="${USE_CERTBOT:-y}"

read -rp "  Git repo URL [https://github.com/geeteq/interview-questions.git]: " REPO_URL
REPO_URL="${REPO_URL:-https://github.com/geeteq/interview-questions.git}"

echo ""
echo -e "${BOLD}  Summary:${RESET}"
echo "    User       : $APP_USER"
echo "    Home       : $APP_HOME"
echo "    App dir    : $APP_DIR"
echo "    Logs       : $LOG_DIR"
echo "    Port       : $APP_PORT"
echo "    Domain     : $DOMAIN"
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

# ── 2 — interview user ─────────────────────────────────────────────────────────
header "2/8 — System user"

if id "$APP_USER" &>/dev/null; then
  info "User '$APP_USER' already exists"
else
  useradd --system --create-home --home-dir "$APP_HOME" \
          --shell /bin/bash "$APP_USER"
  ok "User '$APP_USER' created with home $APP_HOME"
fi

# Ensure home directory exists with correct ownership
mkdir -p "$APP_HOME"
chown "$APP_USER:$APP_USER" "$APP_HOME"
chmod 750 "$APP_HOME"
ok "Home directory: $APP_HOME"

# ── 3 — Code ──────────────────────────────────────────────────────────────────
header "3/8 — App code"

if [[ -d "$APP_DIR/.git" ]]; then
  info "Repo already present — pulling latest…"
  as_interview git -C "$APP_DIR" pull --ff-only
  ok "Code updated"
else
  info "Cloning $REPO_URL → $APP_DIR"
  as_interview git clone "$REPO_URL" "$APP_DIR"
  ok "Code cloned"
fi

# ── 4 — Python virtualenv & dependencies ──────────────────────────────────────
header "4/8 — Python environment"

if [[ ! -d "$VENV" ]]; then
  info "Creating virtualenv at $VENV…"
  as_interview python3 -m venv "$VENV"
  ok "Virtualenv created"
else
  info "Virtualenv exists — skipping creation"
fi

info "Installing Python dependencies…"
as_interview "$VENV/bin/pip" install --quiet --upgrade pip
as_interview "$VENV/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
ok "Dependencies installed"

# ── 5 — Database ───────────────────────────────────────────────────────────────
header "5/8 — Database"

if [[ -f "$DB" ]]; then
  warn "Database already exists at $DB — skipping init (data preserved)"
else
  info "Initialising database…"
  (cd "$APP_DIR" && as_interview "$VENV/bin/python" init_db.py)
  ok "Database initialised with sample questions"
fi

# ── 6 — Logs directory ─────────────────────────────────────────────────────────
header "6/8 — Log directory"

as_interview mkdir -p "$LOG_DIR"
ok "Log directory: $LOG_DIR"

# ── 7 — Systemd service ────────────────────────────────────────────────────────
header "7/8 — Systemd service"

WORKER_COUNT=$(( $(nproc) * 2 + 1 ))
[[ $WORKER_COUNT -gt 9 ]] && WORKER_COUNT=9

cat > /etc/systemd/system/interview-questions.service <<EOF
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

for i in {1..10}; do
  if systemctl is-active --quiet interview-questions; then
    ok "Gunicorn running on 127.0.0.1:${APP_PORT} (${WORKER_COUNT} workers)"
    break
  fi
  sleep 1
  [[ $i -eq 10 ]] && die "Gunicorn failed to start — check: journalctl -u interview-questions -n 30"
done

# ── 8 — Apache ─────────────────────────────────────────────────────────────────
header "8/8 — Apache + SSL"

info "Enabling required Apache modules…"
a2enmod proxy proxy_http headers ssl rewrite -q
ok "Modules enabled"

APACHE_CONF="/etc/apache2/sites-available/interview-questions.conf"
SSL_DIR="/etc/ssl/interview-questions"

if [[ "$USE_CERTBOT" =~ ^[Yy] ]]; then
  # HTTP-only first so certbot can complete its challenge
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
  ok "Apache running (HTTP)"

  info "Requesting Let's Encrypt certificate for ${DOMAIN}…"
  if certbot --apache -d "$DOMAIN" --non-interactive --agree-tos \
       --email "admin@${DOMAIN}" --redirect --quiet; then
    ok "Let's Encrypt certificate issued — HTTPS enabled"
  else
    warn "Certbot could not issue a certificate (is DNS pointing here?)."
    warn "Site is live over HTTP. Re-run when DNS is ready:"
    warn "  certbot --apache -d ${DOMAIN}"
  fi

else
  info "Generating self-signed certificate…"
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

  a2ensite interview-questions.conf -q
  apache2ctl configtest 2>/dev/null || die "Apache config syntax error"
  systemctl reload apache2
  ok "Apache running with self-signed certificate"
fi

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}  ✔ Deployment complete!${RESET}"
echo ""
echo -e "${BOLD}  File layout${RESET}"
echo "    App      : ${APP_DIR}"
echo "    Database : ${DB}"
echo "    Logs     : ${LOG_DIR}"
echo "    Venv     : ${VENV}"
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
echo "    Update   : sudo -u ${APP_USER} git -C ${APP_DIR} pull && systemctl restart interview-questions"
echo "    Shell    : sudo -u ${APP_USER} -s"
echo ""
