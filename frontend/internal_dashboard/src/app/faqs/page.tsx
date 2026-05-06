"use client";

import React, { useState, useEffect } from "react";
import {
  RefreshCw,
  Plus,
  X,
  ExternalLink,
  FileText,
  BookOpen,
  CheckCircle2,
  XCircle,
  Loader2,
  Database,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";

const API_BASE = process.env.NEXT_PUBLIC_PHASE2_URL || "http://localhost:8001";

// ===== Types =====

interface FactsheetUrl {
  url: string;
  name: string;
}

interface DefinitionUrl {
  url: string;
  term: string;
}

interface UrlStatus {
  url: string;
  label: string;
  status: "success" | "failed";
  scraped_at: string;
  failure_reason: string | null;
  fields_extracted?: number;
}

interface IndexingInfo {
  last_refreshed: string | null;
  url_statuses: UrlStatus[];
}

interface PipelineProgress {
  url: string;
  label: string;
  status: "success" | "failed";
  failure_reason: string | null;
}

// ===== Helper =====

function formatTimestamp(ts: string | null): string {
  if (!ts) return "Never";
  return new Date(ts).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: "Asia/Kolkata",
  });
}

function extractNameFromUrl(url: string): string {
  const slug = url.replace(/\/$/, "").split("/").pop() || "";
  return slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

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

// ===== Main Page =====

export default function MutualFundFAQs() {
  // ----- Factsheet state -----
  const [factsheetUrls, setFactsheetUrls] = useState<FactsheetUrl[]>([]);
  const [factsheetIndexing, setFactsheetIndexing] = useState<IndexingInfo>({ last_refreshed: null, url_statuses: [] });
  const [factsheetInput, setFactsheetInput] = useState("");
  const [factsheetRefreshing, setFactsheetRefreshing] = useState(false);
  const [factsheetProgress, setFactsheetProgress] = useState<PipelineProgress[]>([]);

  // ----- Definition state -----
  const [definitionUrls, setDefinitionUrls] = useState<DefinitionUrl[]>([]);
  const [definitionIndexing, setDefinitionIndexing] = useState<IndexingInfo>({ last_refreshed: null, url_statuses: [] });
  const [defTermInput, setDefTermInput] = useState("");
  const [defUrlInput, setDefUrlInput] = useState("");
  const [definitionRefreshing, setDefinitionRefreshing] = useState(false);
  const [definitionProgress, setDefinitionProgress] = useState<PipelineProgress[]>([]);

  // ----- Page-level state -----
  const [pageLoading, setPageLoading] = useState(true);
  const [backendError, setBackendError] = useState<string | null>(null);

  // ----- Initial Load -----
  useEffect(() => {
    let cancelled = false;

    async function loadInitial() {
      setPageLoading(true);
      setBackendError(null);

      try {
        const [fsRes, defRes, statusRes] = await Promise.allSettled([
          fetchWithTimeout(`${API_BASE}/api/faqs/factsheets`),
          fetchWithTimeout(`${API_BASE}/api/faqs/definitions`),
          fetchWithTimeout(`${API_BASE}/api/faqs/status`),
        ]);

        if (!cancelled) {
          if (fsRes.status === "fulfilled") {
            const data = await fsRes.value.json();
            setFactsheetUrls(data.urls || []);
            setFactsheetIndexing(data.indexing || { last_refreshed: null, url_statuses: [] });
          } else {
            console.error("Failed to fetch factsheets", fsRes.reason);
            setBackendError("Could not connect to FAQ backend (port 8001). Make sure it is running.");
          }

          if (defRes.status === "fulfilled") {
            const data = await defRes.value.json();
            setDefinitionUrls(data.urls || []);
            setDefinitionIndexing(data.indexing || { last_refreshed: null, url_statuses: [] });
          }

          if (statusRes.status === "fulfilled") {
            const status = await statusRes.value.json();
            if (status.factsheets.running) {
              setFactsheetRefreshing(true);
              setFactsheetProgress(status.factsheets.progress);
            }
            if (status.definitions.running) {
              setDefinitionRefreshing(true);
              setDefinitionProgress(status.definitions.progress);
            }
          }
        }
      } catch (err) {
        if (!cancelled) {
          console.error("Failed initial load", err);
          setBackendError("Could not connect to FAQ backend (port 8001). Make sure it is running.");
        }
      } finally {
        if (!cancelled) setPageLoading(false);
      }
    }

    loadInitial();
    return () => { cancelled = true; };
  }, []);

  // ----- Factsheet CRUD -----
  const fetchFactsheets = async () => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/api/faqs/factsheets`);
      const data = await res.json();
      setFactsheetUrls(data.urls || []);
      setFactsheetIndexing(data.indexing || { last_refreshed: null, url_statuses: [] });
    } catch (err) {
      console.error("Failed to fetch factsheets", err);
    }
  };

  const addFactsheetUrl = async () => {
    const url = factsheetInput.trim();
    if (!url) return;
    try {
      const res = await fetchWithTimeout(`${API_BASE}/api/faqs/factsheets/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || "Failed to add URL");
        return;
      }
      const data = await res.json();
      setFactsheetUrls(data.urls);
      setFactsheetInput("");
    } catch (err) {
      console.error("Failed to add factsheet URL", err);
    }
  };

  const deleteFactsheetUrl = async (url: string) => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/api/faqs/factsheets?url=${encodeURIComponent(url)}`, { method: "DELETE" });
      const data = await res.json();
      setFactsheetUrls(data.urls);
    } catch (err) {
      console.error("Failed to delete factsheet URL", err);
    }
  };

  // ----- Definition CRUD -----
  const fetchDefinitions = async () => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/api/faqs/definitions`);
      const data = await res.json();
      setDefinitionUrls(data.urls || []);
      setDefinitionIndexing(data.indexing || { last_refreshed: null, url_statuses: [] });
    } catch (err) {
      console.error("Failed to fetch definitions", err);
    }
  };

  const addDefinitionUrl = async () => {
    const url = defUrlInput.trim();
    const term = defTermInput.trim();
    if (!url || !term) return;
    try {
      const res = await fetchWithTimeout(`${API_BASE}/api/faqs/definitions/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, term }),
      });
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || "Failed to add URL");
        return;
      }
      const data = await res.json();
      setDefinitionUrls(data.urls);
      setDefTermInput("");
      setDefUrlInput("");
    } catch (err) {
      console.error("Failed to add definition URL", err);
    }
  };

  const deleteDefinitionUrl = async (url: string) => {
    try {
      const res = await fetchWithTimeout(`${API_BASE}/api/faqs/definitions?url=${encodeURIComponent(url)}`, { method: "DELETE" });
      const data = await res.json();
      setDefinitionUrls(data.urls);
    } catch (err) {
      console.error("Failed to delete definition URL", err);
    }
  };

  const refreshFactsheets = async () => {
    if (factsheetRefreshing) return;
    setFactsheetRefreshing(true);
    setFactsheetProgress([]);
    try {
      await fetchWithTimeout(`${API_BASE}/api/faqs/factsheets/refresh`, { method: "POST" }, 15000);
      // Polling useEffect will handle progress and completion
    } catch (err) {
      console.error("Failed to trigger factsheet refresh", err);
      setFactsheetRefreshing(false);
    }
  };

  const refreshDefinitions = async () => {
    if (definitionRefreshing) return;
    setDefinitionRefreshing(true);
    setDefinitionProgress([]);
    try {
      await fetchWithTimeout(`${API_BASE}/api/faqs/definitions/refresh`, { method: "POST" }, 15000);
      // Polling useEffect will handle progress and completion
    } catch (err) {
      console.error("Failed to trigger definition refresh", err);
      setDefinitionRefreshing(false);
    }
  };

  // ----- Polling Logic -----
  useEffect(() => {
    if (!factsheetRefreshing && !definitionRefreshing) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetchWithTimeout(`${API_BASE}/api/faqs/status`);
        if (!res.ok) return;
        const data = await res.json();

        // Update progress lists
        setFactsheetProgress(data.factsheets.progress);
        setDefinitionProgress(data.definitions.progress);

        // Check if finished
        if (!data.factsheets.running && factsheetRefreshing) {
          setFactsheetRefreshing(false);
          fetchFactsheets(); // Final refresh for success icons and timestamp
        }
        if (!data.definitions.running && definitionRefreshing) {
          setDefinitionRefreshing(false);
          fetchDefinitions(); // Final refresh for success icons and timestamp
        }
      } catch (err) {
        console.error("Polling error", err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [factsheetRefreshing, definitionRefreshing]);

  // ----- Loading State -----
  if (pageLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <Loader2 size={36} className="animate-spin text-neon-green" />
        <p className="text-white/40 text-sm font-medium">Loading FAQ data...</p>
      </div>
    );
  }

  // ----- Backend Error State -----
  if (backendError) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4 max-w-md mx-auto text-center">
        <div className="w-14 h-14 bg-red-500/10 rounded-xl flex items-center justify-center">
          <AlertCircle size={28} className="text-red-500" />
        </div>
        <h2 className="text-white font-bold text-lg">Backend Unavailable</h2>
        <p className="text-white/40 text-sm leading-relaxed">{backendError}</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-4 flex items-center gap-2 bg-neon-green text-black px-5 py-2.5 rounded-lg font-bold text-xs hover:brightness-110 transition-all"
        >
          <RefreshCw size={14} strokeWidth={3} />
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-[1100px]">
      {/* Page Header */}
      <div className="flex items-center gap-4 mb-2">
        <div className="w-12 h-12 bg-neon-green rounded-xl flex items-center justify-center text-black">
          <Database size={24} strokeWidth={2.5} />
        </div>
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">Mutual Fund FAQs</h1>
          <p className="text-white/40 text-[10px] font-medium mt-0.5">
            Manage knowledge base links for fact sheets and mutual fund definitions
          </p>
        </div>
      </div>

      {/* Knowledge Base Section Label */}
      <div className="flex items-center gap-2 mt-4 mb-2">
        <Database size={14} className="text-white/30" />
        <span className="text-[11px] uppercase tracking-widest font-bold text-white/30">Knowledge Base</span>
      </div>

      {/* ===== Fact Sheets Card ===== */}
      <div className="bg-[#111111] border border-white/5 rounded-xl p-6">
        {/* Card Header */}
        <div className="flex items-start justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-[#22c55e]/10 rounded-lg flex items-center justify-center">
              <FileText size={20} className="text-[#22c55e]" />
            </div>
            <div>
              <h2 className="text-white font-bold text-sm">Fact Sheets</h2>
              <p className="text-white/40 text-[10px] font-medium mt-0.5">
                Mutual fund schemes and their fact sheet links
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="text-[9px] text-white/30 uppercase tracking-widest font-bold">Last Updated</div>
              <div className="text-[11px] text-white/70 font-medium">
                {formatTimestamp(factsheetIndexing.last_refreshed)}
              </div>
            </div>
            <button
              onClick={refreshFactsheets}
              disabled={factsheetRefreshing || factsheetUrls.length === 0}
              className="flex items-center gap-2 bg-neon-green text-black px-4 py-2 rounded-lg font-bold text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshCw size={14} strokeWidth={3} className={cn(factsheetRefreshing && "animate-spin")} />
              {factsheetRefreshing ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>

        {/* Add URL Input */}
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={factsheetInput}
            onChange={(e) => setFactsheetInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addFactsheetUrl()}
            placeholder="https://groww.in/mutual-funds/..."
            className="flex-1 bg-[#0A0A0A] border border-white/10 rounded-lg px-4 py-2.5 text-sm text-white placeholder:text-white/20 focus:outline-none focus:border-[#22c55e]/50 transition-colors"
          />
          <button
            onClick={addFactsheetUrl}
            disabled={!factsheetInput.trim()}
            className="flex items-center gap-1.5 bg-[#0A0A0A] border border-white/10 text-white/70 hover:text-white hover:border-white/20 px-4 py-2.5 rounded-lg text-xs font-bold transition-all disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <Plus size={14} strokeWidth={3} />
            Add
          </button>
        </div>

        {/* URL List */}
        <div className="space-y-0">
          {factsheetUrls.map((entry) => {
            const urlStatus = factsheetIndexing.url_statuses.find((s) => s.url === entry.url);
            return (
              <div
                key={entry.url}
                className="flex items-center justify-between py-3 border-b border-white/5 last:border-0 group"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    {urlStatus && (
                      urlStatus.status === "success" ? (
                        <CheckCircle2 size={14} className="text-[#22c55e] shrink-0" />
                      ) : (
                        <XCircle size={14} className="text-[#ef4444] shrink-0" />
                      )
                    )}
                    <span className="text-white font-semibold text-sm truncate">{entry.name}</span>
                  </div>
                  <a
                    href={entry.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[#22c55e] text-[11px] font-medium hover:underline flex items-center gap-1 mt-0.5 ml-6"
                  >
                    {entry.url}
                    <ExternalLink size={10} />
                  </a>
                </div>
                <button
                  onClick={() => deleteFactsheetUrl(entry.url)}
                  className="text-white/10 hover:text-[#ef4444] transition-colors opacity-0 group-hover:opacity-100 ml-3"
                >
                  <X size={16} />
                </button>
              </div>
            );
          })}
          {factsheetUrls.length === 0 && (
            <div className="text-white/20 text-xs text-center py-6">No factsheet URLs added yet</div>
          )}
        </div>

        {/* Refresh Progress */}
        <AnimatePresence>
          {factsheetRefreshing && factsheetProgress.length > 0 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-4 border-t border-white/5 pt-4"
            >
              <div className="text-[10px] uppercase tracking-widest font-bold text-white/30 mb-3 flex items-center gap-2">
                <Loader2 size={12} className="animate-spin text-[#22c55e]" />
                Indexing Progress
              </div>
              <div className="space-y-2">
                {factsheetProgress.map((p, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    {p.status === "success" ? (
                      <CheckCircle2 size={14} className="text-[#22c55e] shrink-0" />
                    ) : (
                      <XCircle size={14} className="text-[#ef4444] shrink-0" />
                    )}
                    <span className="text-white/70">{p.label}</span>
                    {p.failure_reason && (
                      <span className="text-[#ef4444]/70 text-[10px]">— {p.failure_reason}</span>
                    )}
                  </div>
                ))}
              </div>
              <div className="mt-3 text-[10px] text-white/30 font-medium">
                {factsheetProgress.filter((p) => p.status === "success").length} /{" "}
                {factsheetProgress.length} URLs updated successfully
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ===== Mutual Fund Definitions Card ===== */}
      <div className="bg-[#111111] border border-white/5 rounded-xl p-6">
        {/* Card Header */}
        <div className="flex items-start justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-[#22c55e]/10 rounded-lg flex items-center justify-center">
              <BookOpen size={20} className="text-[#22c55e]" />
            </div>
            <div>
              <h2 className="text-white font-bold text-sm">Mutual Fund Definitions</h2>
              <p className="text-white/40 text-[10px] font-medium mt-0.5">
                Glossary terms and their explainer links
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="text-[9px] text-white/30 uppercase tracking-widest font-bold">Last Updated</div>
              <div className="text-[11px] text-white/70 font-medium">
                {formatTimestamp(definitionIndexing.last_refreshed)}
              </div>
            </div>
            <button
              onClick={refreshDefinitions}
              disabled={definitionRefreshing || definitionUrls.length === 0}
              className="flex items-center gap-2 bg-neon-green text-black px-4 py-2 rounded-lg font-bold text-xs hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshCw size={14} strokeWidth={3} className={cn(definitionRefreshing && "animate-spin")} />
              {definitionRefreshing ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>

        {/* Add Definition Input */}
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={defTermInput}
            onChange={(e) => setDefTermInput(e.target.value)}
            placeholder="Term (e.g. Exit Load)"
            className="w-[240px] bg-[#0A0A0A] border border-white/10 rounded-lg px-4 py-2.5 text-sm text-white placeholder:text-white/20 focus:outline-none focus:border-[#22c55e]/50 transition-colors"
          />
          <input
            type="text"
            value={defUrlInput}
            onChange={(e) => setDefUrlInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addDefinitionUrl()}
            placeholder="https://groww.in/p/..."
            className="flex-1 bg-[#0A0A0A] border border-white/10 rounded-lg px-4 py-2.5 text-sm text-white placeholder:text-white/20 focus:outline-none focus:border-[#22c55e]/50 transition-colors"
          />
          <button
            onClick={addDefinitionUrl}
            disabled={!defTermInput.trim() || !defUrlInput.trim()}
            className="flex items-center gap-1.5 bg-[#0A0A0A] border border-white/10 text-white/70 hover:text-white hover:border-white/20 px-4 py-2.5 rounded-lg text-xs font-bold transition-all disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <Plus size={14} strokeWidth={3} />
            Add
          </button>
        </div>

        {/* Definition List */}
        <div className="space-y-0">
          {definitionUrls.map((entry) => {
            const urlStatus = definitionIndexing.url_statuses.find((s) => s.url === entry.url);
            return (
              <div
                key={entry.url}
                className="flex items-center justify-between py-3 border-b border-white/5 last:border-0 group"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    {urlStatus && (
                      urlStatus.status === "success" ? (
                        <CheckCircle2 size={14} className="text-[#22c55e] shrink-0" />
                      ) : (
                        <XCircle size={14} className="text-[#ef4444] shrink-0" />
                      )
                    )}
                    <span className="text-white font-semibold text-sm">{entry.term}</span>
                  </div>
                  <a
                    href={entry.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[#22c55e] text-[11px] font-medium hover:underline flex items-center gap-1 mt-0.5 ml-6"
                  >
                    {entry.url}
                    <ExternalLink size={10} />
                  </a>
                </div>
                <button
                  onClick={() => deleteDefinitionUrl(entry.url)}
                  className="text-white/10 hover:text-[#ef4444] transition-colors opacity-0 group-hover:opacity-100 ml-3"
                >
                  <X size={16} />
                </button>
              </div>
            );
          })}
          {definitionUrls.length === 0 && (
            <div className="text-white/20 text-xs text-center py-6">No definition URLs added yet</div>
          )}
        </div>

        {/* Refresh Progress */}
        <AnimatePresence>
          {definitionRefreshing && definitionProgress.length > 0 && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-4 border-t border-white/5 pt-4"
            >
              <div className="text-[10px] uppercase tracking-widest font-bold text-white/30 mb-3 flex items-center gap-2">
                <Loader2 size={12} className="animate-spin text-[#22c55e]" />
                Indexing Progress
              </div>
              <div className="space-y-2">
                {definitionProgress.map((p, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    {p.status === "success" ? (
                      <CheckCircle2 size={14} className="text-[#22c55e] shrink-0" />
                    ) : (
                      <XCircle size={14} className="text-[#ef4444] shrink-0" />
                    )}
                    <span className="text-white/70">{p.label}</span>
                    {p.failure_reason && (
                      <span className="text-[#ef4444]/70 text-[10px]">— {p.failure_reason}</span>
                    )}
                  </div>
                ))}
              </div>
              <div className="mt-3 text-[10px] text-white/30 font-medium">
                {definitionProgress.filter((p) => p.status === "success").length} /{" "}
                {definitionProgress.length} URLs updated successfully
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
