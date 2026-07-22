# 06 · Cost per minute — proving a multilingual voice agent runs under ₹4/min

This page shows, line by line, what one minute of a live Maya call actually costs when you
self-host the media path on a cheap Indian VPS. The headline: **a tuned cascade lands around
₹3.2/minute — comfortably under ₹4/min** — *as long as you keep replies short* (that last clause
matters; see the sensitivity note).

> ⚠️ **Every number here is illustrative — verify current pricing before you quote a client.**
> All figures were checked on **2026-07-22**. Vendors change prices, exchange rates move, and your
> traffic pattern is your own. Treat this as a transparent model you can re-run with today's rates,
> not a fixed price list.

---

## The conversation we're pricing

To turn "cost per minute" into real arithmetic we have to fix a picture of what one minute of a
Maya call actually looks like. These are the free variables — change any of them and the total
moves, so they're all stated out in the open:

| Variable | Assumed value | Why |
|---|---|---|
| Turns per minute | ~3 exchanges (caller ↔ Maya) | Natural phone back-and-forth |
| Maya's speech share | ~50% of the minute | The caller talks the other half |
| **Maya's words spoken** | **~75 words/min** | ~25 words/turn ≈ the "≤2 sentences" rule |
| Reply cap | `max_tokens = 140` | Hard ceiling; the base case sits well under it |
| Chars per word | ~6 (incl. spaces) | Used to convert words → TTS characters |
| Tokens per word | ~1.33 | Used to convert words → LLM output tokens |
| LLM input per turn | ~5,000 tokens | Short persona + grammar file (in-prompt every turn) + tool schemas + growing history |
| VPS amortization | ₹899/mo ÷ 3,000 call-min/mo | ≈ 100 call-minutes/day on one VPS |
| USD → INR | ₹96.36 | Spot rate, July 2026 |

Notice **Maya's word count (75/min) drives two different costs at once**: the LLM *output* tokens
(words × 1.33) and the TTS *characters* (words × 6). They come from the same sentences, so they
stay consistent — if Maya talks more, both rise together.

> ⚠️ **Why LLM input is ~5,000 tokens, not "a couple hundred".** The grammar file for the call's
> language is appended to the prompt and re-sent on **every turn**, and Indic scripts tokenize
> heavily on OpenAI's tokenizer (~1.5–2.5 tokens per character), so a ~6 KB Malayalam grammar file
> is ~3,000+ tokens on its own — before persona, tool schemas and growing history. We budget ~5,000.
> **OpenAI prompt caching** bills that repeated persona+grammar prefix at ~25% on turns 2+, which
> partly offsets it — we don't discount for it here, so this line is a conservative upper bound.

---

## Component pricing (checked 2026-07-22)

