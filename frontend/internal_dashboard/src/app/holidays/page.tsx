"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  SlidersHorizontal,
  Clock,
  UtensilsCrossed,
  Timer,
  CalendarOff,
  Save,
  Loader2,
  CheckCircle2,
  XCircle,
  Plus,
  X,
  RefreshCw,
  Briefcase,
  CalendarDays,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";

const API_BASE = process.env.NEXT_PUBLIC_PHASE3_URL || "http://localhost:8002";

/** Python datetime.weekday(): Monday = 0 … Sunday = 6 */
const WEEKDAY_META = [
  { id: 0, short: "Mon", full: "Monday" },
  { id: 1, short: "Tue", full: "Tuesday" },
  { id: 2, short: "Wed", full: "Wednesday" },
  { id: 3, short: "Thu", full: "Thursday" },
  { id: 4, short: "Fri", full: "Friday" },
  { id: 5, short: "Sat", full: "Saturday" },
  { id: 6, short: "Sun", full: "Sunday" },
];

interface SlotConfig {
  work_start: string;
  work_end: string;
  lunch_start: string;
  lunch_end: string;
  gap_mins: number;
  work_weekdays: number[];
  holidays: string[];
}

interface HolidayRow {
  date: string;
  label: string;
}

const emptyConfig: SlotConfig = {
  work_start: "09:00",
  work_end: "18:00",
  lunch_start: "13:00",
  lunch_end: "14:00",
  gap_mins: 0,
  work_weekdays: [0, 1, 2, 3, 4],
  holidays: [],
};

function sortNums(a: number[]): number[] {
  return [...new Set(a)].sort((x, y) => x - y);
}

function parseHolidayEntry(raw: string): HolidayRow {
  const i = raw.indexOf("|");
  if (i === -1) return { date: raw.trim(), label: "" };
  return { date: raw.slice(0, i).trim(), label: raw.slice(i + 1).trim() };
}

function holidayRowsFromApi(holidays: string[]): HolidayRow[] {
  return holidays.map(parseHolidayEntry).sort((a, b) => a.date.localeCompare(b.date));
}

function serializeHolidayRows(rows: HolidayRow[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const r of rows) {
    const d = r.date.trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d) || seen.has(d)) continue;
    seen.add(d);
    const lab = r.label.trim();
    out.push(lab ? `${d}|${lab}` : d);
  }
  return out.sort();
}

