# `grammar/` — the per-language "sound native" layer

This folder is Maya's secret sauce. A generic multilingual prompt makes an agent that speaks six
languages *badly* — wrong honorifics, over-translated jargon ("EMI" awkwardly rendered as "monthly
instalment"), robotic numbers. These files fix that by giving the LLM a **small, focused speaking
guide for exactly the one language the call is in** — and nothing else.

## What's here

| File | Language | Polite "you" it enforces |
|---|---|---|
| `maya_en_grammar.md` | English | "you" |
| `maya_hi_grammar.md` | Hindi (हिन्दी) | आप |
| `maya_ta_grammar.md` | Tamil (தமிழ்) | நீங்க |
| `maya_te_grammar.md` | Telugu (తెలుగు) | మీరు |
| `maya_kn_grammar.md` | Kannada (ಕನ್ನಡ) | ನೀವು |
| `maya_ml_grammar.md` | Malayalam (മലയാളം) | നിങ്ങൾ |

Every file has the same six sections: **Register & tone · Code-mixing rule · Real-estate vocabulary ·
§5b Wrong→Right · Numbers & money · DO/DON'T.**

## How a file gets loaded (per call)

Language is locked once per call (the `GreeterAgent` detects it, then hands off to the matching
`LangAgent`). At that point the agent's instructions are built like this:

```python
# prompts.py — sketch
from pathlib import Path

GRAMMAR_DIR = Path(__file__).parent / "grammar"

def build_instructions(language: str) -> str:
    """Hot persona + the ONE grammar file for this call's language."""
    persona = PERSONA_PROMPT                       # short, shared, ≤2 kB — Maya's identity + rules
    grammar_file = GRAMMAR_DIR / f"maya_{language}_grammar.md"
    grammar = grammar_file.read_text(encoding="utf-8")
    return f"{persona}\n\n{grammar}"

# ponytail: one file read per call handoff; cache with @lru_cache(maxsize=8) if it ever shows up hot.
```

Only **one** grammar file is ever in the prompt at a time. That keeps the system prompt short —
which matters twice over: a short prompt is the single biggest latency win on a cascade, **and** the
prompt is billed as LLM input tokens on every turn (see `docs/06-cost-per-minute.md`). Six languages'
worth of guidance stuffed into one prompt would be slower, pricier, and worse.

> ⚠️ The grammar file is **appended to** the hot persona, never a replacement. The persona owns
> Maya's identity, the tools, and the hard rules; the grammar file owns *how she sounds in this language*.

## The self-learning loop (§5b)

Section 5b of each file — the **Wrong → Right** table — is the part that improves over time. The loop:

1. **Pull the transcript** of a finished call (the JSONL the pipeline already writes).
2. **Catalog the slips.** Where did Maya mis-say a number, use "तुम" instead of "आप", over-translate
   "site visit", or mangle an area name? Each slip becomes one row: *said (wrong) → correct → why.*
3. **Append the row to §5b** of that language's grammar file. Real, observed mistakes — not guesses.
4. **Redeploy.** Next call in that language, the LLM reads the updated table and avoids the slip.

Because §5b lives in the prompt, corrections take effect on the very next call — no fine-tuning, no
retraining. The tables ship **seeded** with 4–6 realistic entries per language so the loop starts
useful on day one; keep them short (a bloated §5b re-introduces the latency/cost you were saving).

> Tip: this cataloguing step is a great fit for a nightly batch job — feed the day's transcripts to a
> cheap model with the instruction "list only real wrong→right pairs, one per line", then a human
> skims before appending. Never auto-append unreviewed.

## Adding a new language

1. **Copy** `maya_en_grammar.md` to `maya_<code>_grammar.md` (BCP-47 short code, e.g. `bn` for Bengali,
   `mr` for Marathi, `gu` for Gujarati).
2. **Confirm the STT/TTS support it.** The language must exist for Sarvam Saaras (STT) and Bulbul (TTS),
   and you need a `LangAgent` locked to that BCP-47 code on both.
3. **Rewrite all six sections in that language**, by (or reviewed by) a native speaker:
   - the **polite "you"** and correct honorific register,
   - a **Numbers & money** section with the right lakh/crore words,
   - **native-script code-mix examples** that *keep* `BHK`, `sq ft`, `EMI`, `site visit`, names, and area
     names in Latin — that inline-English is the whole point; translating those breaks the "native" feel,
   - **seed §5b** with 4–6 realistic slips for that language.
4. **Wire it up:** add the language to the greeter's detection + `set_language` handoff so
   `build_instructions("<code>")` can find the file. Remember `set_language` must `session.say(...)` a
   confirmation *in the new language* — swapping the agent silently is a known way to make Maya go mute.
5. **Ship, listen, and let §5b grow** from real calls.

> ⚠️ Get a native speaker to check honorifics and the code-mix examples before going live. Wrong
> register (too familiar, or stiff and bookish) is the fastest way to sound like a bad translation bot —
> which is exactly what this folder exists to prevent.
