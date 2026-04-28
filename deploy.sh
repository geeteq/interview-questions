#!/usr/bin/env bash
# deploy.sh — RHEL/CentOS server setup for interview-questions
# App runs under the 'interview' user at /home/interview
# Apache reverse-proxies http://SERVER/interview/ → Gunicorn on 127.0.0.1:PORT
# SSL is handled upstream — this script configures HTTP only on the internal endpoint.
#
# Usage:
#   sudo bash deploy.sh                # update code, keep existing DB
#   sudo bash deploy.sh --init         # init DB with the 5 hard-coded sample questions
#   sudo bash deploy.sh --init-random  # init DB with 15 random questions from src/master.sql
#   sudo bash deploy.sh --master       # init DB with the full master bank from src/master.sql
#
# --init / --init-random / --master only take effect when interview.db does not
# yet exist on the target host (or has no questions). Existing data is never
# overwritten.
set -euo pipefail

INIT_MODE="auto"   # auto | init | init-random | master
while [[ $# -gt 0 ]]; do
  case "$1" in
    --init)         INIT_MODE="init"        ; shift ;;
    --init-random)  INIT_MODE="init-random" ; shift ;;
    --master)       INIT_MODE="master"      ; shift ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *) echo "Unknown flag: $1" >&2 ; exit 2 ;;
  esac
done

# ── Colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()     { echo -e "${GREEN}  ✔ ${1}${RESET}"; }
info()   { echo -e "${CYAN}  → ${1}${RESET}"; }
warn()   { echo -e "${YELLOW}  ⚠ ${1}${RESET}"; }
die()    { echo -e "${RED}  ✘ ${1}${RESET}"; exit 1; }
header() { echo -e "\n${BOLD}${CYAN}▸ ${1}${RESET}"; }

# Pass proxy env vars explicitly — sudo strips them by default.
as_interview() {
  if [[ -n "${HTTPS_PROXY:-}" ]]; then
    sudo -u "$APP_USER" env \
      https_proxy="$HTTPS_PROXY" \
      HTTPS_PROXY="$HTTPS_PROXY" \
      http_proxy="${HTTP_PROXY:-$HTTPS_PROXY}" \
      HTTP_PROXY="${HTTP_PROXY:-$HTTPS_PROXY}" \
      no_proxy="${NO_PROXY:-localhost,127.0.0.1,::1}" \
      NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,::1}" \
      "$@"
  else
    sudo -u "$APP_USER" "$@"
  fi
}

# Resolve the directory that contains this script — source of truth for the code
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Fixed identity ─────────────────────────────────────────────────────────────
APP_USER="interview"
APP_HOME="/home/interview"
APP_DIR="$APP_HOME/interview-questions"
APP_CODE="$APP_DIR/app"
DB_DIR="$APP_DIR/db"
LOG_DIR="$APP_HOME/logs"
VENV="$APP_DIR/venv"
DB="$DB_DIR/interview.db"

# ── Root check ─────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && die "Run as root: sudo bash deploy.sh"

# ── Detect package manager ─────────────────────────────────────────────────────
if command -v dnf &>/dev/null; then
  PKG="dnf"
elif command -v yum &>/dev/null; then
  PKG="yum"
else
  die "Neither dnf nor yum found — is this a RHEL/CentOS system?"
fi
info "Package manager: $PKG"

# ── Banner ─────────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   Interview Questions — Deploy (RHEL)    ║"
echo "  ║   User: interview  ~${APP_HOME}          ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${RESET}"

# ── Configuration prompts ──────────────────────────────────────────────────────
header "Configuration"

read -rp "  Sub-path for the app [/interview]: " APP_SUBPATH
APP_SUBPATH="${APP_SUBPATH:-/interview}"
APP_SUBPATH="/${APP_SUBPATH#/}"          # ensure leading slash, strip trailing
APP_SUBPATH="${APP_SUBPATH%/}"

read -rp "  Gunicorn port [5002]: " APP_PORT
APP_PORT="${APP_PORT:-5002}"

read -rp "  HTTPS proxy (leave blank if not needed): " PROXY_INPUT
if [[ -n "$PROXY_INPUT" ]]; then
  export https_proxy="$PROXY_INPUT"
  export HTTPS_PROXY="$PROXY_INPUT"
  export http_proxy="$PROXY_INPUT"
  export HTTP_PROXY="$PROXY_INPUT"
  export no_proxy="localhost,127.0.0.1,::1"
  export NO_PROXY="localhost,127.0.0.1,::1"
  PROXY_DISPLAY="$PROXY_INPUT"
else
  PROXY_DISPLAY="(none)"
fi

