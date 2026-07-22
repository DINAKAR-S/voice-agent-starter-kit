# 02 · VPS & SSH setup — from a blank box to a ready host

This guide takes a freshly ordered Ubuntu VPS and turns it into a hardened host
that's ready to run the voice agent. Everything is copy-paste. Replace
`<your-vps-ip>` with your real server IP throughout.

> 🏎️ In a hurry? Everything below is bundled in
> [`deploy/vps_setup.sh`](../deploy/vps_setup.sh) as a one-shot bootstrap. Read
> this page once so you understand what it does, then you can just run the script
> on future boxes.

---

## 0. Prerequisites

- A Hostinger VPS on **Ubuntu 22.04 LTS** (see
  [`01-procurement.md`](01-procurement.md)).
- Its IP address and the root password.
- A terminal on your laptop (macOS/Linux Terminal, or Windows PowerShell / WSL).

---

## 1. First login as root

```bash
ssh root@<your-vps-ip>
```

Accept the host fingerprint and enter your root password. Then update the system:

```bash
apt update && apt upgrade -y
```

---

## 2. Create a non-root user

Running everything as root is asking for trouble. Create a normal user with sudo.

```bash
adduser deploy                 # set a strong password when prompted
usermod -aG sudo deploy
```

Copy your SSH key over so you can log in as `deploy` without a password
(run this **from your laptop**, in a new terminal):

```bash
ssh-copy-id deploy@<your-vps-ip>
```

Now log in as the new user and confirm sudo works:

```bash
ssh deploy@<your-vps-ip>
sudo whoami                    # should print: root
```

> ⚠️ Once key login for `deploy` works, consider disabling root SSH and password
> auth in `/etc/ssh/sshd_config` (`PermitRootLogin no`, `PasswordAuthentication
> no`), then `sudo systemctl restart ssh`. Do this only after you've confirmed you
> can log back in as `deploy` — otherwise you can lock yourself out.

---

## 3. Firewall — open exactly the right ports

The voice agent needs SIP signalling and a wide RTP media range. Open these and
nothing more.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing

sudo ufw allow 22/tcp                 # SSH
sudo ufw allow 80/tcp                 # HTTP (Let's Encrypt / Traefik)
sudo ufw allow 443/tcp                # HTTPS (dashboard, n8n)
sudo ufw allow 5060/udp               # SIP signalling
sudo ufw allow 10000:20000/udp        # RTP media (SIP audio)
sudo ufw allow 50000:60000/udp        # LiveKit WebRTC media
sudo ufw allow 7881/tcp               # LiveKit RTC/TCP fallback

sudo ufw enable
sudo ufw status verbose
```

| Port | Proto | Why |
|---|---|---|
| 22 | tcp | SSH |
| 80 | tcp | HTTP → Let's Encrypt challenge / Traefik |
| 443 | tcp | HTTPS for dashboard + n8n |
| 5060 | udp | SIP signalling (INVITE etc.) |
| 10000–20000 | udp | RTP media (the actual call audio) |
| 50000–60000 | udp | LiveKit WebRTC media |
| 7881 | tcp | LiveKit RTC TCP fallback |

> ⚠️ If you self-host LiveKit and audio connects but you hear **silence**, it is
> almost always a blocked UDP media range. Double-check `10000:20000/udp` and
> `50000:60000/udp` are open on the VPS firewall **and** in any provider-level
> firewall Hostinger gives you.

---

## 4. Install Docker + docker-compose

n8n, Traefik, and (optionally) self-hosted LiveKit run in Docker.

```bash
# Docker engine (official convenience script)
curl -fsSL https://get.docker.com | sudo sh

# Let 'deploy' use docker without sudo
sudo usermod -aG docker deploy
# log out and back in for the group to take effect, then:
docker --version

# docker compose plugin
sudo apt install -y docker-compose-plugin
docker compose version
```

---

## 5. Install Python 3.11 + venv

The agent worker runs on Python 3.11.

```bash
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
python3.11 --version
```

You'll also want build basics and git:

```bash
sudo apt install -y git build-essential ffmpeg
```

(`ffmpeg` helps with recording handling on the VPS.)

---

## 6. Clone the repo to `/opt/voice-agent`

We keep the app under `/opt/voice-agent` — this exact path is referenced by the
`systemd` unit and the docs, so stick to it.

```bash
sudo mkdir -p /opt/voice-agent
sudo chown deploy:deploy /opt/voice-agent
git clone https://github.com/dinakarselvakumar/voice-agent-starter-kit.git /opt/voice-agent
cd /opt/voice-agent
```

---

## 7. Create the virtualenv + install dependencies

```bash
cd /opt/voice-agent
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 8. Configure your environment

```bash
cd /opt/voice-agent
cp .env.example .env
nano .env        # paste in every credential you collected in step 01
```

Fill in **every** value from your credential checklist. The file is the single
source of truth for the whole kit.

> ⚠️ `.env` is git-ignored on purpose. Never commit it. If you ever paste a real
> key into a chat, a commit, or a screenshot — rotate it immediately.

---

## 9. Sanity check

With the venv active and `.env` filled in:

```bash
cd /opt/voice-agent
python agent.py start
```

You should see the worker register with LiveKit and wait for jobs. Leave it
running for now; in production you'll run it under `systemd`
(see [`deploy/voice-agent.service`](../deploy/voice-agent.service) and the deploy
step in the [README quickstart](../README.md#-quickstart)).

Next up → **[03 · Vobiz SIP wiring](03-vobiz-sip.md)** to connect a real phone
number.
