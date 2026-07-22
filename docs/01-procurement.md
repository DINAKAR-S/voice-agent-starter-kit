# 01 · Procurement — get your accounts and credentials

Before you touch a single line of code, you need five accounts (plus two
optional ones). This guide walks you through each, tells you exactly which
credential to copy down, and ends with a checklist you can tick off.

> 💰 **All prices are illustrative, in INR — approx, verify current pricing
> (checked 2026-07).** Signup flows and plan names change; treat every figure
> below as "roughly this much, confirm at checkout."

Keep a scratch note open. By the end you'll have collected every value that goes
into your `.env` file (see [`.env.example`](../.env.example) for the full list).

---

## 1. Vobiz — phone number + SIP trunk

Vobiz is your telephony provider. It gives you a real phone number (a **DID**)
and an inbound **SIP trunk** that forwards calls to LiveKit.

1. Sign up at Vobiz and verify your account (KYC is usually required for Indian
   numbers).
2. **Buy one phone number (DID).** ~₹500 one-time — *approx, verify current
   pricing (checked 2026-07)*.
3. **Recharge your wallet** with ~₹1,000 for call minutes — *approx, verify*.
4. **Enable call recording** on the number (you'll want recordings for the
   dashboard later).
5. From the console, collect:
   - the **DID number** → `VOBIZ_DID`
   - the **SIP domain** → `VOBIZ_SIP_DOMAIN`
   - the **trunk id** → `VOBIZ_TRUNK_ID`
   - the **SIP auth username / password** → `VOBIZ_AUTH_USERNAME`,
     `VOBIZ_AUTH_PASSWORD` (used only for outbound/transfer legs — the inbound
     trunk into LiveKit stays no-auth; more in
     [`03-vobiz-sip.md`](03-vobiz-sip.md)).

> ⚠️ Vobiz often delivers the caller/called number **national / 0-prefixed**
> (e.g. `0XXXXXXXXXX`), not E.164. You'll handle that in the SIP wiring step —
> just note it now.

---

## 2. Sarvam AI — Indian-language STT + TTS

Sarvam provides the speech models tuned for Indian languages: **Saaras** for
speech-to-text and **Bulbul** for text-to-speech.

1. Sign up at **sarvam.ai**.
2. Add **~₹1,000 in credits** — *approx, verify current pricing (checked 2026-07)*.
3. Create an **API key**. The one key covers both STT (Saaras) and TTS (Bulbul).
4. Collect:
   - the **API key** → `SARVAM_API_KEY`
5. The model + voice defaults are already set in `.env.example`
   (`SARVAM_STT_MODEL=saaras:v3`, `SARVAM_TTS_MODEL=bulbul:v3`,
   `SARVAM_TTS_VOICE=simran`) — leave them unless you want a different voice.

---

## 3. OpenAI — the reasoning LLM

1. Create an account at **platform.openai.com**.
2. Add a **few dollars of credit** — `gpt-4.1-mini` is inexpensive — *approx,
   verify current pricing (checked 2026-07)*.
3. Create an **API key**.
4. Collect:
   - the **API key** → `OPENAI_API_KEY`
5. Model defaults are in `.env.example` (`OPENAI_LLM_MODEL=gpt-4.1-mini`,
   `OPENAI_TEMPERATURE=0.3`, `MAX_TOKENS=140`). We chose `gpt-4.1-mini` after a
   bake-off — see [`04-latency.md`](04-latency.md) for why.

---

## 4. LiveKit — realtime media + SIP

You have two paths. **Start with LiveKit Cloud** — it's the easiest way to a
working call. Self-hosting is documented for later if you want everything on your
own box.

### Option A — LiveKit Cloud (recommended to start)

1. Sign up at **livekit.io** and create a project. **Choose the India / Mumbai
   region** for lowest latency.
