import React, { useState, useEffect, useRef } from 'react';

const API_BASE = import.meta.env.DEV
  ? ''
  : (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8002').replace(/\/$/, '');

async function fetchWithTimeout(url, options = {}, timeoutMs = 10000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

const GREEN = '#22c55e';
const GREEN_DIM = 'rgba(34,197,94,0.15)';
const GREEN_BORDER = 'rgba(34,197,94,0.25)';

const keyframes = `
  @keyframes spin {
    from { transform: rotate(0deg); }
    to   { transform: rotate(360deg); }
  }
  @keyframes pulse-glow {
    0%, 100% { opacity: 0.7; }
    50%       { opacity: 1; }
  }
  @keyframes dot-bounce {
    0%, 100% { transform: translateY(0); }
    50%       { transform: translateY(-4px); }
  }
`;

function SpinnerRing() {
  return (
    <div style={{
      position: 'relative',
      width: 128,
      height: 128,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: 40,
    }}>
      {/* Outer static ring */}
      <div style={{
        position: 'absolute',
        inset: 0,
        borderRadius: '50%',
        border: '2px solid rgba(255,255,255,0.05)',
      }} />
      {/* Spinning arc */}
      <div style={{
        position: 'absolute',
        inset: 0,
        borderRadius: '50%',
        border: '2px solid transparent',
        borderTopColor: GREEN,
        borderRightColor: GREEN,
        animation: 'spin 1.2s linear infinite',
      }} />
      {/* Inner glowing circle */}
      <div style={{
        position: 'absolute',
        inset: 8,
        borderRadius: '50%',
        background: GREEN_DIM,
        border: `1px solid ${GREEN_BORDER}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        {/* Sparkle SVG */}
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke={GREEN} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
          style={{ animation: 'pulse-glow 2s ease-in-out infinite' }}>
          <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z"/>
          <path d="M5 17l.75 2.25L8 20l-2.25.75L5 23l-.75-2.25L2 20l2.25-.75L5 17z"/>
          <path d="M19 3l.5 1.5L21 5l-1.5.5L19 7l-.5-1.5L17 5l1.5-.5L19 3z"/>
        </svg>
      </div>
    </div>
  );
}

function StatusCard({ step, statusText }) {
  const isComplete = step >= 5;
  return (
    <div style={{
      width: '100%',
      background: 'rgba(255,255,255,0.02)',
      border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: 16,
      padding: '14px 18px',
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      marginBottom: 28,
    }}>
      <div style={{
        width: 46,
        height: 46,
        borderRadius: 12,
        background: GREEN_DIM,
        border: `1px solid ${GREEN_BORDER}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        color: GREEN,
      }}>
        {isComplete ? (
          /* Check icon */
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={GREEN} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        ) : step === 0 ? (
          /* Server icon */
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={GREEN} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>
            <rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>
            <line x1="6" y1="6" x2="6.01" y2="6"/>
            <line x1="6" y1="18" x2="6.01" y2="18"/>
          </svg>
        ) : (
          /* Spinning refresh icon */
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={GREEN} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            style={{ animation: 'spin 1.5s linear infinite' }}>
            <polyline points="23 4 23 10 17 10"/>
            <polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
          </svg>
        )}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ color: '#fff', fontSize: 14, fontWeight: 700, fontFamily: 'sans-serif', marginBottom: 3 }}>
          Pipeline Status
        </div>
        <div style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12, fontWeight: 500, fontFamily: 'sans-serif', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {statusText}
        </div>
      </div>
    </div>
  );
}

function ProgressDots({ step, total = 5 }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} style={{
          height: 8,
          borderRadius: 4,
          transition: 'all 0.5s ease',
          width: step === i ? 28 : 8,
          background: step === i
            ? GREEN
            : step > i
              ? 'rgba(34,197,94,0.4)'
              : 'rgba(255,255,255,0.1)',
          boxShadow: step === i ? `0 0 10px ${GREEN}80` : 'none',
        }} />
      ))}
    </div>
  );
}

const STEPS_TEXT = [
  "Checking cluster status...",
  "Waking up AI agents...",
  "Classifying reviews & scraping factsheets...",
  "Preparing to index definitions...",
  "Indexing definition embeddings...",
];

