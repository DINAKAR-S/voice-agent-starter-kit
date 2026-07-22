#!/usr/bin/env bash
# ==============================================================================
# vps_setup.sh — one-shot, idempotent bootstrap for a fresh Ubuntu 22.04 VPS.
# ------------------------------------------------------------------------------
# Illustrative — READ IT before running and edit the paths/ports for your setup.
# Safe to run more than once; each step checks before it acts.
#
#   ssh root@<your-vps-ip>
#   # copy this repo to /opt/voice-agent (rsync/git), then:
#   sudo bash /opt/voice-agent/deploy/vps_setup.sh
# ==============================================================================
set -euo pipefail

APP_DIR="/opt/voice-agent"
PY="python3.11"

say() { echo -e "\n\033[1;36m==>\033[0m $*"; }

# --- 1. System packages -------------------------------------------------------
say "Updating apt and installing base packages…"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
  ca-certificates curl gnupg ufw rsync git \
  "${PY}" "${PY}-venv" "${PY}-dev"

# --- 2. Docker + compose plugin (skip if already present) --------------------
if ! command -v docker >/dev/null 2>&1; then
  say "Installing Docker Engine + compose plugin…"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
else
  say "Docker already installed — skipping."
fi
systemctl enable --now docker

# --- 3. Firewall --------------------------------------------------------------
# Open exactly the ports the stack needs. LiveKit media + SIP use big UDP ranges.
say "Configuring UFW firewall…"
ufw allow 22/tcp                 comment 'SSH'
ufw allow 80/tcp                 comment 'HTTP (Traefik / ACME challenge)'
ufw allow 443/tcp                comment 'HTTPS (Traefik: dashboard + n8n)'
ufw allow 7881/tcp               comment 'LiveKit RTC TCP fallback'
ufw allow 50000:60000/udp        comment 'LiveKit WebRTC media'
ufw allow 5060/udp               comment 'SIP signalling (Vobiz INVITE)'
ufw allow 10000:20000/udp        comment 'SIP RTP media'
# NOTE: 7880 (signalling WS) stays CLOSED to the internet — localhost only.
ufw --force enable
ufw status verbose

# --- 4. App dir + Python venv -------------------------------------------------
say "Setting up ${APP_DIR}…"
mkdir -p "${APP_DIR}/recordings" "${APP_DIR}/transcripts"

if [ ! -d "${APP_DIR}/.venv" ]; then
  say "Creating virtualenv…"
  "${PY}" -m venv "${APP_DIR}/.venv"
fi
say "Installing Python dependencies…"
"${APP_DIR}/.venv/bin/pip" install --upgrade pip
if [ -f "${APP_DIR}/requirements.txt" ]; then
  "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"
else
  echo "  (no requirements.txt yet — copy the repo into ${APP_DIR} first)"
fi

# --- 5. .env reminder ---------------------------------------------------------
if [ ! -f "${APP_DIR}/.env" ]; then
  say "No .env found — copying the example. EDIT IT before starting the service."
  [ -f "${APP_DIR}/.env.example" ] && cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
fi

# --- 6. systemd service -------------------------------------------------------
say "Installing + enabling the voice-agent systemd service…"
if [ -f "${APP_DIR}/deploy/voice-agent.service" ]; then
  cp "${APP_DIR}/deploy/voice-agent.service" /etc/systemd/system/voice-agent.service
  systemctl daemon-reload
  systemctl enable voice-agent
  echo "  Start it once your .env is filled in:  systemctl start voice-agent"
fi

say "Done. Next: fill in ${APP_DIR}/.env, then 'systemctl start voice-agent'."
say "If self-hosting LiveKit: 'docker compose -f deploy/docker-compose.livekit.yml up -d'."
