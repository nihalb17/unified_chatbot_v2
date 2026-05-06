"""Streaming STT via Sarvam WebSocket (Saaras v3), 16 kHz mono PCM in WAV payloads."""

import asyncio
import base64
import json
import logging
import struct
import urllib.parse
from collections.abc import Awaitable, Callable
from typing import Any, Optional

import websockets

from phase5_voice.config import get_voice_settings

logger = logging.getLogger(__name__)

STT_URI_BASE = "wss://api.sarvam.ai/speech-to-text/ws"

_STT_SEND_TIMEOUT_S = 15.0
_STT_RECV_AFTER_CLOSE_S = 1.0
_STT_UTTERANCE_DEADLINE_S = 60.0


def _pcm_s16le_to_wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    """Sarvam accepts encoding=audio/wav; each payload must be a valid WAV (header + PCM)."""
    n = len(pcm)
    if n == 0:
        return b""
    byte_rate = sample_rate * 2
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + n,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        byte_rate,
        2,
        16,
        b"data",
        n,
    )
    return header + pcm


def _stt_connect_uri() -> str:
    cfg = get_voice_settings()
    params = {
        "language-code": cfg["language"],
        "model": cfg["stt_model"],
        "mode": "transcribe",
        "sample_rate": str(cfg["sample_rate"]),
        "high_vad_sensitivity": "true",
        "vad_signals": "true",
        "flush_signal": "true",
        "input_audio_codec": "wav",
    }
    return f"{STT_URI_BASE}?{urllib.parse.urlencode(params)}"


async def collect_utterance_transcript(
    api_key: str,
    pcm_queue: asyncio.Queue,
    hangup: asyncio.Event,
    *,
    use_server_vad: bool = False,
    on_transcript: Optional[Callable[[str], Awaitable[None] | None]] = None,
) -> str:
    """Forward microphone PCM to Sarvam until utterance is closed, then return transcript."""
    uri = _stt_connect_uri()
    cfg = get_voice_settings()
    headers = [("Api-Subscription-Key", api_key)]

    state: dict[str, Any] = {
        "transcript": "",
        "end_speech": False,
        "utterance_closed": False,
    }
    done = asyncio.Event()

    async def receiver(ws: Any) -> None:
        try:
            while not done.is_set():
                try:
                    recv_to = (
                        _STT_RECV_AFTER_CLOSE_S
                        if state["utterance_closed"]
                        else 2.0
                    )
                    raw = await asyncio.wait_for(ws.recv(), timeout=recv_to)
                except TimeoutError:
                    if state["utterance_closed"]:
                        logger.debug("STT: no more server messages after flush; finishing")
                        break
                    continue

                msg = json.loads(raw)
                mtype = msg.get("type")
                data = msg.get("data") or {}

                if mtype == "error":
                    err = data.get("error") or data.get("message") or str(data)
                    logger.error("Sarvam STT server error: %s", msg)
                    raise RuntimeError(f"Sarvam STT Error: {err}")

                if mtype == "events":
                    if data.get("signal_type") == "END_SPEECH":
                        state["end_speech"] = True
                        if use_server_vad and state["transcript"]:
                            done.set()

                if mtype == "data":
                    tr = (data.get("transcript") or "").strip()
                    if tr:
                        logger.debug("STT: received chunk: %s", tr)
                        current = state["transcript"]
                        if not current:
                            state["transcript"] = tr
                        elif tr.startswith(current):
                            state["transcript"] = tr
                        elif current.endswith(tr):
                            pass
                        else:
                            state["transcript"] = f"{current} {tr}"

                        if on_transcript:
                            try:
                                if asyncio.iscoroutinefunction(on_transcript):
                                    await on_transcript(state["transcript"])
                                else:
                                    on_transcript(state["transcript"])
                            except Exception as e:
                                logger.error("STT: error in transcript callback: %s", e)

                    if use_server_vad and state["end_speech"]:
                        done.set()
        except websockets.ConnectionClosed:
            logger.debug("STT: WebSocket connection closed gracefully")
        except Exception as e:
            logger.error("STT: receiver encountered error: %s", e)
        finally:
            done.set()

    async def sender(ws: Any) -> None:
        try:
            while not hangup.is_set() and not done.is_set():
                try:
                    chunk = await asyncio.wait_for(pcm_queue.get(), timeout=0.2)
                except TimeoutError:
                    continue
                if chunk is None:
                    logger.debug("STT: client signaled utterance end, sending flush")
                    state["utterance_closed"] = True
                    try:
                        await asyncio.wait_for(
                            ws.send(json.dumps({"type": "flush"})),
                            timeout=_STT_SEND_TIMEOUT_S,
                        )
                    except Exception as e:
                        logger.error("STT: flush send failed: %s", e)
                    break

                wav_bytes = _pcm_s16le_to_wav_bytes(chunk, int(cfg["sample_rate"]))
                payload = {
                    "audio": {
                        "data": base64.b64encode(wav_bytes).decode("ascii"),
                        "sample_rate": int(cfg["sample_rate"]),
                        "encoding": "audio/wav",
                    }
                }
                try:
                    await asyncio.wait_for(
                        ws.send(json.dumps(payload)), timeout=_STT_SEND_TIMEOUT_S
                    )
                except Exception as e:
                    logger.error("STT: send failed: %s", e)
                    break
        finally:
            if not state["utterance_closed"]:
                try:
                    await ws.send(json.dumps({"type": "flush"}))
                except Exception:
                    pass

    try:
        async with websockets.connect(
            uri,
            additional_headers=headers,
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            recv_task = asyncio.create_task(receiver(ws))
            send_task = asyncio.create_task(sender(ws))
            try:
                await asyncio.wait_for(done.wait(), timeout=_STT_UTTERANCE_DEADLINE_S)
            except TimeoutError:
                logger.warning("STT: timed out waiting for transcript")
            finally:
                send_task.cancel()
                try:
                    await send_task
                except asyncio.CancelledError:
                    pass
                recv_task.cancel()
                try:
                    await recv_task
                except asyncio.CancelledError:
                    pass
    except Exception:
        logger.exception("STT session failed")
        return ""

    return state["transcript"].strip()
