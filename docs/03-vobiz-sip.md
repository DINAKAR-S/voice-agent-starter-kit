# 03 · Vobiz SIP wiring — connecting a real phone number

This is the step that turns "code that runs" into "a phone that rings and
answers." It's also where most people lose an afternoon, so every hard-won gotcha
below is called out loudly. Read the callouts. They are not optional.

---

## The model: SIP trunk, NOT a webhook app

Some telephony providers give you a webhook/XML app model — they POST to your
server and you reply with XML instructions. **We do not use that.** We use a
**SIP trunk**: Vobiz forwards the raw SIP call straight to LiveKit's SIP
endpoint, and LiveKit hands the call to your agent worker. Lower latency, cleaner
audio, no XML round-trips.

### The exact inbound flow

```
Caller dials your DID
      │
      ▼
Vobiz DID  ──(bound to)──▶  Vobiz INBOUND SIP trunk
      │                         │  Origination URI points at LiveKit:
      │                         ▼
      └────────── SIP INVITE ──▶  <your-project-id>.sip.livekit.cloud:5060  (UDP)
                                   │
                                   ▼
                        LiveKit INBOUND trunk  (NO-AUTH, matched on the DID number)
                                   │
                                   ▼
                            LiveKit DISPATCH RULE
                                   │
                                   ▼
                        agent worker (agent_name = maya)  →  AgentSession
```

---

## Step 1 — In Vobiz: detach the DID, then set the Origination URI

1. **Detach the DID from any XML/voice app first.**

   > ⚠️ A DID binds to **either** an XML app **or** a SIP trunk — never both. If
   > your number is currently attached to an app, calls will keep going there and
   > your trunk will look dead. Detach from the app before you attach the trunk.

2. Create (or edit) an **inbound SIP trunk** on the DID and set its
   **Origination URI** to your LiveKit SIP host, with the port:

   ```
   <your-project-id>.sip.livekit.cloud:5060
   ```

   > ⚠️ **This host comes from the LiveKit "SIP URI" card** (Dashboard →
   > Telephony → SIP trunks). **Do NOT construct it from your `LIVEKIT_URL` /
   > WSS url.** The WSS host and the SIP host are different endpoints. Using the
   > wrong one is the #1 cause of "the INVITE never arrives" — the call just rings
   > into the void.

3. Note that Vobiz's Origination URI has **no auth fields**. That's expected and
   it drives the next step.

---

## Step 2 — In LiveKit: create the no-auth inbound trunk + dispatch rule

Run the helper on your VPS (venv active, `.env` filled in):

```bash
cd /opt/voice-agent
source .venv/bin/activate
python deploy/create_sip_trunk.py
```

This script uses the LiveKit API to create:

- an **inbound SIP trunk** that is **no-auth** and matches your DID number, and
- a **dispatch rule** that routes matched calls to the agent named `maya`
  (`AGENT_NAME` in `.env`).

> ⚠️ **The LiveKit inbound trunk MUST be no-auth.** Vobiz's Origination URI sends
> no SIP credentials, so if the LiveKit trunk requires auth it will **401** the
> INVITE and the call fails before your agent ever sees it. (Auth is only for the
> outbound/transfer leg — a different trunk.)

> ⚠️ **Put every number format in the trunk's `numbers` list.** Vobiz frequently
> presents the called number **national / 0-prefixed** (e.g. `0XXXXXXXXXX`),
> **not** E.164. If your trunk only matches `+91XXXXXXXXXX`, the INVITE arrives
> but matches nothing and LiveKit replies **`USER_BUSY`**. Include **all** forms:
> `0XXXXXXXXXX` (0-prefixed), `XXXXXXXXXX` (bare), `+91XXXXXXXXXX` (E.164), and
> `91XXXXXXXXXX`. `create_sip_trunk.py` already fans these out from `VOBIZ_DID` —
> just make sure `VOBIZ_DID` is set correctly.

---

## Step 3 — Self-hosted LiveKit? Mind the SIP container

