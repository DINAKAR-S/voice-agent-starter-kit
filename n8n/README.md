# n8n — event ETL for the voice agent

This is the **non-audio** path. It turns Maya's call events into rows in Supabase
and a Telegram ping to the owner when a site visit is booked. It never touches
the live call audio — that all happens in the agent worker.

```
Maya (agent) ──POST──▶ n8n /webhook/voice-events ──▶ Supabase (calls, site_visits) ──▶ Telegram
Vobiz recording ──▶ n8n ──▶ recording_handler (localhost) ──▶ /opt/voice-agent/recordings/<call>.mp3
```

> ⚠️ **Enable HMAC verification before you go to production.** The workflow ships
> with a disabled "Verify HMAC (ENABLE ME)" node at the top. Until you enable it,
> anyone who learns your webhook URL can POST fake events. See step 6.

---

## 1. Bring up n8n

```bash
# Point an A record  n8n.your-vps.example → <your-vps-ip>  first.
# Then edit the placeholders in docker-compose.n8n.yml (DB creds, basic-auth,
# YOUR_LETSENCRYPT_EMAIL) and start it:
docker compose -f docker-compose.n8n.yml up -d
docker compose -f docker-compose.n8n.yml logs -f traefik   # watch the cert issue
```

Open `https://n8n.your-vps.example` and log in with `N8N_BASIC_AUTH_USER` /
`N8N_BASIC_AUTH_PASSWORD`. Traefik gets you a Let's Encrypt cert automatically via
the `le` resolver (HTTP-01 challenge on port 80).

## 2. Import the workflow

In the n8n editor: **⋯ menu → Import from File →** `workflow.voice-events.json`.
It creates the Webhook → Switch → Supabase/OpenAI/Telegram graph, inactive.

## 3. Set the credential placeholders

The imported nodes reference credentials by **placeholder name** — create real
credentials in n8n and select them on each node:

| Node | Credential type | What to put |
|---|---|---|
| Supabase upsert calls / insert site_visits | **Header Auth** | Header `apikey` = `YOUR_SUPABASE_SERVICE_KEY`, plus `Authorization: Bearer YOUR_SUPABASE_SERVICE_KEY` |
| Extract fields (gpt-4o-mini) | **Header Auth** | `Authorization: Bearer YOUR_OPENAI_API_KEY` |
| Telegram: notify owner | **Telegram API** | `YOUR_TELEGRAM_BOT_TOKEN`; set chat id to `YOUR_TELEGRAM_CHAT_ID` on the node |

Also replace the two `YOUR_SUPABASE_URL` strings in the HTTP nodes' URLs with your
project URL.

## 4. Point Vobiz + the agent at the webhooks

- **Event webhook** (agent emits `call.started` / `call.completed` /
  `transcript.ready`): `https://n8n.your-vps.example/webhook/voice-events`
- **Recording webhook** (Vobiz → n8n → localhost handler): configure Vobiz's
  recording callback to hit an n8n webhook that forwards the body to
  `http://127.0.0.1:8099/` with header `X-Rec-Token: YOUR_REC_TOKEN`.

Activate the workflow (top-right toggle) once credentials are set.

## 5. Run the recording handler under systemd

`recording_handler.py` is stdlib-only and binds to `127.0.0.1` (n8n reaches it
locally; nothing else should). Quick smoke test:

```bash
REC_TOKEN=YOUR_REC_TOKEN python3 recording_handler.py --self-check   # asserts SSRF guard
```

Add the allowed Vobiz recording host(s) to `ALLOWED_REC_HOSTS` in the file, then
run it as a service:

```ini
# /etc/systemd/system/voice-agent-rec.service
[Unit]
Description=voice-agent recording handler
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/voice-agent/n8n
EnvironmentFile=/opt/voice-agent/.env
ExecStart=/usr/bin/python3 /opt/voice-agent/n8n/recording_handler.py
Restart=always
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/voice-agent/recordings
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now voice-agent-rec
```

## 6. Enable HMAC verification (production hardening)

1. In n8n, right-click the **Verify HMAC (ENABLE ME)** node → **Enable**.
2. Set an env var on the n8n container: `VOICE_EVENTS_SECRET=<a long random string>`.
3. Have the agent sign each event body with the same secret and send it as the
   `X-Signature` header (HMAC-SHA256 hex of the raw JSON body).

Do not skip this before production.

---

## Supabase table DDL

Run this in the Supabase SQL editor (or any psql) before activating the workflow:

```sql
create table if not exists calls (
  call_id      text primary key,
  did          text,
  caller       text,
  event        text,
  language     text,
  started_at   timestamptz,
  ended_at     timestamptz,
  duration_sec integer,
  updated_at   timestamptz default now()
);

create table if not exists site_visits (
  id         bigint generated always as identity primary key,
  call_id    text references calls(call_id),
  name       text,
  budget     text,
  area       text,
  visit_date text,
  booked     boolean default false,
  created_at timestamptz default now()
);
```

The `calls` upsert relies on `call_id` being the primary key (that is why the HTTP
node sends `Prefer: resolution=merge-duplicates`).
