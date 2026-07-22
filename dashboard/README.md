# dashboard — static call review UI

A zero-dependency HTML dashboard for reviewing Maya's calls: a summary bar
(calls / minutes / cost / avg-per-min), then one card per call with an AI
summary, a per-provider cost breakdown (Vobiz / Sarvam / GPT), an inline audio
player + download, per-stage latency (colour-coded), auto-flag chips, and the
full transcript. Regenerated from files on disk — no server, no framework.

## See it in 5 seconds

```bash
python build_dashboard.py --demo
# open dashboard.html in a browser — 3 sample calls, with playable sample audio
```

`--demo` renders three sample calls (a clean one, a stretched one, and a flagged
one) so you know what "good" and "bad" look like before you have real calls. The
tiny sample `.wav` files in `recordings/` ship with the repo so the player works.

## Real data

- Drop one JSONL file per call in `transcripts/`. The first line is an optional
  `{"type":"meta",...}` header; every other line is a turn:

  ```json
  {"type":"meta","call_id":"maya-2201","phone":"+91 90000 00001","direction":"INBOUND",
   "language":"hi","started_at":"21 Jul 2026, 04:21 PM IST","duration_min":1.2,
   "summary":"Caller booked a Saturday site visit for a 2 BHK.",
   "cost":{"total":3.12,"per_min":2.60,"vobiz":0.40,"sarvam":1.90,"gpt":0.30}}
  {"role":"user","text":"..."}
  {"role":"assistant","text":"...","latency_ms":{"eou":150,"stt":95,"llm":560,"tts":330}}
  ```

  Every `meta` field is optional — the dashboard degrades gracefully. `summary`
  comes from your n8n `transcript.ready` step; `cost` from `analyse_call`.
- Put recordings as `recordings/<call_id>.mp3` (or `.wav`) — the recording
  handler does this.

```bash
python build_dashboard.py            # reads ./transcripts + ./recordings → dashboard.html
python build_dashboard.py --self-check   # asserts the colour-coding + flag logic
```

> ⚠️ **Wiring note (agent → dashboard).** In this skeleton `agent.py` streams
> per-turn latency rows to `logs/metrics.jsonl` (from its `metrics_collected`
> handler). The dashboard reads **one JSONL file per call** from `transcripts/`.
> These are deliberately *not* auto-wired — persisting a full per-call transcript
> is your integration step. The simplest path: in `agent.py`, on session close,
> write that call's turns (role, text, and the `latency_ms` dict shown above) to
> `transcripts/<room>-<ts>.jsonl`. Until you do, use `--demo` to see the layout.

Latency colours per stage (green within budget / amber stretched / red over):
EOU & STT ≤300/500 ms, LLM ≤800/1200 ms, TTS ≤500/800 ms. Flags: `LLM-SLOW>1s`,
`TTS-SLOW>0.5s`, `EMPTY-REPLY`, `VERBOSE`, `RECOVERY-LOOP`.

## In production

Regenerate on a 1-minute cron so the page is always current:

```cron
* * * * * cd /opt/voice-agent/dashboard && /usr/bin/python3 build_dashboard.py >/dev/null 2>&1
```

Serve `dashboard.html` (plus the `recordings/` dir for the `<audio>` players) over
Traefik with HTTP basic-auth. Sketch:

```yaml
# labels on a tiny static file server container behind Traefik
- traefik.http.routers.dash.rule=Host(`dash.your-vps.example`)
- traefik.http.routers.dash.tls.certresolver=le
- traefik.http.routers.dash.middlewares=dash-auth
- traefik.http.middlewares.dash-auth.basicauth.users=YOUR_HTPASSWD_LINE
```

Browsers request audio with HTTP Range; any normal static file server (nginx,
Caddy, Traefik's file provider) handles that out of the box.
