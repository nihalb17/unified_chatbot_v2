"use client";

import React, { useState, useEffect, useRef } from "react";
import { RefreshCw, Play, Apple, Info, AlertCircle, CheckCircle2, ArrowUpRight, MessageSquare, Sparkles, Smartphone, Activity, X, Lightbulb } from "lucide-react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";

/** Fetch with a timeout so the browser never hangs waiting for a dead backend. */
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

interface Theme {
  theme_name: string;
  short_description: string;
  sentiment: 'positive' | 'negative' | 'neutral' | 'mixed';
  total_mentions: number;
  playstore_mentions: number;
  appstore_mentions: number;
  representative_quotes: any[];
  actionable_item: string;
}

interface Metadata {
  timestamp: string;
  total_reviews_processed: number;
  source_breakdown: {
    playstore: number;
    appstore: number;
  };
}

export default function ReviewPulse() {
  const [data, setData] = useState<{ themes: Theme[], refresh_metadata: Metadata | null } | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTheme, setSelectedTheme] = useState<Theme | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const fetchData = async () => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/api/reviews/themes`);
      const json = await res.json();
      setData(json);
    } catch (err) {
      console.error("Failed to fetch themes", err);
    } finally {
      setLoading(false);
    }
  };

  const checkStatus = async (): Promise<boolean> => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/api/reviews/status`);
      const status = await res.json();
      setPipelineRunning(status.running);
      if (status.last_run && status.last_run.startsWith("Failed")) {
        setError(status.last_run);
        setPipelineRunning(false);
      }
      return status.running as boolean;
    } catch (err) {
      console.error("Failed to check status", err);
      return false;
    }
  };

  const startStatusPolling = () => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(async () => {
      const running = await checkStatus();
      if (!running) {
        if (intervalRef.current) clearInterval(intervalRef.current);
        intervalRef.current = null;
        fetchData();
      }
    }, 15000); // 15 seconds
  };

  useEffect(() => {
    const init = async () => {
      fetchData();
      const running = await checkStatus();
      if (running) startStatusPolling(); // resume polling if pipeline was already active
    };
    init();
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const handleRefresh = async () => {
    if (pipelineRunning) return;
    setRefreshing(true);
    setError(null);
    try {
      await fetchWithTimeout(`${API_BASE}/api/reviews/refresh`, { method: "POST" }, 15000);
      setPipelineRunning(true);
      startStatusPolling();
    } catch (err) {
      console.error("Failed to trigger refresh", err);
      setError("Failed to connect to backend server.");
    } finally {
      setRefreshing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen -ml-64">
        <RefreshCw className="animate-spin text-neon-green" size={48} />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-[1400px] relative">
      {/* Toast Notification */}
      <AnimatePresence>
        {error && (
          <motion.div 
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed top-6 right-6 z-[200] bg-red-500/10 border border-red-500/50 backdrop-blur-md p-4 rounded-xl shadow-2xl flex items-center gap-4 max-w-md"
          >
            <div className="w-8 h-8 bg-red-500/20 rounded-lg flex items-center justify-center text-red-500">
              <AlertCircle size={18} />
            </div>
            <div className="flex-1">
              <div className="text-xs font-bold text-white uppercase tracking-wider mb-1">Pipeline Error</div>
              <div className="text-[11px] text-white/70 font-medium line-clamp-2">{error}</div>
            </div>
            <button onClick={() => setError(null)} className="text-white/30 hover:text-white">
              <X size={16} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Top Header */}
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-neon-green rounded-xl flex items-center justify-center text-black">
            <Sparkles size={24} strokeWidth={2.5} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">Review Pulse</h1>
            <p className="text-white/40 text-[10px] font-medium mt-0.5">AI-classified reviews from Play Store & App Store</p>
          </div>
        </div>
        
        <div className="flex items-center gap-5">
          <div className="text-right">
            <div className="text-[9px] text-white/40 uppercase tracking-[0.15em] font-bold mb-1">LAST REFRESHED</div>
            <div className="text-[11px] text-white font-medium">
              {data?.refresh_metadata ? new Date(data.refresh_metadata.timestamp).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: 'numeric', minute: '2-digit', hour12: true, timeZone: 'Asia/Kolkata' }) : "Never"}
            </div>
          </div>
          <button 
            onClick={handleRefresh}
            disabled={refreshing || pipelineRunning}
            className="flex items-center gap-2 bg-neon-green text-black px-5 py-2.5 rounded-lg font-bold text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed min-w-[140px] justify-center"
          >
            <RefreshCw className={cn((refreshing || pipelineRunning) && "animate-spin")} size={14} strokeWidth={3} />
            {pipelineRunning ? "Analyzing..." : refreshing ? "Starting..." : "Refresh data"}
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-[#111111] border border-white/5 p-4 rounded-xl flex justify-between relative overflow-hidden group">
          <div className="relative z-10">
            <div className="text-[9px] text-white/40 uppercase tracking-[0.1em] font-bold mb-2">REVIEWS PROCESSED</div>
            <div className="text-2xl font-bold text-white mb-1 tracking-tight">{data?.refresh_metadata?.total_reviews_processed || 0}</div>
            <div className="text-[9px] text-white/30 font-medium">across both stores</div>
          </div>
          <div className="w-8 h-8 rounded-lg bg-[#22c55e]/10 text-[#22c55e] flex items-center justify-center relative z-10">
            <MessageSquare size={16} strokeWidth={2.5} />
          </div>
        </div>
        
        <div className="bg-[#111111] border border-white/5 p-4 rounded-xl flex justify-between">
          <div>
            <div className="text-[9px] text-white/40 uppercase tracking-[0.1em] font-bold mb-2">PLAY STORE</div>
            <div className="text-2xl font-bold text-white mb-1 tracking-tight">{data?.refresh_metadata?.source_breakdown.playstore || 0}</div>
            <div className="text-[9px] text-white/30 font-medium">
              {data?.refresh_metadata ? Math.round((data.refresh_metadata.source_breakdown.playstore / data.refresh_metadata.total_reviews_processed) * 100) : 0}% of total
            </div>
          </div>
          <div className="w-8 h-8 flex items-start justify-end text-white/20">
            <Play size={18} fill="currentColor" strokeWidth={0} />
          </div>
        </div>

        <div className="bg-[#111111] border border-white/5 p-4 rounded-xl flex justify-between">
          <div>
            <div className="text-[9px] text-white/40 uppercase tracking-[0.1em] font-bold mb-2">APP STORE</div>
            <div className="text-2xl font-bold text-white mb-1 tracking-tight">{data?.refresh_metadata?.source_breakdown.appstore || 0}</div>
            <div className="text-[9px] text-white/30 font-medium">
              {data?.refresh_metadata ? Math.round((data.refresh_metadata.source_breakdown.appstore / data.refresh_metadata.total_reviews_processed) * 100) : 0}% of total
            </div>
          </div>
          <div className="w-8 h-8 flex items-start justify-end text-white/20">
            <Apple size={18} strokeWidth={2} />
          </div>
        </div>

        <div className="bg-[#111111] border border-white/5 p-4 rounded-xl flex justify-between">
          <div>
            <div className="text-[9px] text-white/40 uppercase tracking-[0.1em] font-bold mb-2">SENTIMENT SPLIT</div>
            <div className="text-2xl font-bold text-white mb-1 tracking-tight">
              {data?.themes?.reduce((acc, t) => t.sentiment === 'positive' ? acc + t.total_mentions : acc, 0) || 0} / {data?.themes?.reduce((acc, t) => t.sentiment === 'negative' ? acc + t.total_mentions : acc, 0) || 0}
            </div>
            <div className="text-[9px] text-white/30 font-medium">positive vs negative</div>
          </div>
          <div className="w-8 h-8 flex items-start justify-end text-[#ef4444]">
            <Activity size={18} strokeWidth={2} />
          </div>
        </div>
      </div>

      {/* Themes Section */}
      <div className="space-y-1 mb-4">
        <h2 className="text-lg font-bold tracking-tight text-white">Themes</h2>
        <p className="text-white/40 text-[10px] font-medium">
          {data?.themes?.length || 0} themes - click any card to view reviews & action items
        </p>
      </div>

      {/* Themes Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {data?.themes?.map((theme) => (
          <ThemeCard 
            key={theme.theme_name} 
            theme={theme} 
            onClick={() => setSelectedTheme(theme)}
          />
        ))}
      </div>

      {/* Grid Ends Here */}

      {/* Side Drawer */}
      <AnimatePresence>
        {selectedTheme && (
          <ReviewDrawer 
            theme={selectedTheme} 
            onClose={() => setSelectedTheme(null)} 
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function ThemeCard({ theme, onClick }: { theme: Theme, onClick: () => void }) {
  const sentimentColors = {
    positive: "text-[#22c55e]",
    negative: "text-[#ef4444]",
    neutral: "text-[#f59e0b]",
    mixed: "text-[#eab308]",
  };

  const sentimentBg = {
    positive: "bg-[#22c55e]/10",
    negative: "bg-[#ef4444]/10",
    neutral: "bg-[#f59e0b]/10",
    mixed: "bg-[#eab308]/10",
  };

  return (
    <motion.div 
      layoutId={theme.theme_name}
      onClick={onClick}
      className="bg-[#0D0D0D] border border-white/5 p-5 rounded-xl cursor-pointer hover:border-white/10 transition-all group relative h-[190px] flex flex-col"
    >
      <div className="absolute top-5 right-5 text-white/10 group-hover:text-white transition-colors">
        <ArrowUpRight size={18} strokeWidth={2.5} />
      </div>

      <div className="flex items-center gap-2 mb-5">
        <div className={cn("w-1.5 h-1.5 rounded-full", 
          theme.sentiment === 'positive' ? "bg-[#22c55e]" : 
          theme.sentiment === 'negative' ? "bg-[#ef4444]" : "bg-[#f59e0b]"
        )} />
        <span className={cn(
          "px-2 py-0.5 rounded-md text-[9px] font-black tracking-[0.15em] uppercase",
          sentimentBg[theme.sentiment] || "bg-white/5",
          sentimentColors[theme.sentiment] || "text-white/40"
        )}>
          {theme.sentiment}
        </span>
      </div>
      
      <div className="space-y-1 mb-3">
        <h3 className="text-lg font-bold text-white leading-tight">
          {theme.theme_name}
        </h3>
        <p className="text-white/40 text-[11px] leading-relaxed font-medium">
          {theme.short_description}
        </p>
      </div>

      <div className="flex justify-between items-end mt-auto">
        <div className="space-y-0.5">
          <div className="text-2xl font-bold text-white tracking-tight">{theme.total_mentions}</div>
          <div className="text-[9px] uppercase tracking-widest font-black text-white/20 flex items-center gap-1.5">
            <MessageSquare className="w-3 h-3" strokeWidth={3} />
            mentions
          </div>
        </div>
        
        <div className="space-y-2 text-right pb-1">
          <div className="flex items-center justify-end gap-2 text-white/20 font-bold">
            <span className="text-sm">{theme.playstore_mentions}</span>
            <div className="p-0.5 bg-white/5 rounded">
               <Play size={14} fill="currentColor" className="text-white/40" />
            </div>
          </div>
          <div className="flex items-center justify-end gap-2 text-white/20 font-bold">
            <span className="text-sm">{theme.appstore_mentions}</span>
            <div className="p-0.5 bg-white/5 rounded">
              <Apple size={14} fill="currentColor" className="text-white/40" />
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function ReviewDrawer({ theme, onClose }: { theme: Theme, onClose: () => void }) {
  const sentimentColors = {
    positive: "text-[#22c55e] border-[#22c55e]/20 bg-[#22c55e]/10",
    negative: "text-[#ef4444] border-[#ef4444]/20 bg-[#ef4444]/10",
    neutral: "text-[#f59e0b] border-[#f59e0b]/20 bg-[#f59e0b]/10",
    mixed: "text-[#eab308] border-[#eab308]/20 bg-[#eab308]/10",
  };

  const sentimentDotColors = {
    positive: "bg-[#22c55e]",
    negative: "bg-[#ef4444]",
    neutral: "bg-[#f59e0b]",
    mixed: "bg-[#eab308]",
  };

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] flex justify-end"
      onClick={onClose}
    >
      <motion.div 
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 30, stiffness: 300 }}
        className="w-full max-w-2xl bg-[#111318] border-l border-white/10 h-full overflow-y-auto p-8 shadow-2xl relative"
        onClick={(e) => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-6 right-6 text-white/30 hover:text-white transition-colors">
          <X size={18} strokeWidth={2.5} />
        </button>

        <div className="space-y-8 mt-2">
          {/* Header Section */}
          <div>
            <div className={cn(
              "inline-flex items-center gap-2 px-3 py-1.5 rounded-full border mb-6",
              sentimentColors[theme.sentiment]
            )}>
              <div className={cn("w-1.5 h-1.5 rounded-full", sentimentDotColors[theme.sentiment])} />
              <span className="text-[9px] font-bold uppercase tracking-widest">{theme.sentiment} SENTIMENT</span>
            </div>
            
            <h2 className="text-2xl font-bold mb-2 tracking-tight text-white">{theme.theme_name}</h2>
            <p className="text-white/50 leading-relaxed font-medium text-sm">{theme.short_description}</p>
          </div>

          {/* Metrics Row */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-[#181a20] border border-white/5 p-4 rounded-xl">
              <div className="flex items-center gap-2 text-white/40 mb-2">
                <MessageSquare size={14} strokeWidth={2} />
                <span className="text-[10px] uppercase font-bold tracking-widest">TOTAL</span>
              </div>
              <div className="text-2xl font-bold text-white">{theme.total_mentions}</div>
            </div>
            <div className="bg-[#181a20] border border-white/5 p-4 rounded-xl">
              <div className="flex items-center gap-2 text-white/40 mb-2">
                <Play size={14} fill="currentColor" strokeWidth={0} />
                <span className="text-[10px] uppercase font-bold tracking-widest">PLAY STORE</span>
              </div>
              <div className="text-2xl font-bold text-white">{theme.playstore_mentions}</div>
            </div>
            <div className="bg-[#181a20] border border-white/5 p-4 rounded-xl">
              <div className="flex items-center gap-2 text-white/40 mb-2">
                <Apple size={14} strokeWidth={2} />
                <span className="text-[10px] uppercase font-bold tracking-widest">APP STORE</span>
              </div>
              <div className="text-2xl font-bold text-white">{theme.appstore_mentions}</div>
            </div>
          </div>

          {/* Representative Reviews */}
          <div className="space-y-4 pt-4">
            <h4 className="text-[11px] font-bold text-white/40 uppercase tracking-widest mb-4">REPRESENTATIVE REVIEWS</h4>
            {theme.representative_quotes.map((quote, idx) => {
              const text = typeof quote === 'string' ? quote : quote.text;
              const source = typeof quote === 'string' ? 'PLAY STORE' : (quote.source === 'appstore' ? 'APP STORE' : 'PLAY STORE');
              return (
                <div key={idx} className="bg-[#181a20] border border-white/5 p-5 rounded-xl relative overflow-hidden group">
                  <span className="font-serif text-6xl leading-none absolute top-4 right-4 text-white/5 select-none">”</span>
                  <p className="text-white/90 font-medium leading-relaxed mb-4 relative z-10 pr-8 text-[13px]">
                    "{text}"
                  </p>
                  <div className="text-[9px] uppercase tracking-widest font-bold text-white/30">
                    REVIEW #{idx + 1} - {source}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Actionable Item */}
          <div className="bg-[#111c16] border border-[#22c55e]/30 shadow-[0_0_15px_rgba(34,197,94,0.05)] p-5 rounded-xl mt-6">
            <h4 className="text-[#22c55e] font-black text-[10px] uppercase tracking-widest mb-3 flex items-center gap-2">
              <Lightbulb size={14} strokeWidth={2.5} />
              ACTIONABLE ITEM
            </h4>
            <p className="text-white/90 font-medium leading-relaxed text-[14px]">{theme.actionable_item}</p>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
