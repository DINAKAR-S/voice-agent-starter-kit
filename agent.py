"""Maya -- the Acme Realty inbound voice agent (LiveKit Agents worker).

Run it:
    python agent.py start          # register with LiveKit and take calls
    python agent.py console         # talk to Maya in your terminal (no phone)

Pipeline (cascade), tuned for ~700 ms-1.2 s perceived turn latency on one India VPS:
    Silero VAD -> Sarvam Saaras STT (codemix, 8 kHz) -> OpenAI gpt-4.1-mini
    -> Sarvam Bulbul TTS.

Language flow: a GreeterAgent greets in English and detects the caller's
language, then hands off to a per-language LangAgent that locks STT + TTS to
that language. See GreeterAgent.set_language for the (important) silent-swap fix.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

# --- TLS / cert guard (optional) --------------------------------------------
# On some minimal VPS images the system CA bundle is missing and Sarvam/OpenAI
# TLS handshakes fail. Pointing at certifi's bundle avoids that. Best-effort.
try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except Exception:  # pragma: no cover - purely defensive
    pass

from dotenv import load_dotenv

load_dotenv()

from livekit import agents
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    MetricsCollectedEvent,
    RunContext,
    WorkerOptions,
    function_tool,
    metrics,
)
from livekit.plugins import openai, sarvam, silero

from config import (
    AGENT_NAME,
    AUDIO_SAMPLE_RATE,
    BCP47,
    DEFAULT_LANGUAGE,
    MAX_ENDPOINTING_DELAY,
    MAX_TOKENS,
    MIN_ENDPOINTING_DELAY,
    OPENAI_LLM_MODEL,
    OPENAI_TEMPERATURE,
    SARVAM_STT_MODEL,
    SARVAM_TTS_MODEL,
    SARVAM_TTS_VOICE,
    SUPPORTED_LANGUAGES,
    VAD_MIN_SILENCE_S,
)
from prompts import (
    GREETINGS,
    HOT_PERSONA,
    STYLE_NOTES,
    build_instructions,
)
from tools import AppointmentTools

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("voice-agent")

# Per-stage latency lands here as JSONL, one row per metric. The dashboard
# (dashboard/build_dashboard.py) reads this to colour-code each call.
METRICS_LOG = Path(__file__).parent / "logs" / "metrics.jsonl"

# Confirmation phrase spoken the moment we switch language, IN that language.
# These MUST exist for every supported language -- see set_language for why.
CONFIRMATIONS: dict[str, str] = {
    "en": "Perfect, we'll continue in English.",
    "hi": "ठीक है, अब हम हिंदी में बात करेंगे।",
    "ta": "சரி, இனி நாம் தமிழில் பேசுவோம்.",
    "te": "సరే, ఇప్పటి నుండి మనం తెలుగులో మాట్లాడుకుందాం.",
    "kn": "ಸರಿ, ಇನ್ನು ನಾವು ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡೋಣ.",
    "ml": "ശരി, ഇനി നമുക്ക് മലയാളത്തിൽ സംസാരിക്കാം.",
}


# --- pipeline wiring ---------------------------------------------------------
def _build_session(language: str) -> AgentSession:
    """Wire the whole cascade for a starting language and return the session.

    Silero VAD + Sarvam STT/TTS locked to `language`, OpenAI LLM, Maya's tools,
    and tight endpointing. The session owns the tools and default pipeline;
    each LangAgent later overrides only STT + TTS to relock the language.
    """
    bcp47 = BCP47[language]
    return AgentSession(
        vad=silero.VAD.load(
            min_silence_duration=VAD_MIN_SILENCE_S,
            sample_rate=AUDIO_SAMPLE_RATE,
        ),
        stt=sarvam.STT(
            model=SARVAM_STT_MODEL,       # saaras:v3
            mode="codemix",               # keep English words spoken mid-sentence
            language=bcp47,
            sample_rate=AUDIO_SAMPLE_RATE,  # 8 kHz telephony
        ),
        llm=openai.LLM(
            model=OPENAI_LLM_MODEL,        # gpt-4.1-mini
            temperature=OPENAI_TEMPERATURE,
            max_completion_tokens=MAX_TOKENS,  # cap reply length -> lower latency
        ),
        tts=sarvam.TTS(
            model=SARVAM_TTS_MODEL,        # bulbul:v3
            target_language_code=bcp47,
            speaker=SARVAM_TTS_VOICE,      # "simran"
        ),
        tools=AppointmentTools().to_tools(),
        min_endpointing_delay=MIN_ENDPOINTING_DELAY,  # 0.15 s
        max_endpointing_delay=MAX_ENDPOINTING_DELAY,  # 1.0 s
    )


# --- agents ------------------------------------------------------------------
GREETER_INSTRUCTIONS = (
    HOT_PERSONA
    + "\n\nYou are greeting the caller in English. Listen for the language they "
    "speak or ask for. The moment you know it, call the set_language tool with the "
    "code (en, hi, ta, te, kn, ml). Do not dive into property questions before the "
    "language is set."
)


class GreeterAgent(Agent):
    """Greets the caller in English and detects their language."""

    def __init__(self) -> None:
        super().__init__(instructions=GREETER_INSTRUCTIONS)

    @function_tool
    async def set_language(self, context: RunContext, language: str) -> None:
        """Switch the whole conversation to the caller's preferred language.

        Args:
            language: one of en, hi, ta, te, kn, ml.
        """
        code = language.strip().lower()
        if code not in SUPPORTED_LANGUAGES:
            # Don't swap on an unknown code -- tell the LLM so it can re-ask.
            return f"Language '{language}' is not supported. Supported: {', '.join(SUPPORTED_LANGUAGES)}."

        # ---------------------------------------------------------------------
        # WHY we speak BEFORE swapping (do NOT reorder):
        # session.update_agent() swaps the active agent SILENTLY -- the new
        # agent does NOT automatically say anything. If we swap first and expect
        # the new LangAgent to greet, the call goes to DEAD AIR. That was a real,
        # painful production bug. So we emit the confirmation on the CURRENT
        # session first, THEN swap.
        # ---------------------------------------------------------------------
        await context.session.say(CONFIRMATIONS[code])
        context.session.update_agent(LangAgent(code))
        # We already voiced the confirmation, so return nothing (no extra reply).
        return None


class LangAgent(Agent):
    """One agent parameterised by language code; STT + TTS locked to it."""

    def __init__(self, code: str) -> None:
        bcp47 = BCP47[code]
        super().__init__(
            instructions=build_instructions(code, STYLE_NOTES[code]),
            # Override the session's STT/TTS to relock the language for this agent.
            stt=sarvam.STT(
                model=SARVAM_STT_MODEL,
                mode="codemix",
                language=bcp47,
                sample_rate=AUDIO_SAMPLE_RATE,
            ),
            tts=sarvam.TTS(
                model=SARVAM_TTS_MODEL,
                target_language_code=bcp47,
                speaker=SARVAM_TTS_VOICE,
            ),
        )
        self.code = code


# --- metrics -> JSONL --------------------------------------------------------
def _make_metrics_handler(call_id: str):
    """Build a metrics_collected handler that logs per-stage latency as JSONL."""

    def _on_metrics(ev: MetricsCollectedEvent) -> None:
        m = ev.metrics
        # Pull the one latency number that matters per stage.
        if isinstance(m, metrics.EOUMetrics):
            row = {"stage": "eou", "seconds": m.end_of_utterance_delay, "speech_id": m.speech_id}
        elif isinstance(m, metrics.STTMetrics):
            row = {"stage": "stt", "seconds": m.duration}
        elif isinstance(m, metrics.LLMMetrics):
            row = {"stage": "llm_ttft", "seconds": m.ttft, "speech_id": m.speech_id}
        elif isinstance(m, metrics.TTSMetrics):
            row = {"stage": "tts_ttfb", "seconds": m.ttfb, "speech_id": m.speech_id}
        else:
            return

        row["call_id"] = call_id
        row["ts"] = time.time()
        try:
            METRICS_LOG.parent.mkdir(parents=True, exist_ok=True)
            with METRICS_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:  # never let metrics logging break a live call
            log.exception("failed to write metrics row")
        metrics.log_metrics(m)  # also to the console log

    return _on_metrics


# --- entrypoint --------------------------------------------------------------
async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    session = _build_session(DEFAULT_LANGUAGE)
    session.on("metrics_collected", _make_metrics_handler(ctx.room.name))

    await session.start(agent=GreeterAgent(), room=ctx.room)

    # Speak the opening greeting. update_agent (on language switch) is silent, but
    # the FIRST agent must be told to greet too -- so we say it explicitly here.
    await session.say(GREETINGS[DEFAULT_LANGUAGE])


if __name__ == "__main__":
    agents.cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=os.getenv("AGENT_NAME", "maya"),
        )
    )
