# dashboard — static call review UI

A zero-dependency HTML dashboard for reviewing Maya's calls: per-stage latency
(colour-coded), auto-flag chips, expandable transcripts, and inline audio when a
recording exists. It is regenerated from files on disk — no server, no framework.

## See it in 5 seconds

```bash
python build_dashboard.py --demo
# open dashboard.html in a browser
```

`--demo` renders one sample card from inline fake data so you know what "good"
looks like before you have real calls.

## Real data

- Drop one JSONL file per call in `transcripts/` (the agent writes these — one
  `{"role":..., "text":..., "latency_ms":{...}}` object per line, optional
  `{"type":"meta",...}` header line).
- Put recordings as `recordings/<call_id>.mp3` (the recording handler does this).

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
