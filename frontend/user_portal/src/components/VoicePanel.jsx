/* eslint-disable react-hooks/set-state-in-effect -- WebSocket lifecycle resets phase on disable/teardown */
import { useRef, useState, useEffect, useCallback } from 'react';
import { Mic } from 'lucide-react';
import { voiceWebSocketUrl } from '../voiceApi';
import './VoicePanel.css';

function floatTo16BitPCM(f32) {
  const out = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

function downsample(f32, inRate, outRate) {
  if (inRate === outRate) return f32;
  const ratio = inRate / outRate;
  const n = Math.max(1, Math.floor(f32.length / ratio));
  const o = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    o[i] = f32[Math.min(Math.floor(i * ratio), f32.length - 1)] || 0;
  }
  return o;
}

function i16ToB64(i16) {
  const u8 = new Uint8Array(i16.buffer);
  let bin = '';
  for (let i = 0; i < u8.length; i++) bin += String.fromCharCode(u8[i]);
  return btoa(bin);
}

const RECORDING_MAX_MS = 120_000;

/**
 * Push-to-talk voice footer: WebSocket to backend Sarvam bridge.
 */
export default function VoicePanel({
  sessionId,
  disabled = false,
  /** When false, do not open the WebSocket yet (e.g. wait for welcome typewriter in chat). */
  connectEnabled = true,
  voiceStartedWithHistory = false,
  onUserTranscript,
  onAssistantMessage,
  onVoiceCallComplete,
}) {
  const [phase, setPhase] = useState('connecting');
  const [hint, setHint] = useState('');
  const [recordMs, setRecordMs] = useState(0);
  const [liveTranscript, setLiveTranscript] = useState('');

  const wsRef = useRef(null);
  const recordingRef = useRef(false);
  const skipWelcomeCaptionRef = useRef(!voiceStartedWithHistory);
  const sessionDoneRef = useRef(false);
  const pendingCallEndRef = useRef(null);
  const audioCtxRef = useRef(null);
  const micNodesRef = useRef(null);
  const recordTickRef = useRef(null);
  const recordStartRef = useRef(null);
  const maxRecordTimerRef = useRef(null);
  const inboundChainRef = useRef(Promise.resolve());
  const onMessageRef = useRef(null);
  const audioElRef = useRef(null);
  const ttsChunksRef = useRef([]);
  const ttsContentTypeRef = useRef('audio/mpeg');
  const activeBlobUrlRef = useRef(null);

  const stopMic = useCallback(() => {
    if (maxRecordTimerRef.current != null) {
      clearTimeout(maxRecordTimerRef.current);
      maxRecordTimerRef.current = null;
    }
    recordingRef.current = false;
    const nodes = micNodesRef.current;
    if (nodes) {
      try {
        nodes.proc.disconnect();
        nodes.src.disconnect();
        nodes.stream.getTracks().forEach((t) => t.stop());
      } catch {
        /* ignore disconnect errors */
      }
      micNodesRef.current = null;
    }
    if (recordTickRef.current != null) {
      clearInterval(recordTickRef.current);
      recordTickRef.current = null;
    }
    recordStartRef.current = null;
    setRecordMs(0);
  }, []);

  const teardownAudio = useCallback(() => {
    stopMic();
    if (audioElRef.current) {
      audioElRef.current.pause();
      audioElRef.current.src = '';
    }
    if (activeBlobUrlRef.current) {
      URL.revokeObjectURL(activeBlobUrlRef.current);
      activeBlobUrlRef.current = null;
    }
    ttsChunksRef.current = [];
    ttsContentTypeRef.current = 'audio/mpeg';
    try {
      audioCtxRef.current?.close();
    } catch {
      /* ignore */
    }
    audioCtxRef.current = null;
  }, [stopMic]);

  const ensureAudioCtx = useCallback(() => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new AudioContext();
    }
    return audioCtxRef.current;
  }, []);

  const base64ToUint8 = useCallback((b64) => {
    const raw = atob(b64);
    const u8 = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) u8[i] = raw.charCodeAt(i);
    return u8;
  }, []);

  const playBufferedTtsAndWait = useCallback(async () => {
    const el = audioElRef.current;
    if (!el) return;
    if (ttsChunksRef.current.length === 0) return;

    const chunkBytes = ttsChunksRef.current.map(base64ToUint8);
    const blob = new Blob(chunkBytes, { type: ttsContentTypeRef.current || 'audio/mpeg' });
    const url = URL.createObjectURL(blob);
    if (activeBlobUrlRef.current) {
      URL.revokeObjectURL(activeBlobUrlRef.current);
    }
    activeBlobUrlRef.current = url;
    el.src = url;
    ttsChunksRef.current = [];

    try {
      await el.play();
      await new Promise((resolve) => {
        el.onended = () => resolve();
      });
    } catch {
      if (activeBlobUrlRef.current) {
        URL.revokeObjectURL(activeBlobUrlRef.current);
        activeBlobUrlRef.current = null;
      }
      el.src = '';
      setHint('Audio blocked by browser. Please allow autoplay and try again.');
    } finally {
      el.onended = null;
      el.src = '';
    }
  }, [base64ToUint8]);

  const startMic = useCallback(
    async (ws) => {
      stopMic();
      setLiveTranscript('');
      try {
        ws.send(JSON.stringify({ type: 'recording_start' }));
      } catch {
        /* ignore disconnect errors */
      }
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true },
        });
      } catch {
        try {
          ws.send(JSON.stringify({ type: 'utterance_end' }));
        } catch {
        /* ignore disconnect errors */
      }
        throw new Error('microphone denied');
      }
      const ctx = ensureAudioCtx();
      await ctx.resume();
      const src = ctx.createMediaStreamSource(stream);
      const proc = ctx.createScriptProcessor(4096, 1, 1);
      const mute = ctx.createGain();
      mute.gain.value = 0;
      proc.onaudioprocess = (e) => {
        if (!recordingRef.current || !ws || ws.readyState !== WebSocket.OPEN) return;
        const input = e.inputBuffer.getChannelData(0);
        const down = downsample(input, ctx.sampleRate, 16000);
        const pcm = floatTo16BitPCM(down);
        try {
          ws.send(JSON.stringify({ type: 'pcm_chunk', b64: i16ToB64(pcm) }));
        } catch {
        /* ignore disconnect errors */
      }
      };
      src.connect(proc);
      proc.connect(mute);
      mute.connect(ctx.destination);
      micNodesRef.current = { proc, src, stream };
      recordingRef.current = true;
      recordStartRef.current = Date.now();
      setRecordMs(0);
      recordTickRef.current = setInterval(() => {
        if (recordStartRef.current) {
          setRecordMs(Date.now() - recordStartRef.current);
        }
      }, 100);
      maxRecordTimerRef.current = setTimeout(() => {
        if (!recordingRef.current) return;
        const sock = wsRef.current;
        stopMic();
        if (sock && sock.readyState === WebSocket.OPEN) {
          try {
            sock.send(JSON.stringify({ type: 'utterance_end' }));
          } catch {
        /* ignore disconnect errors */
      }
        }
        setPhase('processing');
        setHint('');
      }, RECORDING_MAX_MS);
    },
    [ensureAudioCtx, stopMic]
  );

  const finishRecordingTurn = useCallback(() => {
    const ws = wsRef.current;
    stopMic();
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: 'utterance_end' }));
      } catch {
        /* ignore disconnect errors */
      }
    }
    setPhase('processing');
    setHint('');
  }, [stopMic]);

  const closeWs = useCallback(() => {
    stopMic();
    const w = wsRef.current;
    wsRef.current = null;
    if (w && w.readyState === WebSocket.OPEN) {
      try {
        w.send(JSON.stringify({ type: 'hangup' }));
      } catch {
        /* ignore disconnect errors */
      }
      w.close();
    }
  }, [stopMic]);

  const handleMessage = useCallback(
    async (ev) => {
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      const t = msg.type;
      if (t === 'error') {
        setHint(msg.message || 'Error');
        setPhase('error');
        stopMic();
        const w = wsRef.current;
        wsRef.current = null;
        if (w) {
          try {
            w.close();
          } catch {
        /* ignore disconnect errors */
      }
        }
        return;
      }
      if (t === 'user_transcript') {
        const text = (msg.text || '').trim();
        if (text) {
          if (msg.partial) {
            setLiveTranscript(text);
          } else {
            setLiveTranscript('');
            onUserTranscript?.(text);
          }
        }
        return;
      }
      if (t === 'agent_caption') {
        ttsChunksRef.current = [];
        ttsContentTypeRef.current = 'audio/mpeg';
        if (audioElRef.current) {
          audioElRef.current.pause();
          audioElRef.current.src = '';
        }
        if (activeBlobUrlRef.current) {
          URL.revokeObjectURL(activeBlobUrlRef.current);
          activeBlobUrlRef.current = null;
        }
        const text = (msg.text || '').trim();
        if (text) {
          if (skipWelcomeCaptionRef.current) {
            skipWelcomeCaptionRef.current = false;
          } else {
            onAssistantMessage?.(text, msg.stream);
          }
        }
        setPhase('speaking');
        setHint('');
        return;
      }
      if (t === 'tts_audio') {
        ttsChunksRef.current.push(msg.b64);
        ttsContentTypeRef.current = msg.content_type || 'audio/mpeg';
        return;
      }
      if (t === 'tts_done') {
        await playBufferedTtsAndWait();
        if (sessionDoneRef.current) return;
        const pending = pendingCallEndRef.current;
        if (pending) {
          pendingCallEndRef.current = null;
          sessionDoneRef.current = true;
          onVoiceCallComplete?.(pending);
          setPhase('ended');
          setHint('');
          closeWs();
          return;
        }
        setHint('Tap to talk');
        setPhase('ready');
        return;
      }
      if (t === 'phase') {
        if (msg.phase === 'processing') {
          stopMic();
          setHint('');
          setPhase('processing');
        }
        return;
      }
      if (t === 'call_ended') {
        stopMic();
        pendingCallEndRef.current = {
          action: msg.action,
          headline: msg.headline || 'Session ended',
          message: msg.message || '',
          booking_code: msg.booking_code,
          scheduled_display: msg.scheduled_display,
          banner_text: msg.banner_text,
        };
      }
    },
    [playBufferedTtsAndWait, stopMic, closeWs, onUserTranscript, onAssistantMessage, onVoiceCallComplete]
  );

  useEffect(() => {
    onMessageRef.current = handleMessage;
  }, [handleMessage]);

  useEffect(() => {
    skipWelcomeCaptionRef.current = !voiceStartedWithHistory;
  }, [voiceStartedWithHistory]);

  useEffect(() => {
    if (disabled || !sessionId) {
      /* Voice UI hidden: close socket and reset local phase (reference VoicePanel lifecycle). */
      closeWs();
      teardownAudio();
      setPhase('ended');
      return;
    }

    if (!connectEnabled) {
      closeWs();
      teardownAudio();
      setPhase('waiting_intro');
      setHint('Finishing the welcome on screen…');
      return;
    }

    const teardownRef = { current: false };

    sessionDoneRef.current = false;
    pendingCallEndRef.current = null;
    setPhase('connecting');
    setHint('Connecting…');

    const url = voiceWebSocketUrl(sessionId);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      if (teardownRef.current || wsRef.current !== ws) return;
      const fn = onMessageRef.current;
      if (!fn) return;
      inboundChainRef.current = inboundChainRef.current
        .then(() => fn(ev))
        .catch(() => {});
    };
    ws.onerror = () => {
      if (teardownRef.current) return;
      if (wsRef.current !== ws) return;
      setHint('Connection error. Is the API running (port 8002) and Vite proxy configured?');
      setPhase('error');
      wsRef.current = null;
      stopMic();
    };
    ws.onclose = () => {
      if (teardownRef.current) return;
      if (wsRef.current !== ws) return;
      wsRef.current = null;
      stopMic();
    };
    ws.onopen = () => {
      if (teardownRef.current || wsRef.current !== ws) return;
      try {
        ws.send(JSON.stringify({ type: 'begin' }));
      } catch {
        /* ignore disconnect errors */
      }
    };

    return () => {
      teardownRef.current = true;
      inboundChainRef.current = Promise.resolve();
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        try {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'hangup' }));
          }
        } catch {
        /* ignore disconnect errors */
      }
        ws.close();
      }
      stopMic();
      teardownAudio();
    };
  }, [disabled, sessionId, connectEnabled, closeWs, stopMic, teardownAudio]);

  const onPttClick = async () => {
    if (
      disabled ||
      !connectEnabled ||
      phase === 'ended' ||
      phase === 'error' ||
      phase === 'connecting' ||
      phase === 'waiting_intro'
    ) {
      return;
    }
    if (phase === 'speaking' || phase === 'processing') return;

    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setHint('Reconnecting…');
      return;
    }

    if (phase === 'ready') {
      try {
        await startMic(ws);
        setPhase('recording');
        setHint('Tap to stop');
      } catch {
        setHint('Microphone permission required');
      }
      return;
    }

    if (phase === 'recording') {
      finishRecordingTurn();
    }
  };

  const recordSec = Math.floor(recordMs / 1000);
  const mm = String(Math.floor(recordSec / 60)).padStart(2, '0');
  const ss = String(recordSec % 60).padStart(2, '0');

  const micDisabled =
    disabled ||
    !connectEnabled ||
    phase === 'waiting_intro' ||
    phase === 'connecting' ||
    phase === 'speaking' ||
    phase === 'processing' ||
    phase === 'ended' ||
    phase === 'error';

  const pttClass =
    'voice-ptt ' +
    (phase === 'recording' ? 'voice-ptt-recording ' : '') +
    (phase === 'processing' ? 'voice-ptt-processing ' : '') +
    (micDisabled ? 'voice-ptt-disabled' : '');

  return (
    <div className="voice-footer">
      <audio ref={audioElRef} style={{ display: 'none' }} />

      {phase === 'recording' || liveTranscript ? (
        <div className="voice-live-container">
          <div className="voice-rec-timer">
            {phase === 'recording' ? `Listening ${mm}:${ss}` : 'Processing...'}
          </div>
          {liveTranscript ? (
            <div className="voice-live-transcript">&ldquo;{liveTranscript}&rdquo;</div>
          ) : null}
        </div>
      ) : (
        <div className="voice-footer-hint">
          {hint ||
            (phase === 'ready'
              ? 'Tap to talk'
              : phase === 'waiting_intro'
                ? 'Finishing the welcome on screen…'
                : phase === 'connecting'
                  ? 'Connecting…'
                  : phase === 'processing'
                    ? 'Agent is thinking...'
                    : phase === 'ended'
                      ? ''
                      : '')}
        </div>
      )}

      {phase === 'processing' && !liveTranscript ? (
        <div className="voice-processing-spinner">
          <div className="dot-pulse" />
        </div>
      ) : null}

      {!disabled ? (
        <div className="voice-footer-mic-row">
          <button
            type="button"
            className={pttClass.trim()}
            onClick={onPttClick}
            disabled={micDisabled}
            aria-label={phase === 'recording' ? 'Stop recording' : 'Start recording'}
          >
            <span className="voice-ptt-icon">
              <Mic size={28} strokeWidth={2} />
            </span>
          </button>
        </div>
      ) : null}
    </div>
  );
}
