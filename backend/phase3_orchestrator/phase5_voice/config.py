import os

from dotenv import load_dotenv

# Project root .env (same resolution as api.py: phase3_orchestrator/../../.env)
_root_env = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
)
load_dotenv(dotenv_path=_root_env)


def get_sarvam_api_key() -> str:
    key = os.getenv("SARVAM_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "SARVAM_API_KEY is not set. Add it to your environment or .env file."
        )
    return key


def get_voice_settings() -> dict:
    return {
        "stt_model": os.getenv("SARVAM_STT_MODEL", "saaras:v3").strip() or "saaras:v3",
        "tts_model": os.getenv("SARVAM_TTS_MODEL", "bulbul:v3").strip() or "bulbul:v3",
        "tts_voice_id": os.getenv("SARVAM_TTS_VOICE_ID", "ritu").strip() or "ritu",
        "language": os.getenv("SARVAM_LANGUAGE", "en-IN").strip() or "en-IN",
        "sample_rate": int(os.getenv("AUDIO_SAMPLE_RATE", "16000")),
        "encoding": os.getenv("AUDIO_ENCODING", "linear16").strip() or "linear16",
        "channels": int(os.getenv("AUDIO_CHANNELS", "1")),
        "fillers_enabled": os.getenv("VOICE_FILLERS_ENABLED", "true").lower() == "true",
        "ui_streaming_enabled": os.getenv("VOICE_UI_STREAMING_ENABLED", "true").lower()
        == "true",
    }