echo ""
echo -e "${BOLD}  Summary${RESET}"
echo "    User       : $APP_USER"
echo "    Home       : $APP_HOME"
echo "    App dir    : $APP_DIR"
echo "    Logs       : $LOG_DIR"
echo "    Port       : $APP_PORT"
echo "    Sub-path   : $APP_SUBPATH"
echo "    Access URL : http://SERVER${APP_SUBPATH}/"
echo "    Source dir : $SCRIPT_DIR"
echo "    HTTPS proxy: $PROXY_DISPLAY"
echo ""
read -rp "  Proceed? (y/n) [y]: " CONFIRM
[[ "${CONFIRM:-y}" =~ ^[Nn] ]] && { echo "Aborted."; exit 0; }

# ── 1 — System packages ────────────────────────────────────────────────────────
header "1/7 — System packages"

pkg_installed() { rpm -q "$1" &>/dev/null; }

PACKAGES=(python3 httpd rsync)
for pkg in "${PACKAGES[@]}"; do
  if pkg_installed "$pkg"; then
    info "$pkg already installed"
  else
    info "Installing $pkg…"
    $PKG install -y -q "$pkg"
    ok "$pkg installed"
  fi
done

# mod_ssl for Apache (provides mod_proxy too on RHEL)
for mod_pkg in mod_ssl; do
  if pkg_installed "$mod_pkg"; then
    info "$mod_pkg already installed"
  else
    info "Installing $mod_pkg…"
    $PKG install -y -q "$mod_pkg"
    ok "$mod_pkg installed"
  fi
done

# python3-venv may be a separate package on some RHEL versions
if ! python3 -m venv --help &>/dev/null 2>&1; then
  info "Installing python3 venv support…"
  $PKG install -y -q python3-virtualenv 2>/dev/null || \
  $PKG install -y -q python3-venv       2>/dev/null || \
  warn "Could not install venv package — will try with base python3"
fi

# ── 2 — interview user ─────────────────────────────────────────────────────────
header "2/7 — System user"

if id "$APP_USER" &>/dev/null; then
  info "User '$APP_USER' already exists"
else
  useradd --system --create-home --home-dir "$APP_HOME" \
          --shell /bin/bash "$APP_USER"
  ok "User '$APP_USER' created"
fi

mkdir -p "$APP_HOME"
chown "$APP_USER:$APP_USER" "$APP_HOME"
chmod 750 "$APP_HOME"
ok "Home: $APP_HOME"


# ── 3 — Code ──────────────────────────────────────────────────────────────────
header "3/7 — App code"

[[ "$SCRIPT_DIR" == "$APP_DIR" ]] && die "Script is already inside $APP_DIR — run it from outside the target directory."

info "Syncing $SCRIPT_DIR → $APP_DIR"
mkdir -p "$APP_DIR"

rsync -a --delete \
  --exclude='.git/' \
  --exclude='venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='*.db' \
  --exclude='*.db-shm' \
  --exclude='*.db-wal' \
  --exclude='src/' \
  "$SCRIPT_DIR/" "$APP_DIR/"

mkdir -p "$DB_DIR"

# The src/ dir holds the master question bank. Only ship master.sql when
# the operator asked for it — and never the xlsx, the master DB, or the
# import scripts.
if [[ "$INIT_MODE" == "master" || "$INIT_MODE" == "init-random" ]]; then
  if [[ -f "$SCRIPT_DIR/src/master.sql" ]]; then
    cp "$SCRIPT_DIR/src/master.sql" "$DB_DIR/master.sql"
    ok "Copied master.sql to $DB_DIR (mode: $INIT_MODE)"
  else
    die "$INIT_MODE requested but $SCRIPT_DIR/src/master.sql is missing — run src/export_master_sql.py first."
  fi
fi

chown -R "$APP_USER:$APP_USER" "$APP_DIR"
ok "Code synced to $APP_CODE, DB dir at $DB_DIR"

# ── 4 — Python environment ─────────────────────────────────────────────────────
header "4/7 — Python environment"

if [[ ! -d "$VENV" ]]; then
  info "Creating virtualenv…"
  as_interview python3 -m venv "$VENV"
  ok "Virtualenv created at $VENV"
else
  info "Virtualenv exists — skipping"
fi

info "Installing Python dependencies…"
as_interview "$VENV/bin/pip" install --quiet --upgrade pip
as_interview "$VENV/bin/pip" install --quiet -r "$APP_CODE/requirements.txt"
ok "Dependencies installed"

# ── 5 — Database ───────────────────────────────────────────────────────────────
header "5/7 — Database"

if [[ -f "$DB" ]]; then
  warn "Database already exists — skipping init (data preserved)"
else
  case "$INIT_MODE" in
    master)
      info "Loading full master question bank from master.sql…"
      (cd "$APP_CODE" && as_interview "$VENV/bin/python" init_db_master.py)
      ok "Database initialised from master bank"
      ;;
    init-random)
      info "Picking 15 random questions from master.sql…"
      (cd "$APP_CODE" && as_interview "$VENV/bin/python" init_db_random.py)
      ok "Database initialised with 15 random questions"
      ;;
    init|auto)
      info "Initialising database with built-in sample questions…"
      (cd "$APP_CODE" && as_interview "$VENV/bin/python" init_db.py)
      ok "Database initialised with sample questions"
      ;;
  esac
