import React, { useState, useEffect, useRef } from "react";
import { Sparkles, Server, CheckCircle2, RefreshCw, Layers } from "lucide-react";

const API_BASE = import.meta.env.DEV
  ? ''
  : (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8002').replace(/\/$/, '');

async function fetchWithTimeout(url, options = {}, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    return res;
  } finally {
    clearTimeout(timer);
  }
}

export default function FullScreenLoader({ onComplete }) {
  const [step, setStep] = useState(0);
  const [statusText, setStatusText] = useState("Checking cluster status...");
  
  const hasTriggeredRef = useRef(false);
  const cooldownRef = useRef(false);

  useEffect(() => {
    let pollingInterval;

    const checkStatus = async () => {
      try {
        const res = await fetchWithTimeout(`${API_BASE}/api/system/status`);
        if (!res.ok) return;
        
        const status = await res.json();
        
        const allReady = status.has_data;
        const anyRunning = status.is_running;

        // If everything is ready and nothing is running, we're done!
        if (allReady && !anyRunning) {
          if (pollingInterval) clearInterval(pollingInterval);
          onComplete();
          return;
        }

        // Update UI Steps based on progress
        if (!status.has_data && status.phase1_running && status.factsheets_running) {
          setStep(1);
          setStatusText("Processing 350+ reviews and scraping factsheets...");
        } else if (!status.has_data && status.phase1_running) {
          setStep(1);
          setStatusText("Classifying app reviews using Groq LLM...");
        } else if (!status.has_data && status.factsheets_running) {
          setStep(2);
          setStatusText("Generating factsheet embeddings via Gemini...");
        } else if (status.has_data && !status.definitions_running && !cooldownRef.current) {
          // Wait! If has_data is somehow true but we are doing a cooldown, the proxy handles factsheets vs definitions.
          // The proxy says `has_data` is false until both fs and df have `last_refreshed`.
        }
        
        // Let's refine the step logic based on the proxy response
        if (!status.has_data && status.factsheets_running && status.phase1_running) {
            setStep(1);
            setStatusText("Processing 350+ reviews and scraping factsheets...");
        } else if (!status.has_data && !status.factsheets_running && !status.definitions_running && hasTriggeredRef.current && !cooldownRef.current) {
            // Factsheets might be done, but definitions not yet started because of the cooldown
            setStep(3);
            setStatusText("Factsheets complete. Cooling down for 15s...");
        } else if (status.definitions_running) {
            setStep(4);
            setStatusText("Indexing definition embeddings...");
        } else if (allReady && anyRunning) {
            setStep(4);
            setStatusText("Finalizing intelligence pipelines...");
        }

        // Trigger Pipelines if empty and not triggered yet
        if (!hasTriggeredRef.current && !allReady && !anyRunning) {
          hasTriggeredRef.current = true;
          setStep(1);
          setStatusText("Waking up AI agents...");
          
          fetchWithTimeout(`${API_BASE}/api/system/refresh`, { method: "POST" }).catch(() => {});
        }

        // Trigger Definitions sequentially after 15s cooldown
        // If factsheets is NOT running, and definitions is NOT running, and we HAVE triggered the initial refresh,
        // and we haven't started the cooldown yet...
        // Wait, how do we know factsheets finished? If factsheets_running is false, but we still don't have full data.
        if (hasTriggeredRef.current && !status.factsheets_running && !status.definitions_running && !status.has_data && !cooldownRef.current) {
          // It could be that the initial `/api/system/refresh` hasn't fully registered in the backend yet,
          // so `factsheets_running` is still false for a split second. We should wait at least 5 seconds before assuming it finished.
          // For simplicity, if we triggered it, and it's not running, we start the 15s cooldown.
          cooldownRef.current = true;
          setStep(3);
          setStatusText("Cooling down API rate limits (15s)...");
          
          setTimeout(() => {
            fetchWithTimeout(`${API_BASE}/api/system/refresh/definitions`, { method: "POST" }).catch(() => {});
          }, 15000);
        }

      } catch (err) {
        console.error("Global loader status check failed", err);
      }
    };

    checkStatus();
    pollingInterval = setInterval(checkStatus, 5000);

    return () => clearInterval(pollingInterval);
  }, [onComplete]);

  return (
    <div className="fixed inset-0 z-[9999] bg-[#0A0A0A] flex flex-col items-center justify-center overflow-hidden">
      {/* Background Grid & Glow */}
      <div 
        style={{
            backgroundImage: `linear-gradient(to right, #ffffff05 1px, transparent 1px), linear-gradient(to bottom, #ffffff05 1px, transparent 1px)`,
            backgroundSize: `4rem 4rem`,
            maskImage: `radial-gradient(ellipse 60% 60% at 50% 50%, #000 70%, transparent 100%)`,
            WebkitMaskImage: `radial-gradient(ellipse 60% 60% at 50% 50%, #000 70%, transparent 100%)`
        }}
        className="absolute inset-0" 
      />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-[#00ff88]/10 rounded-full blur-[120px] opacity-50" />

      <div className="relative z-10 flex flex-col items-center max-w-md w-full px-6">
        {/* Brand Header */}
        <div className="flex items-center gap-2 mb-16">
          <Layers className="text-[#00ff88] w-5 h-5" />
          <span className="text-white/80 font-semibold tracking-wide text-sm" style={{ fontFamily: 'sans-serif' }}>User Portal</span>
        </div>

        {/* Central Spinner */}
        <div className="relative w-32 h-32 mb-12 flex items-center justify-center">
          <div className="absolute inset-0 rounded-full border-2 border-white/5" />
          <div className="absolute inset-0 rounded-full border-2 border-t-[#00ff88] border-r-[#00ff88] border-b-transparent border-l-transparent animate-spin" />
          <div className="absolute inset-2 rounded-full bg-[#00ff88]/5 backdrop-blur-sm border border-[#00ff88]/20 flex items-center justify-center">
            <Sparkles className="text-[#00ff88] w-8 h-8 animate-pulse" strokeWidth={1.5} />
          </div>
        </div>

        {/* Typography */}
        <div className="text-center mb-12" style={{ fontFamily: 'sans-serif' }}>
          <div className="inline-block px-3 py-1 mb-4 rounded-full bg-[#00ff88]/10 border border-[#00ff88]/20 text-[#00ff88] text-[10px] font-black tracking-[0.2em] uppercase">
            System Boot
          </div>
          <h1 className="text-3xl font-bold text-white mb-3 tracking-tight">INITIALIZING WORKSPACE</h1>
          <p className="text-white/40 text-sm font-medium leading-relaxed max-w-sm mx-auto">
            Waking up cluster. This may take 2-3 minutes after a cold start to scrape and vectorize fresh data.
          </p>
        </div>

        {/* Status Card */}
        <div className="w-full bg-white/[0.02] border border-white/10 backdrop-blur-xl rounded-2xl p-4 flex items-center gap-4 mb-8" style={{ fontFamily: 'sans-serif' }}>
          <div className="w-12 h-12 rounded-xl bg-[#00ff88]/10 flex items-center justify-center text-[#00ff88] shrink-0">
            {step === 0 ? <Server size={20} /> : step === 4 ? <CheckCircle2 size={20} /> : <RefreshCw size={20} className="animate-spin" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-white text-sm font-bold truncate">Pipeline Status</div>
            <div className="text-white/50 text-xs font-medium truncate mt-0.5">{statusText}</div>
          </div>
        </div>

        {/* Progress Dots */}
        <div className="flex items-center gap-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className={`h-2 rounded-full transition-all duration-500 ${
                step === i ? "w-8 bg-[#00ff88] shadow-[0_0_10px_rgba(0,255,136,0.5)]" : 
                step > i ? "w-2 bg-[#00ff88]/50" : "w-2 bg-white/10"
              }`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
