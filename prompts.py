"""System prompts and per-language copy for Maya, the Acme Realty receptionist.

Latency note: on a phone call the system prompt is the single biggest latency
killer. Keep HOT_PERSONA SHORT (a couple hundred chars, well under ~800). Do NOT
paste property data, price lists, or FAQs in here -- Maya reads those at runtime
through the function tools in tools.py. A short prompt = fewer input tokens =
faster LLM time-to-first-token every single turn.
"""

from __future__ import annotations

import functools
from pathlib import Path

# Where the per-language grammar sheets live (grammar/maya_<lang>_grammar.md).
GRAMMAR_DIR = Path(__file__).parent / "grammar"

# The one persona prompt, shared by every language agent. Keep it tight.
# (Measured under ~700 chars -- see the self-check at the bottom of this file.)
HOT_PERSONA = (
    "You are Maya, the warm phone receptionist for Acme Realty, a home real-estate agency. "
    "This is a live call: reply in at most two short sentences and ask one question at a time. "
    "Use ONLY the tools for property facts (search_properties, get_property_details) -- never "
    "invent listings, prices, or availability. Help the caller find a 2/3 BHK flat or plot within "
    "their budget and area, capture their name, phone, budget and preferred area, then book a site "
    "visit with book_site_visit. If they ask for a person, use transfer_to_human. If a detail is "
    "not in the data, say a colleague will confirm."
)

# Human-readable language names, used in the per-language instruction line.
LANG_NAMES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
}

# Tiny per-language style note appended to the persona. Kept short on purpose.
STYLE_NOTES: dict[str, str] = {
    "en": "Speak clear, simple English.",
    "hi": "Reply in natural, conversational Hindi (Devanagari script), not formal textbook Hindi.",
    "ta": "Reply in natural spoken Tamil (Tamil script), the way people actually talk.",
    "te": "Reply in natural spoken Telugu (Telugu script).",
    "kn": "Reply in natural spoken Kannada (Kannada script).",
    "ml": "Reply in natural spoken Malayalam (Malayalam script).",
}

# What Maya says first when a call connects, per language.
GREETINGS: dict[str, str] = {
    "en": "Hi, thanks for calling Acme Realty! I'm Maya. How can I help you find a home today?",
    "hi": "नमस्ते, Acme Realty में कॉल करने के लिए धन्यवाद! मैं माया बोल रही हूँ। आपके घर की तलाश में मैं कैसे मदद कर सकती हूँ?",
    "ta": "வணக்கம், Acme Realty-க்கு அழைத்ததற்கு நன்றி! நான் மாயா பேசுகிறேன். உங்கள் வீட்டைத் தேட நான் எப்படி உதவலாம்?",
    "te": "నమస్తే, Acme Realty కి కాల్ చేసినందుకు ధన్యవాదాలు! నేను మాయా మాట్లాడుతున్నాను. మీ ఇంటిని వెతకడంలో నేను ఎలా సహాయం చేయగలను?",
    "kn": "ನಮಸ್ಕಾರ, Acme Realty ಗೆ ಕರೆ ಮಾಡಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು! ನಾನು ಮಾಯಾ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ. ನಿಮ್ಮ ಮನೆ ಹುಡುಕಲು ನಾನು ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
    "ml": "നമസ്കാരം, Acme Realty യിലേക്ക് വിളിച്ചതിന് നന്ദി! ഞാൻ മായ സംസാരിക്കുന്നു. നിങ്ങളുടെ വീട് കണ്ടെത്താൻ ഞാൻ എങ്ങനെ സഹായിക്കാം?",
}


@functools.lru_cache(maxsize=8)
def load_grammar(language: str) -> str:
    """Return the per-language grammar sheet (grammar/maya_<lang>_grammar.md), or "".

    These sheets (honorifics, code-mix rules, real-estate vocab, the §5b
    wrong->right table) are what make Maya sound native. They are loaded once and
    cached. Missing file -> "" so the agent still runs on STYLE_NOTES alone.
    """
    path = GRAMMAR_DIR / f"maya_{language}_grammar.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def build_instructions(language: str, script: str, include_grammar: bool = True) -> str:
    """Compose the full system prompt for a per-language agent.

    `language` is a short code (en/hi/ta/...); `script` is the tiny per-language
    style note (usually STYLE_NOTES[language]). The bulk (HOT_PERSONA) stays the
    same across languages -- we bolt on a one-line language rule, then (if
    available) the full grammar sheet for that language.

    Latency tradeoff: the grammar sheet adds input tokens every turn, which raises
    LLM time-to-first-token a little. It buys much more natural, native-sounding
    Indic speech -- usually worth it. Set include_grammar=False (or trim the sheet)
    if you need to shave the last few ms. See docs/04-latency.md.
    """
    name = LANG_NAMES.get(language, language)
    base = f"{HOT_PERSONA}\n\nRespond only in {name}. {script}"
    grammar = load_grammar(language) if include_grammar else ""
    return f"{base}\n\n{grammar}" if grammar else base


if __name__ == "__main__":
    # Self-check: the persona must stay short (latency) and every language must
    # have parallel copy so nothing goes silent after a language switch.
    assert len(HOT_PERSONA) <= 800, f"HOT_PERSONA too long: {len(HOT_PERSONA)} chars"
    for _code in LANG_NAMES:
        assert _code in STYLE_NOTES, f"missing STYLE_NOTES[{_code}]"
        assert _code in GREETINGS, f"missing GREETINGS[{_code}]"
    assert "Acme Realty" in build_instructions("hi", STYLE_NOTES["hi"])
    # Grammar sheets should exist and get appended when present.
    for _code in LANG_NAMES:
        assert load_grammar(_code), f"missing/empty grammar sheet for {_code}"
    _with = build_instructions("ta", STYLE_NOTES["ta"], include_grammar=True)
    _without = build_instructions("ta", STYLE_NOTES["ta"], include_grammar=False)
    assert len(_with) > len(_without), "grammar sheet was not appended"
    print(f"prompts.py self-check passed (HOT_PERSONA={len(HOT_PERSONA)} chars, grammar wired)")