fi

as_interview mkdir -p "$LOG_DIR"
ok "Log directory: $LOG_DIR"

# ── 6 — Systemd service ────────────────────────────────────────────────────────
header "6/7 — Systemd service"

WORKER_COUNT=$(( $(nproc) * 2 + 1 ))
[[ $WORKER_COUNT -gt 9 ]] && WORKER_COUNT=9

cat > /etc/systemd/system/interview-questions.service <<EOF
[Unit]
Description=Interview Questions — Gunicorn
After=network.target

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_CODE}
Environment="PATH=${VENV}/bin"
Environment="INTERVIEW_BASE_PATH=${APP_SUBPATH}"
ExecStartPre=${VENV}/bin/python ${APP_CODE}/init_db.py
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
  [[ $i -eq 10 ]] && die "Gunicorn failed to start — run: journalctl -u interview-questions -n 40"
done

# ── 7 — Apache ─────────────────────────────────────────────────────────────────
header "7/7 — Apache reverse proxy"

# On RHEL, mod_proxy is included in httpd — no a2enmod needed.
# Config files in /etc/httpd/conf.d/ are loaded automatically.
APACHE_CONF="/etc/httpd/conf.d/interview-questions.conf"

cat > "$APACHE_CONF" <<EOF
# Interview Questions — reverse proxy at ${APP_SUBPATH}/
# SSL is terminated upstream; this block handles the internal HTTP path only.

ProxyPreserveHost On
RequestHeader set X-Forwarded-Proto "https"

# The Flask app self-mounts under ${APP_SUBPATH} (see config.py BASE_URL),
# so we preserve the path prefix when proxying — do NOT strip it.
ProxyPass        ${APP_SUBPATH}/  http://127.0.0.1:${APP_PORT}${APP_SUBPATH}/
ProxyPassReverse ${APP_SUBPATH}/  http://127.0.0.1:${APP_PORT}${APP_SUBPATH}/

# Trailing-slash redirect so /interview → /interview/
RedirectMatch ^${APP_SUBPATH}$  ${APP_SUBPATH}/
EOF

# SELinux: allow Apache to open network connections (required for mod_proxy on RHEL)
if command -v setsebool &>/dev/null; then
  info "Configuring SELinux: httpd_can_network_connect → on"
  setsebool -P httpd_can_network_connect 1
  ok "SELinux boolean set"
else
  warn "setsebool not found — skipping SELinux config (may not be needed)"
fi

# Validate and reload Apache
if httpd -t 2>/dev/null; then
  ok "Apache config syntax OK"
else
  die "Apache config syntax error — check $APACHE_CONF"
fi

systemctl enable httpd
systemctl restart httpd
ok "Apache restarted"

# ── Firewall ───────────────────────────────────────────────────────────────────
if command -v firewall-cmd &>/dev/null && systemctl is-active --quiet firewalld; then
  info "Opening HTTP (80) and HTTPS (443) in firewalld…"
  firewall-cmd --permanent --add-service=http  --quiet
  firewall-cmd --permanent --add-service=https --quiet
  firewall-cmd --reload --quiet
  ok "Firewall rules updated"
fi

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}  ✔ Deployment complete!${RESET}"
echo ""
echo -e "${BOLD}  File layout${RESET}"
echo "    Project  : ${APP_DIR}"
echo "    App code : ${APP_CODE}"
echo "    Database : ${DB}"
echo "    Logs     : ${LOG_DIR}"
echo "    Venv     : ${VENV}"
echo ""
echo -e "${BOLD}  Endpoints${RESET}"
echo "    Candidate  : http://SERVER${APP_SUBPATH}/"
echo "    Admin      : http://SERVER${APP_SUBPATH}/admin"
echo "    Questions  : http://SERVER${APP_SUBPATH}/admin/questions"
echo "    Sessions   : http://SERVER${APP_SUBPATH}/admin/sessions"
echo ""
echo -e "${BOLD}  Useful commands${RESET}"
echo "    Status   : systemctl status interview-questions"
echo "    Logs     : journalctl -u interview-questions -f"
echo "    App logs : tail -f ${LOG_DIR}/error.log"
echo "    Restart  : systemctl restart interview-questions"
echo "    Update   : sudo bash ${APP_DIR}/deploy.sh"
echo "    Shell    : sudo -u ${APP_USER} -s"
if [[ -n "${HTTPS_PROXY:-}" ]]; then
echo ""
echo -e "${BOLD}  Proxy${RESET}"
echo "    Used for : dnf, pip during this deploy"
echo "    Value    : ${HTTPS_PROXY}"
fi
echo ""
