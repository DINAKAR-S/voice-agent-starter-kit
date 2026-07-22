"""Central configuration for the voice-agent-starter-kit.

Everything the agent pipeline needs is read from environment variables here and
exposed as plain, typed module-level constants. Import from this module instead
of calling os.getenv() all over the codebase, so there is exactly one place that
maps env -> value and one place to change a default.

Defaults mirror `.env.example`. No secrets live in this file; missing secrets
simply fall back to obvious placeholders so the module still imports.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Load a local .env if present. In production the values come from the systemd
# EnvironmentFile instead, so this is a no-op there.
load_dotenv()


# --- LiveKit -----------------------------------------------------------------
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "wss://your-project.livekit.cloud")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "YOUR_LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "YOUR_LIVEKIT_API_SECRET")
SIP_URI = os.getenv("SIP_URI", "<your-project-id>.sip.livekit.cloud:5060")


# --- Sarvam AI (STT + TTS) ---------------------------------------------------
# The plugin reads SARVAM_API_KEY from the environment itself; we surface it here
# only so a missing key fails loudly and early rather than deep in the audio loop.
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "YOUR_SARVAM_API_KEY")
SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
# Sarvam's TTS constructor calls this the "speaker"; the env var is *_VOICE.
SARVAM_TTS_VOICE = os.getenv("SARVAM_TTS_VOICE", "simran")


# --- OpenAI (LLM) ------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
OPENAI_LLM_MODEL = os.getenv("OPENAI_LLM_MODEL", "gpt-4.1-mini")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.3"))
# Hard cap on reply length. Short replies = lower TTS/LLM latency on a phone call.
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "140"))


# --- Agent behaviour ---------------------------------------------------------
AGENT_NAME = os.getenv("AGENT_NAME", "maya")
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "en")
# Silero VAD minimum silence before end-of-utterance. Stored as ms in the env
# (matching .env.example) and converted to seconds for the plugin.
VAD_MIN_SILENCE_MS = int(os.getenv("VAD_MIN_SILENCE_MS", "150"))
VAD_MIN_SILENCE_S = VAD_MIN_SILENCE_MS / 1000.0

# Endpointing window (how long to wait for the caller to resume before treating
# the turn as finished). Tuned tight for snappy phone turns.
MIN_ENDPOINTING_DELAY = float(os.getenv("MIN_ENDPOINTING_DELAY", "0.15"))
MAX_ENDPOINTING_DELAY = float(os.getenv("MAX_ENDPOINTING_DELAY", "1.0"))

# Telephony sample rate. 8 kHz end-to-end is the latency recipe for phone audio.
AUDIO_SAMPLE_RATE = 8000


# --- Telephony / transfer ----------------------------------------------------
DEFAULT_TRANSFER_NUMBER = os.getenv("DEFAULT_TRANSFER_NUMBER", "+91XXXXXXXXXX")


# --- Language map ------------------------------------------------------------
# Every supported language -> its BCP-47 tag. Both Sarvam STT (`language`) and
# Sarvam TTS (`target_language_code`) are locked to one of these per call.
BCP47: dict[str, str] = {
    "en": "en-IN",
    "hi": "hi-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "kn": "kn-IN",
    "ml": "ml-IN",
}
SUPPORTED_LANGUAGES: list[str] = list(BCP47.keys())
