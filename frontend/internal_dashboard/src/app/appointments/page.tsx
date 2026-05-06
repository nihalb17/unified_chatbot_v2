"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  Calendar,
  Search,
  ExternalLink,
  Clock,
  FileText,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  List,
  CalendarDays,
} from "lucide-react";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_PHASE3_URL || "http://localhost:8002";

// ===== Types =====

interface Appointment {
  booking_code: string;
  topic: string;
  date: string;       // YYYY-MM-DD
  time: string;       // HH:MM
  broker_email?: string;
  doc_link?: string;
  doc_id?: string;
  calendar_event_id?: string;
  calendar_event_link?: string;
  status: string;
  created_at?: string;
}

// ===== Helpers =====

function formatTimeParts(time: string): { clock: string; period: string } {
  const [h, m] = time.split(":").map(Number);
  const period = h >= 12 ? "PM" : "AM";
  const hour = h % 12 || 12;
  return {
    clock: `${hour}:${m.toString().padStart(2, "0")}`,
    period,
  };
}

function formatTime(time: string): string {
  const { clock, period } = formatTimeParts(time);
  return `${clock} ${period}`;
}

function formatDate(date: string): string {
  const d = new Date(date + "T00:00:00");
  return d.toLocaleDateString("en-GB", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function formatDateShort(date: string): string {
  const d = new Date(date + "T00:00:00");
  return d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
  });
}

function isToday(date: string): boolean {
  const today = new Date();
  const d = new Date(date + "T00:00:00");
  return (
    d.getDate() === today.getDate() &&
    d.getMonth() === today.getMonth() &&
    d.getFullYear() === today.getFullYear()
  );
}

function isUpcoming(date: string): boolean {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(date + "T00:00:00");
  return d >= today;
}

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

function getFirstDayOfMonth(year: number, month: number): number {
  return new Date(year, month, 1).getDay();
}

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// ===== Main Page =====

