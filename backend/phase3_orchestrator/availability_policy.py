"""Meeting slot availability policy.

Single source of truth for the rules that gate appointment booking:
  - Working weekdays (which days of the week accept bookings; Python weekday:
    Monday = 0 … Sunday = 6)
  - Holidays (whole-day block)
  - Working hours (slot must fully fit inside)
  - Lunchtime (slot must not overlap)
  - Minimum gap between back-to-back meetings

The policy is loaded from ``config/slot_config.json`` (created on first save
from the internal dashboard). When the file is missing or malformed, the
module falls back to defaults that match historical behaviour
(work 09:00 to 18:00, lunch 13:00 to 14:00, gap 0, Mon–Fri, no holidays).

Both ``check_slot_availability_node`` and the next-slot suggestion logic
import from here so the rules cannot drift apart.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")
SLOT_CONFIG_FILE = os.path.join(CONFIG_DIR, "slot_config.json")

# Defaults preserve current product behaviour while introducing lunch.
DEFAULT_POLICY_DICT: dict = {
    "work_start": "09:00",
    "work_end": "18:00",
    "lunch_start": "13:00",
    "lunch_end": "14:00",
    "gap_mins": 0,
    # Monday–Friday (datetime.weekday(): Mon=0 … Sun=6)
    "work_weekdays": [0, 1, 2, 3, 4],
    # Each entry: "YYYY-MM-DD" or "YYYY-MM-DD|Holiday name" (label after first |).
    "holidays": [],
}


# ---------------------------------------------------------------------------
# Dataclass and parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Policy:
    """Validated, immutable view of the slot policy.

    Times are ``datetime.time`` (naive, IST). ``holiday_entries`` lists each
    blocked day with an optional display label. Use ``.holidays`` for the set
    of dates. ``work_weekdays`` uses ``datetime.weekday()`` numbering (Monday = 0).
    """

    work_start: time
    work_end: time
    lunch_start: Optional[time]
    lunch_end: Optional[time]
    gap_mins: int
    work_weekdays: frozenset[int]
    holiday_entries: tuple[tuple[date, str], ...] = field(default_factory=tuple)

    @property
    def holidays(self) -> frozenset[date]:
        return frozenset(d for d, _ in self.holiday_entries)

    @property
    def has_lunch(self) -> bool:
        return self.lunch_start is not None and self.lunch_end is not None

    def holiday_label(self, d: date) -> str:
        for hd, lab in self.holiday_entries:
            if hd == d:
                return lab
        return ""


def _parse_time(value: str, field_name: str) -> time:
    """Accept ``HH:MM`` (24h). Raise ValueError with a clear message."""
    try:
        return datetime.strptime(value.strip(), "%H:%M").time()
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be HH:MM, got {value!r}") from exc


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"holiday date must be YYYY-MM-DD, got {value!r}") from exc


def _parse_holiday_entry(value: str) -> tuple[date, str]:
    """Parse ``YYYY-MM-DD`` or ``YYYY-MM-DD|Label`` (only first ``|`` splits)."""
    if not isinstance(value, str):
        raise ValueError(f"holiday entry must be a string, got {value!r}")
    raw = value.strip()
    if "|" in raw:
        date_part, label_part = raw.split("|", 1)
        return _parse_date(date_part), label_part.strip()
    return _parse_date(raw), ""


def _coerce_policy(raw: dict) -> Policy:
    """Build a Policy from a raw dict, applying defaults and validating.

    Validation rules (raise ValueError on violation, with a precise reason):
      - work_end > work_start
      - if lunch is set: both ends present, lunch_end > lunch_start, lunch fully inside work hours
      - gap_mins >= 0
      - holidays parse cleanly
    """
    merged = {**DEFAULT_POLICY_DICT, **(raw or {})}

    work_start = _parse_time(merged["work_start"], "work_start")
    work_end = _parse_time(merged["work_end"], "work_end")
    if work_end <= work_start:
        raise ValueError("work_end must be after work_start")

    lunch_start_raw = merged.get("lunch_start")
    lunch_end_raw = merged.get("lunch_end")
    if (lunch_start_raw and not lunch_end_raw) or (lunch_end_raw and not lunch_start_raw):
        raise ValueError("lunch_start and lunch_end must both be set or both empty")

    lunch_start: Optional[time] = None
    lunch_end: Optional[time] = None
    if lunch_start_raw and lunch_end_raw:
        lunch_start = _parse_time(lunch_start_raw, "lunch_start")
        lunch_end = _parse_time(lunch_end_raw, "lunch_end")
        if lunch_end <= lunch_start:
            raise ValueError("lunch_end must be after lunch_start")
        if lunch_start < work_start or lunch_end > work_end:
            raise ValueError("lunch window must lie inside working hours")

    gap_mins_raw = merged.get("gap_mins", 0)
    try:
        gap_mins = int(gap_mins_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"gap_mins must be an integer, got {gap_mins_raw!r}") from exc
    if gap_mins < 0:
        raise ValueError("gap_mins must be >= 0")

    ww_raw = merged.get("work_weekdays")
    if ww_raw is None:
        ww_raw = DEFAULT_POLICY_DICT["work_weekdays"]
    if not isinstance(ww_raw, list) or len(ww_raw) == 0:
        raise ValueError("work_weekdays must be a non-empty list of integers 0–6 (Mon–Sun)")
    work_weekdays_set: set[int] = set()
    for x in ww_raw:
        try:
            xi = int(x)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"work_weekdays entries must be integers 0–6, got {x!r}") from exc
        if xi < 0 or xi > 6:
            raise ValueError(f"work_weekdays must be between 0 (Monday) and 6 (Sunday), got {xi}")
        work_weekdays_set.add(xi)
    work_weekdays = frozenset(work_weekdays_set)

    holidays_raw = merged.get("holidays") or []
    if not isinstance(holidays_raw, list):
        raise ValueError("holidays must be a list of YYYY-MM-DD strings (optional |label)")
    parsed: list[tuple[date, str]] = []
    seen_dates: set[date] = set()
    for h in holidays_raw:
        d, label = _parse_holiday_entry(h)
        if d in seen_dates:
            raise ValueError(f"duplicate holiday date {d.strftime('%Y-%m-%d')}")
        seen_dates.add(d)
        parsed.append((d, label))
    holiday_entries = tuple(sorted(parsed, key=lambda x: x[0]))

    return Policy(
        work_start=work_start,
        work_end=work_end,
        lunch_start=lunch_start,
        lunch_end=lunch_end,
        gap_mins=gap_mins,
        work_weekdays=work_weekdays,
        holiday_entries=holiday_entries,
    )


def _holiday_entry_to_str(d: date, label: str) -> str:
    s = d.strftime("%Y-%m-%d")
    lab = (label or "").strip()
    return f"{s}|{lab}" if lab else s


def policy_to_dict(policy: Policy) -> dict:
    """Serialise a Policy back to JSON-friendly dict."""
    return {
        "work_start": policy.work_start.strftime("%H:%M"),
        "work_end": policy.work_end.strftime("%H:%M"),
        "lunch_start": policy.lunch_start.strftime("%H:%M") if policy.lunch_start else "",
        "lunch_end": policy.lunch_end.strftime("%H:%M") if policy.lunch_end else "",
        "gap_mins": policy.gap_mins,
        "work_weekdays": sorted(policy.work_weekdays),
        "holidays": [
            _holiday_entry_to_str(d, lab) for d, lab in sorted(policy.holiday_entries, key=lambda x: x[0])
        ],
    }


# ---------------------------------------------------------------------------
# Disk IO with mtime cache (avoids rereading the file on every chat turn).
# ---------------------------------------------------------------------------


_lock = threading.Lock()
_cache: dict = {"mtime": None, "policy": None}


def _read_file() -> dict:
    if not os.path.exists(SLOT_CONFIG_FILE):
        return {}
    with open(SLOT_CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_policy() -> Policy:
    """Return the current policy, rereading the file only when its mtime changes."""
    try:
        mtime = os.path.getmtime(SLOT_CONFIG_FILE) if os.path.exists(SLOT_CONFIG_FILE) else 0
    except OSError:
        mtime = 0

    with _lock:
        cached_policy = _cache["policy"]
        if cached_policy is not None and _cache["mtime"] == mtime:
            return cached_policy

    # Outside the lock: legacy JSON files may omit work_weekdays (older writers).
    # They still parse as Mon–Fri via DEFAULT_POLICY_DICT merge, but then every PUT
    # must rewrite the full shape; if the process never ran new code, the key stays
    # missing and weekdays never persist. Re-save once to normalize the file.
    try:
        raw = _read_file()
        policy = _coerce_policy(raw)
        if (
            raw
            and isinstance(raw, dict)
            and "work_weekdays" not in raw
            and os.path.exists(SLOT_CONFIG_FILE)
        ):
            policy = save_policy(policy_to_dict(policy))
    except Exception as exc:
        logger.error("[policy] Could not load %s, using defaults: %s", SLOT_CONFIG_FILE, exc)
        policy = _coerce_policy({})

    try:
        mtime_after = os.path.getmtime(SLOT_CONFIG_FILE) if os.path.exists(SLOT_CONFIG_FILE) else 0
    except OSError:
        mtime_after = 0
    with _lock:
        _cache["mtime"] = mtime_after
        _cache["policy"] = policy
    return policy


def save_policy(raw: dict) -> Policy:
    """Validate and persist the policy. Returns the parsed Policy.

    Atomic write (tmp file then rename) so a crash mid-save cannot corrupt the file.
    """
    policy = _coerce_policy(raw)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp_path = SLOT_CONFIG_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(policy_to_dict(policy), f, indent=2)
    os.replace(tmp_path, SLOT_CONFIG_FILE)
    with _lock:
        _cache["mtime"] = os.path.getmtime(SLOT_CONFIG_FILE)
        _cache["policy"] = policy
    return policy


# ---------------------------------------------------------------------------
# Validation primitives
# ---------------------------------------------------------------------------


def _slot_overlaps(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    """Half-open overlap: [a_start, a_end) intersects [b_start, b_end)."""
    return a_start < b_end and b_start < a_end


def _has_gap_conflict(
    slot_start: datetime,
    slot_end: datetime,
    busy: Iterable[tuple[datetime, datetime]],
    gap_mins: int,
) -> Optional[tuple[datetime, datetime]]:
    """Return the first event that violates the gap rule, else None.

    Uses strict ``>`` and ``<`` so an event ending exactly at ``slot_start - gap``
    (or starting exactly at ``slot_end + gap``) is allowed. With ``gap_mins == 0``
    this collapses to plain interval overlap, which is what back-to-back booking
    needs.
    """
    gap = timedelta(minutes=gap_mins)
    for ev_start, ev_end in busy:
        # Event ends too close before our slot starts.
        if ev_end > slot_start - gap and ev_start < slot_end:
            return ev_start, ev_end
        # Event starts too close after our slot ends.
        if ev_start < slot_end + gap and ev_end > slot_start:
            return ev_start, ev_end
    return None


def validate_slot(
    slot_start: datetime,
    slot_end: datetime,
    busy: Iterable[tuple[datetime, datetime]] = (),
    policy: Optional[Policy] = None,
) -> tuple[bool, str]:
    """Validate a desired slot against policy + (optional) busy events.

    Returns ``(ok, reason)``. ``reason`` is empty when ``ok`` is True.

    Times are naive IST datetimes. ``busy`` is a list of (start, end) IST datetimes
    representing existing calendar events. The gap rule is applied here, so the
    caller does not need to pre-pad ``busy`` intervals.
    """
    if policy is None:
        policy = load_policy()

    if slot_end <= slot_start:
        return (
            False,
            "That time range is not valid. Please choose an end time after the start time.",
        )

    if slot_start.date() != slot_end.date():
        return (
            False,
            "Please keep your meeting within a single calendar day.",
        )

    if slot_start.date() in policy.holidays:
        lab = policy.holiday_label(slot_start.date())
        date_h = slot_start.strftime("%d %b %Y")
        if lab:
            return (
                False,
                f"We are closed on {date_h} for {lab}. Please pick another date.",
            )
        return (
            False,
            f"We are closed on {date_h} for a scheduled holiday. Please pick another date.",
        )

    if slot_start.weekday() not in policy.work_weekdays:
        day_name = slot_start.strftime("%A")
        return (
            False,
            f"Our office is not open for bookings on {day_name}s. "
            f"Please choose a day when we are open.",
        )

    s_t = slot_start.time()
    e_t = slot_end.time()

    if s_t < policy.work_start or e_t > policy.work_end:
        return (
            False,
            f"Our office hours for bookings are {policy.work_start:%H:%M} to "
            f"{policy.work_end:%H:%M} (IST). Please choose a time within that window.",
        )

    if policy.has_lunch and _slot_overlaps(
        s_t, e_t, policy.lunch_start, policy.lunch_end
    ):
        return (
            False,
            f"That time is during our lunch break ({policy.lunch_start:%H:%M} to "
            f"{policy.lunch_end:%H:%M}). Please pick a different time.",
        )

    conflict = _has_gap_conflict(slot_start, slot_end, busy, policy.gap_mins)
    if conflict is not None:
        ev_s, ev_e = conflict
        if policy.gap_mins > 0:
            return (
                False,
                f"We need at least {policy.gap_mins} minutes between meetings. "
                f"That slot is too close to another one ({ev_s:%H:%M} to {ev_e:%H:%M}). "
                f"Please choose a different time.",
            )
        return (
            False,
            f"That time overlaps another commitment ({ev_s:%H:%M} to {ev_e:%H:%M}). "
            f"Please choose a different slot.",
        )

    return True, ""


# ---------------------------------------------------------------------------
# Suggestion: next compliant slot
# ---------------------------------------------------------------------------


def _round_up_to_30_min(dt: datetime) -> datetime:
    """Round up to the next :00 or :30 boundary."""
    base = dt.replace(second=0, microsecond=0)
    if base == dt and base.minute in (0, 30):
        return base
    minute = (base.minute // 30 + 1) * 30
    if minute >= 60:
        return base.replace(minute=0) + timedelta(hours=1)
    return base.replace(minute=minute)


def _align_to_allowed_weekday(candidate: datetime, policy: Policy) -> datetime:
    """If ``candidate`` falls on a non-working weekday, jump forward day by day."""
    guard = 0
    while candidate.weekday() not in policy.work_weekdays and guard < 14:
        candidate = (candidate + timedelta(days=1)).replace(
            hour=policy.work_start.hour,
            minute=policy.work_start.minute,
            second=0,
            microsecond=0,
        )
        guard += 1
    return candidate


def next_compliant_slot(
    after_ist: datetime,
    busy: Iterable[tuple[datetime, datetime]] = (),
    duration_mins: int = 30,
    search_days: int = 14,
    policy: Optional[Policy] = None,
) -> Optional[dict]:
    """Find the next slot that satisfies the full policy + calendar.

    Walks forward in 30-minute increments inside working hours, skipping
    non-working weekdays, holidays, lunch and busy intervals (with gap).

    Returns ``{"start_ist": datetime, "end_ist": datetime, "reason": ""}``
    or ``None`` if no slot is available within ``search_days`` days.
    """
    if policy is None:
        policy = load_policy()

    busy = list(busy)
    candidate = _round_up_to_30_min(after_ist)
    horizon = after_ist + timedelta(days=search_days)

    # 30-min steps across at most ~14 days of business hours = bounded.
    max_iterations = (search_days + 1) * 24 * 2
    for _ in range(max_iterations):
        if candidate >= horizon:
            return None

        candidate = _align_to_allowed_weekday(candidate, policy)

        # Skip holidays whole day.
        if candidate.date() in policy.holidays:
            next_day = candidate + timedelta(days=1)
            candidate = next_day.replace(
                hour=policy.work_start.hour,
                minute=policy.work_start.minute,
                second=0,
                microsecond=0,
            )
            continue

        # Snap to start of working hours if before.
        if candidate.time() < policy.work_start:
            candidate = candidate.replace(
                hour=policy.work_start.hour,
                minute=policy.work_start.minute,
                second=0,
                microsecond=0,
            )

        # Slot must end within working hours.
        slot_end = candidate + timedelta(minutes=duration_mins)
        end_of_work = candidate.replace(
            hour=policy.work_end.hour,
            minute=policy.work_end.minute,
            second=0,
            microsecond=0,
        )
        if slot_end > end_of_work:
            next_day = candidate + timedelta(days=1)
            candidate = _align_to_allowed_weekday(
                next_day.replace(
                    hour=policy.work_start.hour,
                    minute=policy.work_start.minute,
                    second=0,
                    microsecond=0,
                ),
                policy,
            )
            continue

        ok, _reason = validate_slot(candidate, slot_end, busy, policy)
        if ok:
            return {"start_ist": candidate, "end_ist": slot_end, "reason": ""}

        candidate += timedelta(minutes=30)

    return None
