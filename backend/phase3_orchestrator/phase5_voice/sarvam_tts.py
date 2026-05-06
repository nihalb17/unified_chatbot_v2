"""Streaming TTS via Sarvam WebSocket (Bulbul), MP3 chunks to the client."""

import asyncio
import base64
import json
import logging
import urllib.parse
from typing import TYPE_CHECKING, Optional

import websockets
import websockets.exceptions as wsexc
from starlette.websockets import WebSocketDisconnect

from phase5_voice.config import get_voice_settings

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)

TTS_URI_BASE = "wss://api.sarvam.ai/text-to-speech/ws"


def _tts_connect_uri() -> str:
    cfg = get_voice_settings()
    params = {
        "model": cfg["tts_model"],
        "send_completion_event": "true",
    }
    return f"{TTS_URI_BASE}?{urllib.parse.urlencode(params)}"


async def stream_tts_utterance(
    websocket: "WebSocket",
    api_key: str,
    text: str,
    hangup: Optional[asyncio.Event] = None,
    stream: bool = True,
    include_caption: bool = True,
) -> bool:
    """Send agent caption and stream Sarvam audio chunks. Returns False if client disconnected."""
    caption_text = (text or "").strip()
    speak_text = caption_text or " "
    # Caption must not be empty: UI and TTS both need a visible string (strip() would drop a lone filler space).
    if not caption_text:
        caption_text = "Here is the reply."

    try:
        if include_caption:
            logger.info("TTS: Synthesizing speech for text: %s", speak_text[:200])
            await websocket.send_json(
                {
                    "type": "agent_caption",
                    "text": caption_text,
                    "stream": stream,
                }
            )
        else:
            logger.info("TTS (Voice-only): Synthesizing speech for text: %s", speak_text[:200])
    except WebSocketDisconnect:
        return False
    except Exception:
        return False

    cfg = get_voice_settings()
    uri = _tts_connect_uri()
    headers = [("Api-Subscription-Key", api_key)]

    try:
        async with websockets.connect(
            uri,
            additional_headers=headers,
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        ) as tts_ws:
            tts_model = (cfg["tts_model"] or "bulbul:v2").strip()
            sample_rate = "24000" if "v3" in tts_model else "22050"
            config_msg = {
                "type": "config",
                "data": {
                    "speaker": cfg["tts_voice_id"],
                    "target_language_code": cfg["language"],
                    "speech_sample_rate": sample_rate,
                    "output_audio_codec": "mp3",
                    "output_audio_bitrate": "128k",
                },
            }
            await tts_ws.send(json.dumps(config_msg))
            await tts_ws.send(
                json.dumps({"type": "text", "data": {"text": speak_text}})
            )
            await tts_ws.send(json.dumps({"type": "flush"}))

            while True:
                if hangup and hangup.is_set():
                    return False

                raw = await tts_ws.recv()
                if isinstance(raw, bytes):
                    try:
                        b64 = base64.b64encode(raw).decode("ascii")
                        await websocket.send_json(
                            {
                                "type": "tts_audio",
                                "b64": b64,
                                "content_type": "audio/mpeg",
                            }
                        )
                    except Exception:
                        return False
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.error(
                        "TTS: invalid JSON from Sarvam: %s",
                        raw[:500] if raw else "",
                    )
                    try:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": "Voice service returned invalid data.",
                            }
                        )
                    except Exception:
                        pass
                    return False
                mtype = msg.get("type")
                data = msg.get("data") or {}

                if mtype == "audio":
                    try:
                        await websocket.send_json(
                            {
                                "type": "tts_audio",
                                "b64": data.get("audio"),
                                "content_type": data.get(
                                    "content_type", "audio/mpeg"
                                ),
                            }
                        )
                    except Exception:
                        return False
                elif mtype == "event":
                    if data.get("event_type") == "final":
                        return True
                elif mtype == "error":
                    err = data.get("message") or "Text-to-speech failed."
                    logger.error("Sarvam TTS error: %s", msg)
                    try:
                        await websocket.send_json(
                            {"type": "error", "message": err}
                        )
                    except Exception:
                        pass
                    return False
    except wsexc.InvalidStatus as exc:
        logger.error("Sarvam TTS WebSocket rejected: %s", exc)
        hint = (
            "Check SARVAM_API_KEY, plan access, and that TTS is enabled for your account."
        )
        try:
            await websocket.send_json(
                {"type": "error", "message": f"{exc}. {hint}"}
            )
        except Exception:
            pass
        return False
    except (wsexc.InvalidHandshake, wsexc.SecurityError) as exc:
        logger.error("Sarvam TTS handshake failed: %s", exc)
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"Voice connection failed: {exc}.",
                }
            )
        except Exception:
            pass
        return False
    except (OSError, TimeoutError, asyncio.TimeoutError) as exc:
        logger.error("Sarvam TTS network error: %s", exc)
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"Could not reach voice service: {exc}.",
                }
            )
        except Exception:
            pass
        return False
    except wsexc.ConnectionClosed as exc:
        logger.error("Sarvam TTS connection closed unexpectedly: %s", exc)
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "Voice service closed the connection.",
                }
            )
        except Exception:
            pass
        return False
    except Exception as exc:
        logger.exception("Raw TTS session failed")
        detail = (str(exc) or type(exc).__name__).strip()[:280]
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"Voice synthesis failed: {detail}.",
                }
            )
        except Exception:
            pass
        return False
