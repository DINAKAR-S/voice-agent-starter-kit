# 04 · Latency — the honest numbers and how to hit them

Voice agents live and die on latency. If Maya takes two seconds to start
replying, the call feels broken no matter how smart she is. This page gives you
the **real measured numbers**, the **recipe** that produces them, and the
**model bake-off** notes so you don't repeat our mistakes.

---

## The measured numbers

Measured on an India VPS with the tuned cascade in this kit. Quoted honestly —
these are what you should actually expect, not a best-case demo.

| Stage | Measured |
|---|---|
| End-of-utterance detection (EOU) | ~0.15–0.29 s |
| STT transcription delay | ~0.08–0.29 s |
| LLM time-to-first-token (gpt-4.1-mini) | ~0.5–0.8 s *(Groq Llama-3.3 ~0.32 s but weaker Indic)* |
| TTS time-to-first-byte (Sarvam Bulbul v3) | ~0.33–0.35 s |
| **Perceived turn latency** | **~700 ms – 1.2 s** |

> **The honest headline:** ~700 ms–1.2 s perceived turn latency on a self-hosted
> STT→LLM→TTS cascade, on one India VPS. **Sub-500 ms every turn is NOT achievable
> with a cascade** — only a speech-to-speech model gets you there. Measured, not
> guessed.

"Perceived turn latency" is the gap the caller actually feels: from when they
stop talking to when they hear Maya start talking. It's less than the sum of the
stages because they **overlap** (streaming) — the LLM starts generating before
STT fully settles, and TTS starts speaking the first sentence while the LLM is
still writing the rest.

---

## The latency recipe — an actionable checklist

Do all of these. Each one shaves real milliseconds; skipping the prompt-size one
alone can double your latency.

- [ ] **8 kHz end-to-end.** Telephony audio is 8 kHz — keep STT and TTS at 8 kHz
      instead of upsampling. Less data, less delay, and it matches the line.
- [ ] **Stream both ways over WebSocket.** STT streams partials in; TTS streams
      audio out. Never wait for a full transcript or a full audio file.
- [ ] **Sentence-level TTS dispatch.** Send the first sentence to TTS the moment
      it's complete, while the LLM keeps writing. The caller hears speech sooner.
- [ ] **Short system prompt (≤2 kB).** 🔴 **This is the single biggest latency
      killer.** Every token in the system prompt is re-processed on every turn.
      Keep the persona tight; push bulk data into tools.
- [ ] **Tight endpointing.** `min_endpointing_delay 0.15s`, `max 1.0s` — detect
      the caller finished quickly without chopping them off mid-sentence.
- [ ] **Aggressive VAD.** Silero `min_silence 0.15s` (`VAD_MIN_SILENCE_MS=150`).
- [ ] **Cap output length.** `max_tokens 80–140`. A phone reply should be one or
      two sentences; capping tokens caps generation time.
- [ ] **Keep bulk data in tools, not the prompt.** Property listings, menus,
      schedules — load them via a function tool (`data/properties.json`), never
      paste them into the system prompt.
- [ ] **Colocate in India (Mumbai).** VPS, LiveKit region, and model endpoints all
      close together. Cross-continent round-trips are pure tax.
- [ ] **Instrument every stage first.** You can't tune what you can't see — see
      below.

---

## Per-stage instrumentation

Before you optimize anything, measure everything. The agent timestamps each stage
of a turn and emits them (into the transcript JSONL and the dashboard):

- **EOU** — when VAD/endpointing decides the caller has stopped.
- **STT delay** — EOU → final transcript ready.
- **LLM TTFT** — transcript sent → first token back.
- **TTS TTFB** — first sentence sent → first audio byte back.

The dashboard ([`dashboard/build_dashboard.py`](../dashboard/build_dashboard.py))
colour-codes each stage per call (🟢 green / 🟡 amber / 🔴 red) and raises
**auto-flag chips** so slow turns jump out:

| Chip | Means |
|---|---|
| `LLM-SLOW` | LLM time-to-first-token over budget |
| `TTS-SLOW` | TTS time-to-first-byte over budget |
| `EMPTY-REPLY` | model returned empty content (see bake-off below) |
| `VERBOSE` | reply too long — tighten `max_tokens` / prompt |
| `RECOVERY-LOOP` | agent stuck re-asking / repeating |

Fix the reddest stage first, re-measure, repeat. Optimizing blind wastes time on
stages that were already fine.

---

## Model bake-off — why `gpt-4.1-mini`

We tried the obvious alternatives. Here's what happened, so you don't have to
relearn it live on a customer call:

- **Sarvam-30b / 105b** — tempting to keep everything on one vendor, but these are
  **reasoning-oriented** models. On short voice turns they returned **empty
  `content` ~60% of the time** (all their effort went into hidden reasoning, not
  the answer). That triggers the `EMPTY-REPLY` flag and dead air on the call.
  **Unfit for voice.**
- **Groq Llama-3.3** — genuinely **fast** (~0.32 s TTFT, faster than gpt-4.1-mini)
  and great for English. But its **Tamil (and broader Indic) quality was weak** —
  wrong words, awkward phrasing. Speed you can't understand isn't a win.
- **`gpt-4.1-mini`** — the balance that won: **fast enough** (~0.5–0.8 s TTFT),
  **cheap**, reliably returns real content, and handles Indic prompting well
  enough alongside Sarvam's STT/TTS doing the heavy language lifting.

If your use case is English-only and you want the last ~200 ms, Groq Llama-3.3 is
worth revisiting. For multilingual Indian calls, stay on `gpt-4.1-mini`.

Next up → **[05 · Add a client](05-add-a-client.md)** to point all this at your
own business.