export default function ScheduledAppointments() {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [viewMode, setViewMode] = useState<"list" | "calendar">("list");
  const [filter, setFilter] = useState<"upcoming" | "all">("upcoming");
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() };
  });
  const [selectedCalendarDate, setSelectedCalendarDate] = useState<string | null>(null);

  // Fetch appointments
  const fetchAppointments = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/appointments`);
      const data = await res.json();
      setAppointments(data.appointments || []);
    } catch (err) {
      console.error("Failed to fetch appointments", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAppointments();
  }, []);

  // Search handler
  const handleSearch = async (query: string) => {
    setSearchQuery(query);
    if (query.trim()) {
      try {
        const res = await fetch(`${API_BASE}/api/appointments/search?q=${encodeURIComponent(query)}`);
        const data = await res.json();
        setAppointments(data.appointments || []);
      } catch (err) {
        console.error("Search failed", err);
      }
    } else {
      fetchAppointments();
    }
  };

  // Filtered & sorted appointments
  const filteredAppointments = useMemo(() => {
    let result = [...appointments];

    if (filter === "upcoming") {
      result = result.filter((a) => isUpcoming(a.date));
    }

    // Sort by date, then time
    result.sort((a, b) => {
      const dateCompare = a.date.localeCompare(b.date);
      if (dateCompare !== 0) return dateCompare;
      return a.time.localeCompare(b.time);
    });

    return result;
  }, [appointments, filter]);

  // Group by date for list view
  const groupedByDate = useMemo(() => {
    const groups: Record<string, Appointment[]> = {};
    for (const apt of filteredAppointments) {
      if (!groups[apt.date]) groups[apt.date] = [];
      groups[apt.date].push(apt);
    }
    return groups;
  }, [filteredAppointments]);

  // Calendar day data
  const calendarAppointments = useMemo(() => {
    const byDate: Record<string, Appointment[]> = {};
    for (const apt of appointments) {
      if (!byDate[apt.date]) byDate[apt.date] = [];
      byDate[apt.date].push(apt);
    }
    return byDate;
  }, [appointments]);

  const selectedDateAppointments = useMemo(() => {
    if (!selectedCalendarDate) return [];
    return calendarAppointments[selectedCalendarDate] || [];
  }, [selectedCalendarDate, calendarAppointments]);

  // Calendar navigation
  const prevMonth = () => {
    setCalendarMonth((prev) => {
      const m = prev.month - 1;
      if (m < 0) return { year: prev.year - 1, month: 11 };
      return { ...prev, month: m };
    });
    setSelectedCalendarDate(null);
  };

  const nextMonth = () => {
    setCalendarMonth((prev) => {
      const m = prev.month + 1;
      if (m > 11) return { year: prev.year + 1, month: 0 };
      return { ...prev, month: m };
    });
    setSelectedCalendarDate(null);
  };

  // Stats
  const upcomingCount = appointments.filter((a) => isUpcoming(a.date)).length;
  const todayCount = appointments.filter((a) => isToday(a.date)).length;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen -ml-64">
        <RefreshCw className="animate-spin text-neon-green" size={48} />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-[1200px]">
      {/* Page Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-neon-green rounded-xl flex items-center justify-center text-black">
            <Calendar size={24} strokeWidth={2.5} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              Scheduled Appointments
            </h1>
            <p className="text-white/40 text-[10px] font-medium mt-0.5">
              View and manage advisor calls booked through the assistant
            </p>
          </div>
        </div>

        <button
          onClick={fetchAppointments}
          className="flex items-center gap-2 bg-neon-green text-black px-4 py-2 rounded-lg font-bold text-xs hover:brightness-110 transition-all"
        >
          <RefreshCw size={14} strokeWidth={3} />
          Refresh
        </button>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-[#111111] border border-white/5 p-4 rounded-xl flex justify-between">
          <div>
            <div className="text-[9px] text-white/40 uppercase tracking-[0.1em] font-bold mb-2">
              TOTAL BOOKED
            </div>
            <div className="text-2xl font-bold text-white tracking-tight">
              {appointments.length}
            </div>
            <div className="text-[9px] text-white/30 font-medium">all time</div>
          </div>
          <div className="w-8 h-8 rounded-lg bg-[#22c55e]/10 text-[#22c55e] flex items-center justify-center">
            <Calendar size={16} strokeWidth={2.5} />
          </div>
        </div>

        <div className="bg-[#111111] border border-white/5 p-4 rounded-xl flex justify-between">
          <div>
            <div className="text-[9px] text-white/40 uppercase tracking-[0.1em] font-bold mb-2">
              UPCOMING
            </div>
            <div className="text-2xl font-bold text-white tracking-tight">
              {upcomingCount}
            </div>
            <div className="text-[9px] text-white/30 font-medium">scheduled ahead</div>
          </div>
          <div className="w-8 h-8 rounded-lg bg-blue-500/10 text-blue-400 flex items-center justify-center">
            <Clock size={16} strokeWidth={2.5} />
          </div>
        </div>

        <div className="bg-[#111111] border border-white/5 p-4 rounded-xl flex justify-between">
          <div>
            <div className="text-[9px] text-white/40 uppercase tracking-[0.1em] font-bold mb-2">
              TODAY
            </div>
            <div className="text-2xl font-bold text-white tracking-tight">
              {todayCount}
            </div>
            <div className="text-[9px] text-white/30 font-medium">calls today</div>
          </div>
          <div className="w-8 h-8 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center">
            <CalendarDays size={16} strokeWidth={2.5} />
          </div>
        </div>
      </div>

      {/* View Toggle + Search + Filter */}
      <div className="flex items-center gap-3">
        {/* View Mode Toggle */}
        <div className="flex bg-[#111111] border border-white/5 rounded-lg overflow-hidden">
          <button
            onClick={() => setViewMode("list")}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-xs font-bold transition-all",
              viewMode === "list"
                ? "bg-neon-green text-black"
                : "text-white/40 hover:text-white/70"
            )}
          >
            <List size={14} />
            List
          </button>
          <button
            onClick={() => setViewMode("calendar")}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 text-xs font-bold transition-all",
              viewMode === "calendar"
                ? "bg-neon-green text-black"
                : "text-white/40 hover:text-white/70"
            )}
          >
            <CalendarDays size={14} />
            Calendar
          </button>
        </div>

        {/* Filter Tabs */}
        <div className="flex bg-[#111111] border border-white/5 rounded-lg overflow-hidden">
          <button
            onClick={() => setFilter("upcoming")}
            className={cn(
              "px-4 py-2.5 text-xs font-bold transition-all",
              filter === "upcoming"
                ? "bg-white/10 text-white"
                : "text-white/40 hover:text-white/70"
            )}
          >
            Upcoming
          </button>
          <button
            onClick={() => setFilter("all")}
            className={cn(
              "px-4 py-2.5 text-xs font-bold transition-all",
              filter === "all"
                ? "bg-white/10 text-white"
                : "text-white/40 hover:text-white/70"
            )}
          >
            All
          </button>
        </div>

        {/* Search */}
        <div className="flex-1 relative">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-white/20"
          />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Search by booking code or topic..."
            className="w-full bg-[#0A0A0A] border border-white/10 rounded-lg pl-9 pr-4 py-2.5 text-sm text-white placeholder:text-white/20 focus:outline-none focus:border-[#22c55e]/50 transition-colors"
          />
        </div>
      </div>

      {/* Content */}
      {viewMode === "list" ? (
        <ListView
          groupedByDate={groupedByDate}
          totalCount={filteredAppointments.length}
        />
      ) : (
        <CalendarView
          calendarMonth={calendarMonth}
          calendarAppointments={calendarAppointments}
          selectedCalendarDate={selectedCalendarDate}
          selectedDateAppointments={selectedDateAppointments}
          prevMonth={prevMonth}
          nextMonth={nextMonth}
          selectDate={setSelectedCalendarDate}
        />
      )}
    </div>
  );
}

// ===== List View =====

function ListView({
  groupedByDate,
  totalCount,
}: {
  groupedByDate: Record<string, Appointment[]>;
  totalCount: number;
}) {
  const dates = Object.keys(groupedByDate).sort();

  if (totalCount === 0) {
    return (
      <div
        className="rounded-2xl border border-white/10 bg-gradient-to-b from-zinc-900/95 to-zinc-950/98 p-12 text-center shadow-xl shadow-black/50 ring-1 ring-white/[0.07]"
      >
        <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.05] text-zinc-500">
          <Calendar size={36} strokeWidth={2} className="text-zinc-400" />
        </div>
        <div className="text-base font-semibold text-zinc-200">
          No appointments found
        </div>
        <div className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-zinc-500">
          Appointments will appear here when booked through the assistant
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {dates.map((date) => (
        <div key={date}>
          {/* Date Header */}
          <div className="mb-2 flex items-center gap-3">
            <div
              className={cn(
                "h-2.5 w-2.5 shrink-0 rounded-full shadow-sm",
                isToday(date)
                  ? "bg-[#4ade80] shadow-[#22c55e]/40"
                  : isUpcoming(date)
                    ? "bg-sky-400 shadow-sky-400/30"
                    : "bg-zinc-500"
              )}
            />
            <h3 className="text-base font-bold tracking-tight text-zinc-100">
              {formatDate(date)}
            </h3>
            {isToday(date) && (
              <span className="rounded-md border border-[#22c55e]/35 bg-[#22c55e]/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-[#4ade80]">
                Today
              </span>
            )}
            <div className="h-px flex-1 bg-gradient-to-r from-white/15 to-transparent" />
            <span className="shrink-0 text-[11px] font-bold uppercase tracking-wider text-zinc-500">
              {groupedByDate[date].length}{" "}
              {groupedByDate[date].length === 1 ? "appointment" : "appointments"}
            </span>
          </div>

          {/* Appointment rows */}
          <div className="space-y-1.5">
            {groupedByDate[date].map((apt) => (
              <AppointmentCard key={apt.booking_code} appointment={apt} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ===== Appointment Card =====

function AppointmentCard({ appointment: apt }: { appointment: Appointment }) {
  const { clock, period } = formatTimeParts(apt.time);
  return (
    <div className="group flex items-center gap-2 rounded-xl border border-white/10 bg-gradient-to-b from-zinc-900/95 to-zinc-950/98 px-2.5 py-1 shadow-md shadow-black/30 ring-1 ring-white/[0.07] transition-all hover:border-white/15 sm:gap-3 sm:px-3 sm:py-1.5">
      <div
        className="flex w-[3.85rem] shrink-0 items-baseline gap-0.5 border-r border-white/10 pr-2 sm:w-[4rem] sm:pr-3"
        title={formatTime(apt.time)}
      >
        <span className="text-[13px] font-bold tabular-nums leading-none text-white">
          {clock}
        </span>
        <span className="text-[8px] font-bold leading-none text-zinc-500">
          {period}
        </span>
      </div>

      <p className="min-w-0 flex-1 truncate text-[13px] font-semibold leading-tight text-zinc-100">
        {apt.topic}
      </p>

      <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
        <span className="max-w-[3.5rem] shrink-0 truncate font-mono text-[10px] font-bold text-zinc-400 tabular-nums sm:max-w-none sm:text-[11px]">
          #{apt.booking_code}
        </span>

        {apt.doc_link && (
          <a
            href={apt.doc_link}
            target="_blank"
            rel="noopener noreferrer"
            title="Meeting notes"
            className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-[#22c55e]/25 bg-[#22c55e]/10 text-[#4ade80] transition-colors hover:border-[#22c55e]/45 hover:bg-[#22c55e]/20 sm:h-auto sm:w-auto sm:gap-1 sm:px-2 sm:py-1"
          >
            <FileText size={12} strokeWidth={2.25} />
            <span className="hidden text-[10px] font-semibold sm:inline">Notes</span>
          </a>
        )}

        {apt.calendar_event_link && (
          <a
            href={apt.calendar_event_link}
            target="_blank"
            rel="noopener noreferrer"
            title="Calendar event"
            className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-sky-500/30 bg-sky-500/10 text-sky-300 transition-colors hover:border-sky-400/50 hover:bg-sky-500/15 sm:h-auto sm:w-auto sm:gap-1 sm:px-2 sm:py-1"
          >
            <Calendar size={12} strokeWidth={2.25} />
            <span className="hidden text-[10px] font-semibold sm:inline">Cal</span>
          </a>
        )}
      </div>
    </div>
  );
}

// ===== Calendar View =====

function CalendarView({
  calendarMonth,
  calendarAppointments,
  selectedCalendarDate,
  selectedDateAppointments,
  prevMonth,
  nextMonth,
  selectDate,
}: {
  calendarMonth: { year: number; month: number };
  calendarAppointments: Record<string, Appointment[]>;
  selectedCalendarDate: string | null;
  selectedDateAppointments: Appointment[];
  prevMonth: () => void;
  nextMonth: () => void;
  selectDate: (date: string | null) => void;
}) {
  const { year, month } = calendarMonth;
  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfMonth(year, month);
  const today = new Date();

  // Build calendar grid
  const cells: (number | null)[] = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  const dateStr = (day: number) =>
    `${year}-${(month + 1).toString().padStart(2, "0")}-${day
      .toString()
      .padStart(2, "0")}`;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-6">
      {/* Calendar Grid */}
      <div
        className="rounded-2xl border border-white/10 bg-gradient-to-b from-zinc-900/95 to-zinc-950/98 p-6 shadow-xl shadow-black/50 ring-1 ring-white/[0.07]"
      >
        {/* Month Navigation */}
        <div className="flex items-center justify-between mb-6">
          <button
            type="button"
            onClick={prevMonth}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/[0.06] text-zinc-300 transition-all hover:border-white/20 hover:bg-white/10 hover:text-white"
            aria-label="Previous month"
          >
            <ChevronLeft size={18} strokeWidth={2.25} />
          </button>
          <div className="text-center">
            <h3 className="text-lg font-bold tracking-tight text-white">
              {MONTHS[month]} {year}
            </h3>
            <p className="mt-0.5 text-[11px] font-medium uppercase tracking-[0.14em] text-zinc-500">
              Schedule
            </p>
          </div>
          <button
            type="button"
            onClick={nextMonth}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/[0.06] text-zinc-300 transition-all hover:border-white/20 hover:bg-white/10 hover:text-white"
            aria-label="Next month"
          >
            <ChevronRight size={18} strokeWidth={2.25} />
          </button>
        </div>

        {/* Weekday Headers */}
        <div className="mb-3 grid grid-cols-7 gap-1.5">
          {WEEKDAYS.map((day) => (
            <div
              key={day}
              className="py-2 text-center text-[11px] font-bold uppercase tracking-wider text-zinc-400"
            >
              {day}
            </div>
          ))}
        </div>

        {/* Day Cells */}
        <div className="grid grid-cols-7 gap-1.5">
          {cells.map((day, idx) => {
            if (day === null) {
              return (
                <div
                  key={`empty-${idx}`}
                  className="min-h-[5.25rem] rounded-xl bg-zinc-950/40"
                />
              );
            }

            const ds = dateStr(day);
            const apts = calendarAppointments[ds] || [];
            const isCurrentDay =
              day === today.getDate() &&
              month === today.getMonth() &&
              year === today.getFullYear();
            const isSelected = selectedCalendarDate === ds;

            return (
              <button
                type="button"
                key={ds}
                onClick={() => selectDate(isSelected ? null : ds)}
                className={cn(
                  "relative min-h-[5.25rem] rounded-xl border p-2 text-left transition-all duration-150",
                  isSelected &&
                    "z-[1] border-[#22c55e] bg-[#22c55e]/15 shadow-[0_0_0_1px_rgba(34,197,94,0.35),0_8px_24px_-4px_rgba(34,197,94,0.12)]",
                  !isSelected &&
                    apts.length > 0 &&
                    "border-emerald-500/25 bg-emerald-500/[0.08] hover:border-emerald-400/40 hover:bg-emerald-500/[0.12]",
                  !isSelected &&
                    apts.length === 0 &&
                    "border-white/[0.08] bg-white/[0.03] hover:border-white/15 hover:bg-white/[0.06]",
                  isCurrentDay &&
                    !isSelected &&
                    "ring-2 ring-[#22c55e]/50 ring-offset-2 ring-offset-zinc-950"
                )}
              >
                <span
                  className={cn(
                    "inline-flex h-6 min-w-[1.5rem] items-center justify-center text-[13px] font-bold tabular-nums",
                    isCurrentDay && "text-[#4ade80]",
                    !isCurrentDay && apts.length > 0 && "text-zinc-100",
                    !isCurrentDay && apts.length === 0 && "text-zinc-400"
                  )}
                >
                  {day}
                </span>
                {apts.length > 0 && (
                  <div className="mt-1 space-y-1">
                    {apts.slice(0, 2).map((apt) => (
                      <div
                        key={apt.booking_code}
                        className="truncate rounded-md border border-[#22c55e]/20 bg-[#22c55e]/15 px-1.5 py-0.5 text-[9px] font-semibold leading-snug text-emerald-100/95"
                      >
                        {formatTime(apt.time)} · {apt.topic}
                      </div>
                    ))}
                    {apts.length > 2 && (
                      <div className="text-center text-[9px] font-semibold text-zinc-500">
                        +{apts.length - 2} more
                      </div>
                    )}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Selected Date Detail */}
      <div
        className="h-fit rounded-2xl border border-white/10 bg-gradient-to-b from-zinc-900/95 to-zinc-950/98 p-6 shadow-xl shadow-black/50 ring-1 ring-white/[0.07] lg:sticky lg:top-12"
      >
        {selectedCalendarDate ? (
          <>
            <h4 className="text-base font-bold tracking-tight text-white">
              {formatDate(selectedCalendarDate)}
            </h4>
            <p className="mb-5 mt-1 text-xs font-medium text-zinc-400">
              {selectedDateAppointments.length}{" "}
              {selectedDateAppointments.length === 1
                ? "appointment"
                : "appointments"}
            </p>

            {selectedDateAppointments.length === 0 ? (
              <div className="rounded-xl border border-dashed border-white/10 bg-zinc-950/50 py-10 text-center text-sm text-zinc-500">
                No appointments on this date
              </div>
            ) : (
              <div className="space-y-3">
                {selectedDateAppointments.map((apt) => (
                  <div
                    key={apt.booking_code}
                    className="rounded-xl border border-white/10 bg-zinc-950/80 p-4 shadow-inner shadow-black/20"
                  >
                    <div className="mb-2 flex items-center gap-2">
                      <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#22c55e]/20 text-[#4ade80]">
                        <Clock size={14} strokeWidth={2.25} />
                      </div>
                      <span className="text-sm font-bold text-white">
                        {formatTime(apt.time)}
                      </span>
                      <span className="ml-auto rounded-md bg-white/5 px-2 py-0.5 font-mono text-[10px] font-semibold text-zinc-400">
                        #{apt.booking_code}
                      </span>
                    </div>
                    <div className="text-[15px] font-semibold leading-snug text-zinc-100">
                      {apt.topic}
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {apt.doc_link && (
                        <a
                          href={apt.doc_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1.5 rounded-lg border border-[#22c55e]/25 bg-[#22c55e]/10 px-2.5 py-1.5 text-[11px] font-semibold text-[#4ade80] transition-colors hover:border-[#22c55e]/45 hover:bg-[#22c55e]/20"
                        >
                          <FileText size={12} />
                          Notes
                        </a>
                      )}
                      {apt.calendar_event_link && (
                        <a
                          href={apt.calendar_event_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1.5 rounded-lg border border-sky-500/30 bg-sky-500/10 px-2.5 py-1.5 text-[11px] font-semibold text-sky-300 transition-colors hover:border-sky-400/50 hover:bg-sky-500/15"
                        >
                          <Calendar size={12} />
                          Event
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : (
          <div className="flex flex-col items-center py-10 text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.05] text-zinc-500">
              <CalendarDays size={28} strokeWidth={2} className="text-zinc-400" />
            </div>
            <div className="max-w-[220px] text-sm font-medium leading-relaxed text-zinc-400">
              Select a date on the calendar to view appointments
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
