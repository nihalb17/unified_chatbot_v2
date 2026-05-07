"use client";

import React, { useState, useEffect, useRef } from "react";
import { Sparkles, Server, Database, CheckCircle2, RefreshCw, Layers } from "lucide-react";
import { cn } from "@/lib/utils";

const PHASE1_URL = process.env.NEXT_PUBLIC_PHASE1_URL || "http://localhost:8000";
const PHASE2_URL = process.env.NEXT_PUBLIC_PHASE2_URL || "http://localhost:8001";

/** Fetch with a timeout so the browser never hangs. */
async function fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs = 8000): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    return res;
  } finally {
    clearTimeout(timer);
  }
}

export default function GlobalColdStartLoader({ children }: { children: React.ReactNode }) {
  const [isInitializing, setIsInitializing] = useState(true);
  const [step, setStep] = useState(0);
  const [statusText, setStatusText] = useState("Checking cluster status...");
  
  const hasTriggeredRef = useRef(false);
  const cooldownRef = useRef(false);

  useEffect(() => {
    let pollingInterval: NodeJS.Timeout;

    const checkStatus = async () => {
      try {
        let phase1Ready = false;
        let phase1Running = false;
        let phase2FsReady = false;
        let phase2FsRunning = false;
        let phase2DfReady = false;
        let phase2DfRunning = false;

        // Check Phase 1
        try {
          const r1 = await fetchWithTimeout(`${PHASE1_URL}/api/reviews/themes`);
          const d1 = await r1.json();
          phase1Ready = (d1.themes && d1.themes.length > 0);
          
          const s1 = await fetchWithTimeout(`${PHASE1_URL}/api/reviews/status`);
          const sd1 = await s1.json();
          phase1Running = sd1.running;
        } catch (e) {
          console.error("Phase 1 check failed", e);
        }

        // Check Phase 2
        try {
          const r2 = await fetchWithTimeout(`${PHASE2_URL}/api/faqs/status`);
          const d2 = await r2.json();
          
          const fs = d2.factsheets || {};
          const df = d2.definitions || {};
          
          phase2FsReady = !!fs.last_refreshed;
          phase2FsRunning = fs.running;
          
          phase2DfReady = !!df.last_refreshed;
          phase2DfRunning = df.running;
        } catch (e) {
          console.error("Phase 2 check failed", e);
        }

        const allReady = phase1Ready && phase2FsReady && phase2DfReady;
        const anyRunning = phase1Running || phase2FsRunning || phase2DfRunning;

        // If everything is ready and nothing is running, we're done!
        if (allReady && !anyRunning) {
          setIsInitializing(false);
          if (pollingInterval) clearInterval(pollingInterval);
          return;
        }

        // Update UI Steps based on progress
        if (!phase1Ready && phase1Running && phase2FsRunning) {
          setStep(1);
          setStatusText("Processing 350+ reviews and scraping factsheets...");
        } else if (!phase1Ready && phase1Running) {
          setStep(1);
          setStatusText("Classifying app reviews using Groq LLM...");
        } else if (!phase2FsReady && phase2FsRunning) {
          setStep(2);
          setStatusText("Generating factsheet embeddings via Gemini...");
        } else if (phase1Ready && phase2FsReady && !phase2DfRunning && !phase2DfReady && !cooldownRef.current) {
          setStep(3);
          setStatusText("Factsheets complete. Preparing to index definitions...");
        } else if (phase2DfRunning) {
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
          
          if (!phase1Ready) {
            fetchWithTimeout(`${PHASE1_URL}/api/reviews/refresh`, { method: "POST" }).catch(() => {});
          }
          if (!phase2FsReady) {
            fetchWithTimeout(`${PHASE2_URL}/api/faqs/factsheets/refresh`, { method: "POST" }).catch(() => {});
          }
        }

        // Trigger Definitions sequentially after 15s cooldown
        if (hasTriggeredRef.current && phase2FsReady && !phase2FsRunning && !phase2DfReady && !phase2DfRunning && !cooldownRef.current) {
          cooldownRef.current = true;
          setStep(3);
          setStatusText("Preparing to index definitions...");
          
          setTimeout(() => {
            fetchWithTimeout(`${PHASE2_URL}/api/faqs/definitions/refresh`, { method: "POST" }).catch(() => {});
          }, 15000);
        }

      } catch (err) {
        console.error("Global loader status check failed", err);
      }
    };

    checkStatus();
    pollingInterval = setInterval(checkStatus, 5000);

    return () => clearInterval(pollingInterval);
  }, []);

  if (!isInitializing) {
    return <>{children}</>;
  }

  // Lovable App-Lens Glow Design
  return (
    <div className="fixed inset-0 z-[9999] bg-[#0A0A0A] flex flex-col items-center justify-center overflow-hidden">
      {/* Background Grid & Glow */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_60%_at_50%_50%,#000_70%,transparent_100%)]" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-neon-green/10 rounded-full blur-[120px] opacity-50" />

      <div className="relative z-10 flex flex-col items-center max-w-md w-full px-6">
        {/* Brand Header */}
        <div className="flex items-center gap-2 mb-16">
          <Layers className="text-neon-green w-5 h-5" />
          <span className="text-white/80 font-semibold tracking-wide text-sm">Internal Ops</span>
        </div>

        {/* Central Spinner */}
        <div className="relative w-32 h-32 mb-12 flex items-center justify-center">
          <div className="absolute inset-0 rounded-full border-2 border-white/5" />
          <div className="absolute inset-0 rounded-full border-2 border-t-neon-green border-r-neon-green border-b-transparent border-l-transparent animate-spin" />
          <div className="absolute inset-2 rounded-full bg-neon-green/5 backdrop-blur-sm border border-neon-green/20 flex items-center justify-center">
            <Sparkles className="text-neon-green w-8 h-8 animate-pulse" strokeWidth={1.5} />
          </div>
        </div>

        {/* Typography */}
        <div className="text-center mb-12">
          <div className="inline-block px-3 py-1 mb-4 rounded-full bg-neon-green/10 border border-neon-green/20 text-neon-green text-[10px] font-black tracking-[0.2em] uppercase">
            System Boot
          </div>
          <h1 className="text-3xl font-bold text-white mb-3 tracking-tight">INITIALIZING WORKSPACE</h1>
          <p className="text-white/40 text-sm font-medium leading-relaxed max-w-sm mx-auto">
            Waking up cluster. This may take 2-3 minutes after a cold start to scrape and vectorize fresh data.
          </p>
        </div>

        {/* Status Card */}
        <div className="w-full bg-white/[0.02] border border-white/10 backdrop-blur-xl rounded-2xl p-4 flex items-center gap-4 mb-8">
          <div className="w-12 h-12 rounded-xl bg-neon-green/10 flex items-center justify-center text-neon-green shrink-0">
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
              className={cn(
                "h-2 rounded-full transition-all duration-500",
                step === i ? "w-8 bg-neon-green shadow-[0_0_10px_rgba(34,197,94,0.5)]" : 
                step > i ? "w-2 bg-neon-green/50" : "w-2 bg-white/10"
              )}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