| Component | Vendor / rate | Source |
|---|---|---|
| STT | Sarvam **Saaras** — ₹30 per **hour** of audio = ₹0.50/min | [sarvam.ai/api-pricing](https://www.sarvam.ai/api-pricing) |
| TTS | Sarvam **Bulbul v3** — ₹30 per **10,000 characters** = ₹0.003/char | [sarvam.ai/api-pricing](https://www.sarvam.ai/api-pricing) |
| LLM | OpenAI **gpt-4.1-mini** — $0.40 / 1M input, $1.60 / 1M output tokens | [OpenAI API pricing](https://developers.openai.com/api/docs/pricing) |
| Telephony | Vobiz inbound SIP — *rate not public;* typical Indian SIP inbound **₹0.30–0.50/min** | [Vobiz](https://www.vobiz.ai/) · [SIP rate reference](https://frejun.com/sip-trunk-providers-india/) |
| Media (LiveKit) | **Self-hosted** on the same VPS → ~₹0 marginal per minute | self-hosted (see deployment docs) |
| VPS | Hostinger **KVM 2** — ₹899/mo (≈₹519/mo on a 12-month term) | [Hostinger VPS](https://www.hostinger.in/vps-hosting) |
| FX | USD → INR ≈ ₹96.36 (July 2026) | [exchangerates.org.uk](https://www.exchangerates.org.uk/USD-INR-spot-exchange-rates-history-2026.html) |

> ⚠️ **Vobiz does not publish a per-minute inbound rate** (it's quote-based). We use a
> **clearly-labelled typical Indian SIP inbound rate of ₹0.40/min** (midpoint of the ₹0.30–0.50
> range seen across Indian SIP providers). Replace it with your actual Vobiz quote before you rely
> on this. DID rental (~₹500/mo) and one-time setup are separate and not in the per-minute figure.

---

## The per-minute table

Each line shows the arithmetic, then the cost for one call-minute.

| Component | How it's computed | Cost / min |
|---|---|---|
| **STT (Saaras)** | ₹30/hr ÷ 60 = ₹0.50/min (full-minute, conservative) | **₹0.50** |
| **LLM input** | 3 turns × 5,000 tok = 15,000 tok → 15,000 × $0.40/1M = $0.006 → ×96.36 | **₹0.58** |
| **LLM output** | 75 words × 1.33 = ~100 tok → 100 × $1.60/1M = $0.00016 → ×96.36 | **₹0.02** |
| **TTS (Bulbul v3)** | 75 words × 6 = 450 chars → 450 × ₹0.003 | **₹1.35** |
| **Telephony (Vobiz)** | typical Indian SIP inbound, illustrative | **₹0.40** |
| **LiveKit media** | self-hosted on the VPS → marginal | **₹0.00** |
| **VPS (amortized)** | ₹899/mo ÷ 3,000 call-min/mo | **₹0.30** |
| **Total** | | **≈ ₹3.15 / min** |

**≈ ₹3.15/minute — under ₹4/min with room to spare.** (Prompt caching on the repeated persona+grammar
prefix, which we did *not* discount above, pulls it back toward ~₹2.8 in practice.)

A quick sanity read of the shape: **TTS is the single biggest line (~₹1.35, ~43% of the total)** and
it scales *linearly* with how much Maya talks. STT is next and is basically fixed. The LLM (~₹0.60
combined) is modest — and almost all of it is *input*, from re-sending the persona+grammar every turn,
not the actual thinking; output is a rounding error because replies are capped. That's the whole game:
**what Maya speaks (TTS) and what we feed her every turn (input tokens) are the costs — so the persona
is short and written to speak few words.**

---

## Sensitivity — what pushes it over ₹4

Because TTS dominates and scales with Maya's word count, the budget lives or dies on **reply length**:

- **Long replies (the killer).** If Maya hits `max_tokens = 140` on *every* turn — ~105 words/turn,
  ~315 words/min — TTS alone becomes 315 × 6 × ₹0.003 ≈ **₹5.7/min**, and the total blows past **₹7/min**.
  This is exactly why the grammar files enforce **"≤ 2 sentences per turn"** and **"don't blow
  max_tokens"** as hard DON'Ts: **those rules are cost controls, not just style.** Under ₹4/min is only
  true *with the ≤2-sentence discipline actually enforced.*
- **Premium / higher-quality TTS voice or Bulbul at a higher tier** → more ₹/char, higher TTS line.
- **LiveKit Cloud instead of self-host.** Cloud has a generous free tier, but past it you pay per
  participant-minute for media — that adds a real per-minute line that self-hosting avoids.
- **Low call volume.** The VPS is a fixed ₹899/mo. At 3,000 min/mo it's ₹0.30/min; at only 500 min/mo
  it's ₹1.80/min. Amortization only helps if the line is busy.
- **STT on the full minute.** We charged the whole minute of audio (₹0.50). VAD-gating so you only
  send *caller* speech to Saaras can roughly halve this in practice.

---

## How to cut cost further

- **Self-host LiveKit** (which this kit does) — keeps the media line at ~₹0/min instead of paying
  Cloud per-participant-minute past the free tier.
- **Cap `max_tokens` tight (80–140) and enforce short replies** in the persona + grammar files —
  the highest-leverage knob, because it shrinks the dominant TTS line directly.
- **Pick a cheaper TTS tier where quality allows** (e.g. Bulbul v2 at ₹15/10k chars ≈ half the TTS
  line) for non-flagship voices or internal lines.
- **VAD-gate STT** so you only transcribe caller speech, not silence or Maya's audio.
- **Batch the VPS across clients.** One KVM 2 can host several agents; splitting the ₹899/mo across
  clients drives the amortized VPS line toward zero.
- **Trim the system prompt.** A shorter prompt cuts both latency *and* the LLM input line on every turn.

---

*All figures illustrative — verify current pricing (checked 2026-07-22). Never present a number here
as a fixed quote; re-run the table with live rates for the client and date in front of you.*
