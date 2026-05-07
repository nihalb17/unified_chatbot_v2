"use client";

import React, { useState, useEffect, useRef } from "react";
import { Sparkles, Server, CheckCircle2, RefreshCw, Layers } from "lucide-react";
import { cn } from "@/lib/utils";

const PHASE1_URL = process.env.NEXT_PUBLIC_PHASE1_URL || "http://localhost:8000";
const PHASE2_URL = process.env.NEXT_PUBLIC_PHASE2_URL || "http://localhost:8001";

async function fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs = 10000): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

const STEPS = [
  "Checking cluster status...",
  "Waking up AI agents...",
  "Classifying reviews & scraping factsheets...",
  "Preparing to index definitions...",
  "Indexing definitions...",
];

export default function GlobalColdStartLoader({ children }: { children: React.ReactNode }) {
  const [isInitializing, setIsInitializing] = useState(true);
  const [step, setStep] = useState(0);
  const [statusText, setStatusText] = useState(STEPS[0]);

  // Refs to prevent race conditions
  const hasTriggeredInitialRef = useRef(false);
  const hasTriggeredDefinitionsRef = useRef(false);
  const factsheetsDoneTimestampRef = useRef<number | null>(null);

  useEffect(() => {
    let pollingInterval: NodeJS.Timeout;

    const checkStatus = async () => {
      try {
        // Use the Phase 3 proxy status endpoint which aggregates everything
        const res = await fetchWithTimeout(`${PHASE1_URL.replace(':8000', ':8002')}/api/system/status`);
        if (!res.ok) return;
        const s = await res.json();

        const {
          has_data,
          is_running,
          phase1_ready, phase1_running,
          factsheets_ready, factsheets_running,
          definitions_ready, definitions_running,
        } = s;

        // ✅ Everything is done — dismiss loader
        if (has_data && !is_running) {
          clearInterval(pollingInterval);
          setIsInitializing(false);
          return;
        }

        // 🔥 Nothing is triggered yet — trigger initial pipelines
        if (!hasTriggeredInitialRef.current && !phase1_ready && !factsheets_ready && !phase1_running && !factsheets_running) {
          hasTriggeredInitialRef.current = true;
          setStep(1);
          setStatusText("Waking up AI agents...");
          fetchWithTimeout(`${PHASE1_URL.replace(':8000', ':8002')}/api/system/refresh`, { method: "POST" }).catch(() => {});
          return;
        }

        // 📊 Update UI based on current state
        if (phase1_running && factsheets_running) {
          setStep(2);
          setStatusText("Classifying 350+ reviews & scraping factsheets...");
        } else if (phase1_running && !factsheets_running) {
          setStep(2);
          setStatusText("Classifying app reviews using Groq LLM...");
        } else if (!phase1_running && factsheets_running) {
          setStep(2);
          setStatusText("Generating factsheet embeddings via Gemini...");
        } else if (definitions_running) {
          setStep(4);
          setStatusText("Indexing definition embeddings...");
        }

        // ⏳ Factsheets just finished — start 15s cooldown before definitions
        if (factsheets_ready && !factsheets_running && !definitions_ready && !definitions_running && !hasTriggeredDefinitionsRef.current) {
          if (factsheetsDoneTimestampRef.current === null) {
            factsheetsDoneTimestampRef.current = Date.now();
            setStep(3);
            setStatusText("Preparing to index definitions...");
          } else if (Date.now() - factsheetsDoneTimestampRef.current >= 15000) {
            hasTriggeredDefinitionsRef.current = true;
            fetchWithTimeout(`${PHASE1_URL.replace(':8000', ':8002')}/api/system/refresh/definitions`, { method: "POST" }).catch(() => {});
            setStep(4);
            setStatusText("Indexing definition embeddings...");
          }
        }

      } catch (err) {
        console.error("[GlobalLoader] Status check failed:", err);
      }
    };

    checkStatus();
    pollingInterval = setInterval(checkStatus, 5000);
    return () => clearInterval(pollingInterval);
  }, []);

  if (!isInitializing) return <>{children}</>;

  return (
    <div className="fixed inset-0 z-[9999] bg-[#0A0A0A] flex flex-col items-center justify-center overflow-hidden">
      {/* Background Grid */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_60%_at_50%_50%,#000_70%,transparent_100%)]" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-neon-green/10 rounded-full blur-[120px] opacity-50" />

      <div className="relative z-10 flex flex-col items-center max-w-md w-full px-6">
        {/* Brand */}
        <div className="flex items-center gap-2 mb-16">
          <Layers className="text-neon-green w-5 h-5" />
          <span className="text-white/80 font-semibold tracking-wide text-sm">Internal Ops</span>
        </div>

        {/* Spinner */}
        <div className="relative w-32 h-32 mb-12 flex items-center justify-center">
          <div className="absolute inset-0 rounded-full border-2 border-white/5" />
          <div className="absolute inset-0 rounded-full border-2 border-t-neon-green border-r-neon-green border-b-transparent border-l-transparent animate-spin" />
          <div className="absolute inset-2 rounded-full bg-neon-green/5 backdrop-blur-sm border border-neon-green/20 flex items-center justify-center">
            <Sparkles className="text-neon-green w-8 h-8 animate-pulse" strokeWidth={1.5} />
          </div>
        </div>

        {/* Text */}
        <div className="text-center mb-12">
          <div className="inline-block px-3 py-1 mb-4 rounded-full bg-neon-green/10 border border-neon-green/20 text-neon-green text-[10px] font-black tracking-[0.2em] uppercase">
            System Boot
          </div>
          <h1 className="text-3xl font-bold text-white mb-3 tracking-tight">INITIALIZING WORKSPACE</h1>
          <p className="text-white/40 text-sm font-medium leading-relaxed max-w-sm mx-auto">
            Waking up cluster. This may take 2–3 minutes on a cold start.
          </p>
        </div>

        {/* Status Card */}
        <div className="w-full bg-white/[0.02] border border-white/10 backdrop-blur-xl rounded-2xl p-4 flex items-center gap-4 mb-8">
          <div className="w-12 h-12 rounded-xl bg-neon-green/10 flex items-center justify-center text-neon-green shrink-0">
            {step === 0 ? <Server size={20} /> : step >= 5 ? <CheckCircle2 size={20} /> : <RefreshCw size={20} className="animate-spin" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-white text-sm font-bold truncate">Pipeline Status</div>
            <div className="text-white/50 text-xs font-medium truncate mt-0.5">{statusText}</div>
          </div>
        </div>

        {/* Progress Dots */}
        <div className="flex items-center gap-3">
          {STEPS.map((_, i) => (
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