export default function FullScreenLoader({ onComplete }) {
  const [step, setStep] = useState(0);
  const [statusText, setStatusText] = useState(STEPS_TEXT[0]);

  const hasTriggeredInitialRef = useRef(false);
  const hasTriggeredDefinitionsRef = useRef(false);
  const factsheetsDoneTimestampRef = useRef(null);

  useEffect(() => {
    let pollingInterval;

    const checkStatus = async () => {
      try {
        const res = await fetchWithTimeout(`${API_BASE}/api/system/status`);
        if (!res.ok) return;
        const s = await res.json();

        const {
          has_data, is_running,
          cache_initialized,
          suggest_initial_refresh,
          suggest_definitions_refresh,
          phase1_ready, phase1_running,
          factsheets_ready, factsheets_running,
          definitions_ready, definitions_running,
        } = s;

        // ⏳ Backend cache not ready yet — wait silently
        if (!cache_initialized) {
          setStep(0);
          setStatusText("Checking cluster status...");
          return;
        }

        // ✅ All done
        if (has_data && !is_running) {
          clearInterval(pollingInterval);
          onComplete();
          return;
        }

        // 🔥 Backend suggests initial refresh (Cold Start)
        if (suggest_initial_refresh && !hasTriggeredInitialRef.current) {
          hasTriggeredInitialRef.current = true;
          setStep(1);
          setStatusText("Waking up AI agents...");
          fetchWithTimeout(`${API_BASE}/api/system/refresh`, { method: 'POST' }).catch(() => {});
          return;
        }

        // 📊 Update step label
        if (definitions_running) {
          setStep(4);
          setStatusText("Indexing definition embeddings...");
        } else if (phase1_running && factsheets_running) {
          setStep(2);
          setStatusText("Classifying 350+ reviews & scraping factsheets...");
        } else if (phase1_running) {
          setStep(2);
          setStatusText("Classifying app reviews using Groq LLM...");
        } else if (factsheets_running) {
          setStep(2);
          setStatusText("Generating factsheet embeddings via Gemini...");
        }

        // ⏳ Backend suggests definitions refresh (Sequential gap)
        if (suggest_definitions_refresh && !hasTriggeredDefinitionsRef.current) {
          if (factsheetsDoneTimestampRef.current === null) {
            factsheetsDoneTimestampRef.current = Date.now();
            setStep(3);
            setStatusText("Preparing to index definitions...");
          } else if (Date.now() - factsheetsDoneTimestampRef.current >= 8000) {
            hasTriggeredDefinitionsRef.current = true;
            fetchWithTimeout(`${API_BASE}/api/system/refresh/definitions`, { method: 'POST' }).catch(() => {});
            setStep(4);
            setStatusText("Indexing definition embeddings...");
          }
        }
      } catch (err) {
        console.error('[FullScreenLoader] Status check failed:', err);
      }
    };

    checkStatus();
    pollingInterval = setInterval(checkStatus, 5000);
    return () => clearInterval(pollingInterval);
  }, [onComplete]);

  return (
    <>
      <style>{keyframes}</style>
      <div style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: '#0A0A0A',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      }}>
        {/* Radial grid background */}
        <div style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: 'linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)',
          backgroundSize: '60px 60px',
          maskImage: 'radial-gradient(ellipse 70% 70% at 50% 50%, #000 60%, transparent 100%)',
          WebkitMaskImage: 'radial-gradient(ellipse 70% 70% at 50% 50%, #000 60%, transparent 100%)',
        }} />

        {/* Green glow blob */}
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: 480,
          height: 480,
          background: 'rgba(34,197,94,0.07)',
          borderRadius: '50%',
          filter: 'blur(100px)',
          pointerEvents: 'none',
        }} />

        {/* Content */}
        <div style={{
          position: 'relative',
          zIndex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          width: '100%',
          maxWidth: 420,
          padding: '0 24px',
        }}>
          {/* Brand row */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginBottom: 48,
          }}>
            {/* Layers icon */}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={GREEN} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="12 2 2 7 12 12 22 7 12 2"/>
              <polyline points="2 17 12 22 22 17"/>
              <polyline points="2 12 12 17 22 12"/>
            </svg>
            <span style={{ color: 'rgba(255,255,255,0.75)', fontWeight: 600, fontSize: 13, letterSpacing: '0.04em' }}>
              User Portal
            </span>
          </div>

          {/* Spinner */}
          <SpinnerRing />

          {/* Headline */}
          <div style={{ textAlign: 'center', marginBottom: 36 }}>
            <div style={{
              display: 'inline-block',
              padding: '4px 12px',
              borderRadius: 100,
              background: GREEN_DIM,
              border: `1px solid ${GREEN_BORDER}`,
              color: GREEN,
              fontSize: 10,
              fontWeight: 800,
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              marginBottom: 14,
            }}>
              System Boot
            </div>
            <h1 style={{
              color: '#ffffff',
              fontSize: 26,
              fontWeight: 800,
              letterSpacing: '-0.02em',
              margin: '0 0 10px',
              lineHeight: 1.2,
            }}>
              INITIALIZING WORKSPACE
            </h1>
            <p style={{
              color: 'rgba(255,255,255,0.38)',
              fontSize: 13,
              fontWeight: 500,
              lineHeight: 1.6,
              margin: 0,
              maxWidth: 320,
              marginLeft: 'auto',
              marginRight: 'auto',
            }}>
              Waking up cluster. This may take 2–3 minutes on a cold start to scrape and vectorize fresh data.
            </p>
          </div>

          {/* Status card */}
          <StatusCard step={step} statusText={statusText} />

          {/* Progress dots */}
          <ProgressDots step={step} total={STEPS_TEXT.length} />
        </div>
      </div>
    </>
  );
}