export default function MeetingSlotConfiguration() {
  const [config, setConfig] = useState<SlotConfig>(emptyConfig);
  const [newHolidayDate, setNewHolidayDate] = useState("");
  const [newHolidayLabel, setNewHolidayLabel] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{
    type: "ok" | "err";
    text: string;
  } | null>(null);

  const holidayRows = useMemo(
    () => holidayRowsFromApi(config.holidays),
    [config.holidays]
  );

  const loadConfig = useCallback(async () => {
    setLoading(true);
    setMessage(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/slot-config`, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const ww = Array.isArray(data.work_weekdays)
        ? sortNums(data.work_weekdays.map((n: unknown) => Number(n)))
        : [0, 1, 2, 3, 4];
      setConfig({
        work_start: data.work_start ?? "09:00",
        work_end: data.work_end ?? "18:00",
        lunch_start: data.lunch_start ?? "",
        lunch_end: data.lunch_end ?? "",
        gap_mins: typeof data.gap_mins === "number" ? data.gap_mins : 0,
        work_weekdays: ww.length ? ww : [0, 1, 2, 3, 4],
        holidays: Array.isArray(data.holidays) ? data.holidays : [],
      });
    } catch {
      setMessage({
        type: "err",
        text: "Could not load configuration. Is the orchestrator running on port 8002?",
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const toggleWeekday = (id: number) => {
    setConfig((c) => {
      const has = c.work_weekdays.includes(id);
      const next = has
        ? c.work_weekdays.filter((x) => x !== id)
        : sortNums([...c.work_weekdays, id]);
      if (next.length === 0) return c;
      return { ...c, work_weekdays: next };
    });
    setMessage(null);
  };

  const applyPreset = (days: number[]) => {
    setConfig((c) => ({ ...c, work_weekdays: sortNums(days) }));
    setMessage(null);
  };

  const weekdaySummary = useMemo(() => {
    if (config.work_weekdays.length === 7) return "Every day";
    if (
      config.work_weekdays.length === 5 &&
      [0, 1, 2, 3, 4].every((d) => config.work_weekdays.includes(d))
    )
      return "Monday–Friday";
    if (
      config.work_weekdays.length === 6 &&
      [0, 1, 2, 3, 4, 5].every((d) => config.work_weekdays.includes(d))
    )
      return "Monday–Saturday";
    return config.work_weekdays.map((id) => WEEKDAY_META[id]?.short ?? id).join(", ");
  }, [config.work_weekdays]);

  const save = async () => {
    setSaving(true);
    setMessage(null);
    // Snapshot the latest committed state (avoids stale ref/closures if Save races a toggle).
    const snap = await new Promise<SlotConfig>((resolve) => {
      setConfig((c) => {
        resolve({
          ...c,
          work_weekdays: [...c.work_weekdays],
          holidays: [...c.holidays],
        });
        return c;
      });
    });
    const workWeekdays = sortNums([...snap.work_weekdays]);
    if (workWeekdays.length === 0) {
      setMessage({ type: "err", text: "Select at least one work day." });
      setSaving(false);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/admin/slot-config`, {
        method: "PUT",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          work_start: snap.work_start,
          work_end: snap.work_end,
          lunch_start: snap.lunch_start.trim(),
          lunch_end: snap.lunch_end.trim(),
          gap_mins: snap.gap_mins,
          work_weekdays: workWeekdays,
          holidays: snap.holidays,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        let detail: string = res.statusText || "Save failed";
        if (typeof body.detail === "string") detail = body.detail;
        else if (Array.isArray(body.detail)) {
          const first = body.detail[0];
          if (first && typeof first.msg === "string") detail = first.msg;
        }
        throw new Error(detail);
      }
      const parsedWw = Array.isArray(body.work_weekdays)
        ? sortNums(body.work_weekdays.map((n: unknown) => Number(n)))
        : [];
      const ww =
        parsedWw.length > 0 ? parsedWw : workWeekdays;
      setConfig({
        work_start: body.work_start,
        work_end: body.work_end,
        lunch_start: body.lunch_start ?? "",
        lunch_end: body.lunch_end ?? "",
        gap_mins: body.gap_mins ?? 0,
        work_weekdays: ww,
        holidays: body.holidays ?? [],
      });
      setMessage({
        type: "ok",
        text: "Saved. Slot checks and suggestions use these rules immediately.",
      });
    } catch (e) {
      setMessage({
        type: "err",
        text: e instanceof Error ? e.message : "Save failed.",
      });
    } finally {
      setSaving(false);
    }
  };

  const addHoliday = () => {
    const d = newHolidayDate.trim();
    if (!d || !/^\d{4}-\d{2}-\d{2}$/.test(d)) {
      setMessage({
        type: "err",
        text: "Pick a valid date (YYYY-MM-DD).",
      });
      return;
    }
    const rows = holidayRowsFromApi(config.holidays);
    if (rows.some((r) => r.date === d)) {
      setMessage({ type: "err", text: "That date is already in the holiday list." });
      return;
    }
    const nextRows = [...rows, { date: d, label: newHolidayLabel.trim() }];
    setConfig((c) => ({ ...c, holidays: serializeHolidayRows(nextRows) }));
    setNewHolidayDate("");
    setNewHolidayLabel("");
    setMessage(null);
  };

  const removeHolidayByDate = (dateStr: string) => {
    const next = holidayRows.filter((r) => r.date !== dateStr);
    setConfig((c) => ({ ...c, holidays: serializeHolidayRows(next) }));
  };

  const updateHolidayLabel = (dateStr: string, label: string) => {
    const next = holidayRows.map((r) =>
      r.date === dateStr ? { ...r, label } : r
    );
    setConfig((c) => ({ ...c, holidays: serializeHolidayRows(next) }));
  };

  const cardShell = (
    icon: React.ReactNode,
    title: string,
    children: React.ReactNode
  ) => (
    <section className="bg-[#111111] border border-white/5 rounded-xl overflow-hidden h-full flex flex-col">
      <div className="border-b border-white/5 px-3 py-2 flex items-center gap-2 shrink-0">
        {icon}
        <h2 className="text-white font-bold text-sm">{title}</h2>
      </div>
      <div className="p-3.5 flex-1 flex flex-col min-h-0">{children}</div>
    </section>
  );

  return (
    <div className="space-y-4 max-w-[1100px] relative">
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-neon-green rounded-lg flex items-center justify-center text-black shrink-0">
            <SlidersHorizontal className="w-5 h-5" strokeWidth={2.5} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              Meeting Slot Configuration
            </h1>
            <p className="text-white/40 text-[10px] font-medium mt-0.5 max-w-xl">
              2×2 grid: work week, business hours, lunch, and slot gap. Holidays
              are listed below with optional names (e.g. Independence Day, Holi).
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={loadConfig}
            disabled={saving || loading}
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-white/75 hover:bg-white/10 disabled:opacity-40"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
            Reload
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving || loading}
            className="inline-flex items-center gap-1.5 rounded-lg bg-neon-green px-4 py-1.5 text-xs font-semibold text-black hover:opacity-90 disabled:opacity-50"
          >
            {saving ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Save className="w-3.5 h-3.5" />
            )}
            Save
          </button>
        </div>
      </motion.div>

      <AnimatePresence>
        {message && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className={cn(
              "rounded-lg border px-3 py-2 flex items-start gap-2 text-xs leading-snug",
              message.type === "ok"
                ? "border-neon-green/35 bg-neon-green/[0.07] text-neon-green"
                : "border-red-500/40 bg-red-500/[0.06] text-red-300"
            )}
          >
            {message.type === "ok" ? (
              <CheckCircle2 className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            ) : (
              <XCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            )}
            <span>{message.text}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-16 gap-2">
          <Loader2 className="w-8 h-8 animate-spin text-neon-green" />
          <p className="text-white/40 text-xs">Loading configuration…</p>
        </div>
      ) : (
        <>
          {/* 2×2 configuration matrix */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {cardShell(
              <Briefcase className="w-3.5 h-3.5 text-[#22c55e] shrink-0" />,
              "Work week (Mon–Sun)",
              <>
                <p className="text-xs text-white/40 mb-2">
                  Active:{" "}
                  <span className="text-white/65">{weekdaySummary}</span>
                </p>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  <button
                    type="button"
                    onClick={() => applyPreset([0, 1, 2, 3, 4])}
                    className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs font-medium text-white/75 hover:bg-white/10"
                  >
                    Mon–Fri
                  </button>
                  <button
                    type="button"
                    onClick={() => applyPreset([0, 1, 2, 3, 4, 5])}
                    className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs font-medium text-white/75 hover:bg-white/10"
                  >
                    Mon–Sat
                  </button>
                  <button
                    type="button"
                    onClick={() => applyPreset([0, 1, 2, 3, 4, 5, 6])}
                    className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs font-medium text-white/75 hover:bg-white/10"
                  >
                    All days
                  </button>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {WEEKDAY_META.map((d) => {
                    const on = config.work_weekdays.includes(d.id);
                    return (
                      <button
                        key={d.id}
                        type="button"
                        title={d.full}
                        onClick={() => toggleWeekday(d.id)}
                        className={cn(
                          "min-w-[2.25rem] rounded-md px-2 py-1 text-xs font-semibold transition-all",
                          on
                            ? "bg-neon-green text-black"
                            : "border border-white/10 bg-black/40 text-white/45 hover:border-white/20 hover:text-white/65"
                        )}
                      >
                        {d.short}
                      </button>
                    );
                  })}
                </div>
              </>
            )}

            {cardShell(
              <Clock className="w-3.5 h-3.5 text-[#22c55e] shrink-0" />,
              "Business hours",
              <>
                <p className="text-xs text-white/40 mb-2">
                  Working window for bookable slots each work day.
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-[11px] font-bold uppercase tracking-wider text-white/40 block mb-1">
                      Day starts
                    </label>
                    <input
                      type="time"
                      value={config.work_start}
                      onChange={(e) =>
                        setConfig((c) => ({ ...c, work_start: e.target.value }))
                      }
                      className="w-full rounded-lg border border-white/10 bg-black/50 px-2.5 py-1.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-neon-green/40"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-bold uppercase tracking-wider text-white/40 block mb-1">
                      Day ends
                    </label>
                    <input
                      type="time"
                      value={config.work_end}
                      onChange={(e) =>
                        setConfig((c) => ({ ...c, work_end: e.target.value }))
                      }
                      className="w-full rounded-lg border border-white/10 bg-black/50 px-2.5 py-1.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-neon-green/40"
                    />
                  </div>
                </div>
              </>
            )}

            {cardShell(
              <UtensilsCrossed className="w-3.5 h-3.5 text-[#22c55e] shrink-0" />,
              "Lunch break",
              <>
                <p className="text-xs text-white/40 mb-2">
                  Slots may not overlap this window. Clear both times to disable.
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-[11px] text-white/50 block mb-1">
                      From
                    </label>
                    <input
                      type="time"
                      value={config.lunch_start}
                      onChange={(e) =>
                        setConfig((c) => ({
                          ...c,
                          lunch_start: e.target.value,
                        }))
                      }
                      className="w-full rounded-lg border border-white/10 bg-black/50 px-2.5 py-1.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-neon-green/40"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] text-white/50 block mb-1">
                      To
                    </label>
                    <input
                      type="time"
                      value={config.lunch_end}
                      onChange={(e) =>
                        setConfig((c) => ({ ...c, lunch_end: e.target.value }))
                      }
                      className="w-full rounded-lg border border-white/10 bg-black/50 px-2.5 py-1.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-neon-green/40"
                    />
                  </div>
                </div>
              </>
            )}

            {cardShell(
              <Timer className="w-3.5 h-3.5 text-[#22c55e] shrink-0" />,
              "Gap between slots",
              <>
                <p className="text-xs text-white/40 mb-2">
                  Minimum minutes between meetings. 0 allows back-to-back when
                  the calendar allows.
                </p>
                <label className="text-[11px] text-white/50 block mb-1">
                  Minutes
                </label>
                <input
                  type="number"
                  min={0}
                  step={1}
                  value={config.gap_mins}
                  onChange={(e) =>
                    setConfig((c) => ({
                      ...c,
                      gap_mins: Math.max(0, parseInt(e.target.value, 10) || 0),
                    }))
                  }
                  className="w-full max-w-[8rem] rounded-lg border border-white/10 bg-black/50 px-2.5 py-1.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-neon-green/40"
                />
              </>
            )}
          </div>

          {/* Holidays: full width below matrix */}
          <section className="bg-[#111111] border border-white/5 rounded-xl overflow-hidden">
            <div className="border-b border-white/5 px-3 py-2 flex items-center gap-2">
              <CalendarOff className="w-3.5 h-3.5 text-[#22c55e]" />
              <h2 className="text-white font-bold text-sm">Holidays</h2>
              <span className="text-xs text-white/40">
                Full-day blocks (date + optional name)
              </span>
            </div>
            <div className="p-3.5 space-y-3">
              <div className="flex flex-col sm:flex-row flex-wrap gap-2 items-end">
                <div className="flex flex-col gap-1">
                  <label className="text-[11px] font-bold uppercase tracking-wider text-white/40 flex items-center gap-1">
                    <CalendarDays className="w-3.5 h-3.5 text-white/45" />
                    Date
                  </label>
                  <input
                    type="date"
                    value={newHolidayDate}
                    onChange={(e) => setNewHolidayDate(e.target.value)}
                    className="rounded-lg border border-white/10 bg-black/50 px-2.5 py-1.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-neon-green/40 [color-scheme:dark] min-w-[11rem]"
                  />
                </div>
                <div className="flex flex-col gap-1 flex-1 min-w-[12rem]">
                  <label className="text-[11px] font-bold uppercase tracking-wider text-white/40">
                    Holiday name / reason
                  </label>
                  <input
                    type="text"
                    value={newHolidayLabel}
                    onChange={(e) => setNewHolidayLabel(e.target.value)}
                    placeholder="e.g. Independence Day, Holi, Diwali…"
                    className="w-full rounded-lg border border-white/10 bg-black/50 px-2.5 py-1.5 text-sm text-white placeholder:text-white/25 focus:outline-none focus:ring-1 focus:ring-neon-green/40"
                  />
                </div>
                <button
                  type="button"
                  onClick={addHoliday}
                  className="inline-flex items-center gap-1 rounded-lg bg-white/10 px-3 py-2 text-sm font-medium text-white hover:bg-white/15 h-[2.25rem] sm:h-auto sm:mb-0"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Add
                </button>
              </div>

              <div className="rounded-lg border border-white/5 overflow-hidden">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/10 bg-black/30 text-white/50">
                      <th className="px-2.5 py-2 font-semibold w-[7.5rem]">
                        Date
                      </th>
                      <th className="px-2.5 py-2 font-semibold">Name / reason</th>
                      <th className="px-2.5 py-2 font-semibold w-[3rem] text-right">
                        {/* remove */}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {holidayRows.length === 0 ? (
                      <tr>
                        <td
                          colSpan={3}
                          className="px-2.5 py-4 text-center text-white/40 text-xs"
                        >
                          No holidays yet. Add a date and optional name, then
                          click Add.
                        </td>
                      </tr>
                    ) : (
                      holidayRows.map((row) => (
                        <tr
                          key={row.date}
                          className="border-b border-white/[0.06] last:border-0"
                        >
                          <td className="px-2.5 py-2 text-white/85 whitespace-nowrap font-mono text-[13px]">
                            {row.date}
                          </td>
                          <td className="px-2.5 py-1.5">
                            <input
                              type="text"
                              value={row.label}
                              onChange={(e) =>
                                updateHolidayLabel(row.date, e.target.value)
                              }
                              placeholder="—"
                              className="w-full rounded border border-transparent bg-transparent px-1 py-0.5 text-sm text-white/90 hover:border-white/10 focus:border-neon-green/40 focus:outline-none"
                            />
                          </td>
                          <td className="px-2 py-1 text-right">
                            <button
                              type="button"
                              onClick={() => removeHolidayByDate(row.date)}
                              className="inline-flex p-1 rounded text-white/35 hover:text-red-300 hover:bg-red-500/10"
                              aria-label={`Remove holiday ${row.date}`}
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
