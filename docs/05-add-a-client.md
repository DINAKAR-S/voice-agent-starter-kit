# 05 · Add a client — clone Maya for your own business

The whole kit ships configured for the demo: **Maya**, an inbound receptionist
for **Acme Realty**. Pointing the same machinery at your own business — a
restaurant, a gym, a repair shop, a support desk — is deliberately small. You edit three files,
set a few env vars, and redeploy. No plumbing changes.

Think of it as a fill-in-the-blanks exercise, not a rebuild.

---

## What defines "the client"

Only four things make Maya *Maya-for-Acme-Realty* rather than a generic agent:

| Thing | Lives in | What it controls |
|---|---|---|
| **Persona & rules** | `prompts.py` | Who the agent is, tone, what she's allowed to do |
| **Business data** | `data/properties.json` | The facts she answers from (never in the prompt) |
| **Actions** | `tools.py` | The function tools (look up data, book, transfer) |
| **Identity & config** | `.env` | `AGENT_NAME`, default language, transfer number |

Change those four, keep everything else.

---

## Step 1 — Rewrite the persona in `prompts.py`

Open [`prompts.py`](../prompts.py) and edit the system prompt(s):

- Replace Maya / Acme Realty with your agent's name and business.
- State the tone (warm, brisk, formal — your call).
- List what she **can** do and what she **must not** do (e.g. "never quote a price
  not in the data", "always offer to book, never pressure").
- Keep the per-language variants in sync (English + the Indic languages you
  support).

> 🔴 **Keep the system prompt short — ≤2 kB.** This is the single biggest latency
> lever (see [`04-latency.md`](04-latency.md)). Resist the urge to paste your
> whole brochure in here. Facts go in the data file, not the prompt.

---

## Step 2 — Replace the data in `data/`

Swap [`data/properties.json`](../data/properties.json) for your own data file —
your menu, services, availability, price list, whatever the agent needs to answer
from. Keep it valid JSON with clear fields.

The agent reads this through a **function tool at runtime**, so:

- it never bloats the system prompt (good for latency), and
- you can update your data without touching prompts or redeploying code logic —
  just edit the JSON.

If your data has a different shape than properties, rename the file and update the
tool that reads it in the next step.

---

## Step 3 — Adjust the tools in `tools.py`

Open [`tools.py`](../tools.py) and align the function tools to your domain:

- Rename/repurpose the lookup tool to read your new data file.
- Rename the booking tool to fit (e.g. `book_visit` → `book_appointment` /
  `reserve_table`), keeping the fields you actually need to capture.
- Keep the **`set_language`** tool as-is — and remember its critical quirk:

  > ⚠️ When you change language mid-call, `set_language` **must call
  > `session.say(...)`** with a confirmation line in the *new* language. LiveKit's
  > `update_agent()` swaps the agent **silently** and does **not** make the new
  > agent speak on its own. Skip the `session.say` and the agent goes mute right
  > after switching languages — a real, confusing bug. Keep that line.

- Keep the **transfer** tool; it dials `DEFAULT_TRANSFER_NUMBER`.

---

## Step 4 — Set identity in `.env`

In your `.env` (copied from [`.env.example`](../.env.example)):

- `AGENT_NAME` — your agent's name/slug. **This must match the dispatch rule**
  created by `deploy/create_sip_trunk.py`. If you change it, re-run that script so
  the dispatch rule points at the new name.
- `DEFAULT_LANGUAGE` — the language the greeter opens in before detecting the
  caller's.
- `DEFAULT_TRANSFER_NUMBER` — the human this agent hands off to.
- `SARVAM_TTS_VOICE` — pick a voice that fits the new persona if `simran` doesn't.

---

## Step 5 — Deploy and test

Same flow as the first deploy:

```bash
cd /opt/voice-agent
git pull                       # or rsync your edits up
source .venv/bin/activate
pip install -r requirements.txt   # only if deps changed

# if you changed AGENT_NAME, refresh the dispatch rule:
python deploy/create_sip_trunk.py

# restart the worker (systemd) or run directly:
sudo systemctl restart voice-agent
# or: python agent.py start
```

Dial your DID and talk to your new agent. Done. 🎉

---

## Running multiple clients

Want more than one business on the same box? Two clean options:

1. **One number per agent** — give each client a distinct `AGENT_NAME`, its own
   data file and prompt module, its own DID + dispatch rule. Run each as its own
   `systemd` service (copy [`deploy/voice-agent.service`](../deploy/voice-agent.service)
   to `voice-agent-<client>.service` with its own `EnvironmentFile`).
2. **One deployment per client** — clone the repo into
   `/opt/voice-agent-<client>` and run them fully separately. Simplest to reason
   about; uses a bit more RAM.

Either way the pattern is identical to what you just did for one. Start with one,
prove it, then scale out.