If you self-host LiveKit (Option B) instead of using LiveKit Cloud, the SIP
service is the `livekit/sip` container. It needs:

- `sip_port: 5060`
- RTP media range `10000-20000/udp`
- `network_mode: host` in compose (so it can bind the media ports directly)

Those ports must be open in `ufw` (see
[`02-vps-ssh-setup.md`](02-vps-ssh-setup.md)). The compose file is
[`deploy/docker-compose.livekit.yml`](../deploy/docker-compose.livekit.yml),
with server config in [`deploy/livekit.yaml.example`](../deploy/livekit.yaml.example).

---

## Step 4 — Make a test call

1. Make sure the agent worker is running (`python agent.py start`, or the
   `systemd` service).
2. Dial your `VOBIZ_DID` from any phone.
3. Maya should pick up within a ring or two and greet you.

If she does — 🎉 you have a working phone agent. Move on to
[`04-latency.md`](04-latency.md) to keep her fast, and wire up the n8n ETL below
so calls get logged.

---

## n8n ETL — logging, lead extraction, alerts (side-path)

n8n runs on the same VPS and handles everything that is **not** the live audio
path. It runs in Docker via [`n8n/docker-compose.n8n.yml`](../n8n/docker-compose.n8n.yml);
import [`n8n/workflow.voice-events.json`](../n8n/workflow.voice-events.json) into your n8n instance.

The single workflow:

1. **Webhook `POST /webhook/voice-events`** — responds `200` immediately, then a
   **Switch** on the event type:
   - `call.started` / `call.completed` → upsert a row in the Supabase `calls`
     table.
   - `transcript.ready` → an OpenAI `gpt-4o-mini` **strict-JSON** extraction
     (caller name, budget, preferred area, site-visit date) → insert into the
     Supabase `site_visits` table → **if** a visit was booked, **Telegram DM** the
     owner.
2. **Recording webhook** — Vobiz POSTs the call recording; n8n forwards it to a
   tiny **localhost `recording_handler`** on the VPS, which (behind an SSRF
   allow-list) downloads the file and drops it into
   `/opt/voice-agent/recordings/<call>.mp3` so the dashboard can play it.

> ⚠️ **Enable HMAC signature verification on the webhooks before you go live.**
> The workflow ships with the verification step **stubbed** so it imports and
> runs. An open webhook lets anyone forge call events into your database and spam
> your owner's Telegram. Turn it on: verify the provider's signature header
> against a shared secret, reject on mismatch.

> ⚠️ The `recording_handler` is **SSRF-guarded to an allow-list** on purpose.
> It only downloads from approved recording hosts. Don't loosen that — an
> unguarded "fetch this URL" endpoint on your VPS is a classic pivot for
> attackers to reach internal services.

Recordings live on the VPS filesystem by default. To use S3 instead, uncomment
the `S3_*` vars in [`.env.example`](../.env.example).

---

## 🔧 Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| **INVITE never arrives** (LiveKit shows no incoming call) | Origination URI built from the WSS url, not the SIP host | Copy the host from LiveKit's **"SIP URI" card**; use `<your-project-id>.sip.livekit.cloud:5060` |
| Call fails with **`USER_BUSY`** | DID delivered as `0`-prefixed / national but trunk only matches E.164 | Add **all** number formats to the trunk `numbers` list (`0…`, bare, `+91…`, `91…`) |
| INVITE gets a **`401 Unauthorized`** | LiveKit inbound trunk requires auth; Vobiz sends none | Recreate the inbound trunk as **no-auth** |
| Number rings but hits an old menu / dead air | DID still attached to an XML app | **Detach the DID from the app**, then bind it to the SIP trunk |
| Call connects but you hear **silence** | UDP media ports blocked | Open `10000:20000/udp` and `50000:60000/udp` in `ufw` and any provider firewall |
| Everything connects but no agent joins | Dispatch rule points at the wrong `agent_name` | Ensure the dispatch rule targets `AGENT_NAME` (`maya`) and the worker is running |

Next up → **[04 · Latency](04-latency.md)**.