2. From **Settings → Keys**, collect:
   - the project **URL** (WSS) → `LIVEKIT_URL`
     (looks like `wss://your-project.livekit.cloud`)
   - the **API key** → `LIVEKIT_API_KEY`
   - the **API secret** → `LIVEKIT_API_SECRET`
3. Go to **Telephony → SIP trunks**. You'll find a **"SIP URI" card** — copy that
   host → `SIP_URI` (e.g. `<your-project-id>.sip.livekit.cloud:5060`).

> ⚠️ **Get `SIP_URI` from the "SIP URI" card, NOT from your `LIVEKIT_URL`.** The
> WSS URL and the SIP host are different endpoints. Deriving the SIP host from the
> WSS URL is the single most common reason "the INVITE never arrives." This bites
> everyone once — don't be everyone.

### Option B — Self-host LiveKit

Run `livekit/livekit-server` + `livekit/sip` + `redis` via Docker Compose on the
same VPS. The compose file lives at [`deploy/docker-compose.livekit.yml`](../deploy/docker-compose.livekit.yml),
with server config in [`deploy/livekit.yaml.example`](../deploy/livekit.yaml.example).
You'll still generate an API key/secret and note your server's SIP host. See
[`02-vps-ssh-setup.md`](02-vps-ssh-setup.md) for the ports this needs.

---

## 5. Hostinger VPS — the one box that runs everything

1. Sign up at Hostinger and order a **VPS** on roughly the **KVM 2** plan
   (~2 vCPU / 8 GB RAM) — ~₹2,500/mo — *approx, verify current pricing
   (checked 2026-07)*.
2. Choose **Ubuntu 22.04 LTS** as the OS.
3. Set (or retrieve) the **root password** and note the **server IP**.
4. Collect:
   - the **VPS IP** → used everywhere as `<your-vps-ip>`
   - **root SSH access** (password to start; you'll add a key in the next guide)

Full setup — firewall, users, Docker, Python, cloning the repo — is
[`02-vps-ssh-setup.md`](02-vps-ssh-setup.md).

---

## 6. (Optional) Supabase — call logs + booked visits

1. Create a free project at **supabase.com** (it's Postgres under the hood).
2. From **Project Settings → API**, collect:
   - the **project URL** → `SUPABASE_URL`
   - the **service role key** → `SUPABASE_SERVICE_KEY`
3. You'll create two tables (`calls`, `site_visits`) when you wire up n8n.

---

## 7. (Optional) Telegram — owner alerts

1. In Telegram, message **@BotFather**, run `/newbot`, and follow the prompts.
2. Collect:
   - the **bot token** → `TELEGRAM_BOT_TOKEN`
3. Get your **chat id** (message your bot, then check
   `https://api.telegram.org/bot<token>/getUpdates`, or use a chat-id bot):
   - the **chat id** → `TELEGRAM_CHAT_ID`

---

## ✅ Credential checklist

By now you should hold every one of these. If any box is empty, go back before
you deploy.

**LiveKit**
- [ ] `LIVEKIT_URL`
- [ ] `LIVEKIT_API_KEY`
- [ ] `LIVEKIT_API_SECRET`
- [ ] `SIP_URI` *(from the "SIP URI" card — not the WSS url)*

**Sarvam**
- [ ] `SARVAM_API_KEY`

**OpenAI**
- [ ] `OPENAI_API_KEY`

**Vobiz**
- [ ] `VOBIZ_DID`
- [ ] `VOBIZ_SIP_DOMAIN`
- [ ] `VOBIZ_TRUNK_ID`
- [ ] `VOBIZ_AUTH_USERNAME`
- [ ] `VOBIZ_AUTH_PASSWORD`
- [ ] `DEFAULT_TRANSFER_NUMBER` *(the human agent's number)*

**Hostinger VPS**
- [ ] `<your-vps-ip>` + root SSH working

**Optional**
- [ ] `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
- [ ] `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- [ ] `REC_TOKEN` *(a long random string you generate yourself)*

Next up → **[02 · VPS & SSH setup](02-vps-ssh-setup.md)**.
