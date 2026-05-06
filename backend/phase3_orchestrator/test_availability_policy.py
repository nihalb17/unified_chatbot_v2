"""Unit tests for availability_policy.

Run from the phase3_orchestrator directory:
    python -m unittest test_availability_policy
or simply:
    python test_availability_policy.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))

import availability_policy as ap


# Helper: build a Policy directly so tests do not depend on disk IO.
def make_policy(
    work_start: str = "09:00",
    work_end: str = "18:00",
    lunch_start: str | None = "13:00",
    lunch_end: str | None = "14:00",
    gap_mins: int = 0,
    holidays: list[str] | None = None,
    work_weekdays: list[int] | None = None,
) -> ap.Policy:
    payload: dict = {
        "work_start": work_start,
        "work_end": work_end,
        "lunch_start": lunch_start or "",
        "lunch_end": lunch_end or "",
        "gap_mins": gap_mins,
        "holidays": holidays or [],
    }
    if work_weekdays is not None:
        payload["work_weekdays"] = work_weekdays
    return ap._coerce_policy(payload)


def at(d: str, t: str) -> datetime:
    """Convenience: '2026-05-04', '09:30' -> datetime."""
    return datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M")


class CoercePolicyTests(unittest.TestCase):
    def test_defaults_round_trip(self):
        p = ap._coerce_policy({})
        self.assertEqual(p.work_start, time(9, 0))
        self.assertEqual(p.work_end, time(18, 0))
        self.assertEqual(p.lunch_start, time(13, 0))
        self.assertEqual(p.lunch_end, time(14, 0))
        self.assertEqual(p.gap_mins, 0)
        self.assertEqual(p.work_weekdays, frozenset(range(5)))
        self.assertEqual(p.holidays, frozenset())

    def test_work_end_must_be_after_start(self):
        with self.assertRaises(ValueError):
            make_policy(work_start="18:00", work_end="09:00")

    def test_partial_lunch_is_invalid(self):
        with self.assertRaises(ValueError):
            make_policy(lunch_start="13:00", lunch_end=None)

    def test_lunch_outside_work_hours_is_invalid(self):
        with self.assertRaises(ValueError):
            make_policy(work_start="09:00", work_end="12:00", lunch_start="13:00", lunch_end="14:00")

    def test_gap_must_be_non_negative(self):
        with self.assertRaises(ValueError):
            make_policy(gap_mins=-5)

    def test_holidays_parse_strict(self):
        with self.assertRaises(ValueError):
            make_policy(holidays=["2026/05/04"])

    def test_holiday_with_label_parses(self):
        p = make_policy(holidays=["2026-08-15|Independence Day"])
        self.assertEqual(p.holiday_label(date(2026, 8, 15)), "Independence Day")
        self.assertIn(date(2026, 8, 15), p.holidays)

    def test_duplicate_holiday_date_rejected(self):
        with self.assertRaises(ValueError):
            make_policy(holidays=["2026-05-04", "2026-05-04|Dup"])

    def test_labeled_holiday_round_trip_dict(self):
        p = make_policy(holidays=["2026-03-14|Holi", "2026-01-01"])
        d = ap.policy_to_dict(p)
        self.assertIn("2026-03-14|Holi", d["holidays"])
        self.assertIn("2026-01-01", d["holidays"])

    def test_no_lunch_is_allowed(self):
        p = make_policy(lunch_start="", lunch_end="")
        self.assertFalse(p.has_lunch)

    def test_empty_work_weekdays_invalid(self):
        with self.assertRaises(ValueError):
            make_policy(work_weekdays=[])


class ValidateSlotPolicyTests(unittest.TestCase):
    def test_holiday_blocks_full_day(self):
        p = make_policy(holidays=["2026-05-04"])
        ok, reason = ap.validate_slot(at("2026-05-04", "11:00"), at("2026-05-04", "11:30"), policy=p)
        self.assertFalse(ok)
        self.assertIn("holiday", reason.lower())

    def test_holiday_reason_includes_label_when_set(self):
        p = make_policy(holidays=["2026-05-04|Labour Day"])
        ok, reason = ap.validate_slot(at("2026-05-04", "11:00"), at("2026-05-04", "11:30"), policy=p)
        self.assertFalse(ok)
        self.assertIn("Labour Day", reason)

    def test_inside_working_hours_passes(self):
        p = make_policy(lunch_start="", lunch_end="")
        ok, reason = ap.validate_slot(at("2026-05-04", "10:00"), at("2026-05-04", "10:30"), policy=p)
        self.assertTrue(ok, reason)

    def test_non_working_weekday_fails(self):
        # 2026-05-09 is Saturday (weekday 5); default policy is Mon–Fri only.
        p = make_policy(lunch_start="", lunch_end="")
        ok, reason = ap.validate_slot(at("2026-05-09", "10:00"), at("2026-05-09", "10:30"), policy=p)
        self.assertFalse(ok)
        self.assertIn("saturday", reason.lower())
        self.assertIn("not open", reason.lower())

    def test_saturday_allowed_when_in_policy(self):
        p = make_policy(lunch_start="", lunch_end="", work_weekdays=[0, 1, 2, 3, 4, 5])
        ok, reason = ap.validate_slot(at("2026-05-09", "10:00"), at("2026-05-09", "10:30"), policy=p)
        self.assertTrue(ok, reason)

    def test_outside_working_hours_fails(self):
        p = make_policy()
        ok, reason = ap.validate_slot(at("2026-05-04", "08:30"), at("2026-05-04", "09:00"), policy=p)
        self.assertFalse(ok)
        self.assertIn("office hours", reason.lower())

    def test_slot_ending_exactly_at_work_end_passes(self):
        p = make_policy(lunch_start="", lunch_end="")
        ok, reason = ap.validate_slot(at("2026-05-04", "17:30"), at("2026-05-04", "18:00"), policy=p)
        self.assertTrue(ok, reason)

    def test_slot_overlapping_lunch_fails(self):
        p = make_policy()  # lunch 13-14
        ok, reason = ap.validate_slot(at("2026-05-04", "12:30"), at("2026-05-04", "13:30"), policy=p)
        self.assertFalse(ok)
        self.assertIn("lunch", reason.lower())

    def test_slot_touching_lunch_boundary_passes(self):
        p = make_policy()
        ok, _ = ap.validate_slot(at("2026-05-04", "12:30"), at("2026-05-04", "13:00"), policy=p)
        self.assertTrue(ok)
        ok, _ = ap.validate_slot(at("2026-05-04", "14:00"), at("2026-05-04", "14:30"), policy=p)
        self.assertTrue(ok)

    def test_zero_gap_allows_back_to_back(self):
        p = make_policy(gap_mins=0, lunch_start="", lunch_end="")
        busy = [(at("2026-05-04", "10:00"), at("2026-05-04", "10:30"))]
        ok, reason = ap.validate_slot(at("2026-05-04", "10:30"), at("2026-05-04", "11:00"), busy, p)
        self.assertTrue(ok, reason)

    def test_gap_blocks_close_prior_meeting(self):
        # User example: gap=10, slot at 16:00, prior event ending at 15:55 must fail.
        p = make_policy(gap_mins=10, lunch_start="", lunch_end="")
        busy = [(at("2026-05-04", "15:30"), at("2026-05-04", "15:55"))]
        ok, reason = ap.validate_slot(at("2026-05-04", "16:00"), at("2026-05-04", "16:30"), busy, p)
        self.assertFalse(ok)
        self.assertIn("between meetings", reason.lower())

    def test_gap_allows_event_ending_exactly_at_boundary(self):
        # Strict >: an event ending at 15:50 leaves the user's 16:00 slot legal with gap=10.
        p = make_policy(gap_mins=10, lunch_start="", lunch_end="")
        busy = [(at("2026-05-04", "15:30"), at("2026-05-04", "15:50"))]
        ok, reason = ap.validate_slot(at("2026-05-04", "16:00"), at("2026-05-04", "16:30"), busy, p)
        self.assertTrue(ok, reason)

    def test_gap_blocks_close_following_meeting(self):
        p = make_policy(gap_mins=15, lunch_start="", lunch_end="")
        busy = [(at("2026-05-04", "10:35"), at("2026-05-04", "11:00"))]
        ok, reason = ap.validate_slot(at("2026-05-04", "10:00"), at("2026-05-04", "10:30"), busy, p)
        self.assertFalse(ok)


class NextCompliantSlotTests(unittest.TestCase):
    def test_finds_first_clear_slot_skipping_lunch(self):
        p = make_policy(gap_mins=0)  # lunch 13-14 by default
        busy = []
        slot = ap.next_compliant_slot(at("2026-05-04", "12:30"), busy=busy, policy=p)
        self.assertIsNotNone(slot)
        # 12:30-13:00 is fine (touches lunch boundary), should be picked.
        self.assertEqual(slot["start_ist"], at("2026-05-04", "12:30"))

    def test_skips_holiday_to_next_day(self):
        p = make_policy(holidays=["2026-05-04"])
        slot = ap.next_compliant_slot(at("2026-05-04", "10:00"), busy=[], policy=p)
        self.assertIsNotNone(slot)
        self.assertGreaterEqual(slot["start_ist"].date(), date(2026, 5, 5))

    def test_respects_gap_with_existing_meeting(self):
        p = make_policy(gap_mins=15, lunch_start="", lunch_end="")
        busy = [(at("2026-05-04", "10:00"), at("2026-05-04", "10:30"))]
        slot = ap.next_compliant_slot(at("2026-05-04", "10:00"), busy=busy, policy=p)
        self.assertIsNotNone(slot)
        # Earliest legal start must be >= 10:30 + 15 min = 10:45.
        self.assertGreaterEqual(slot["start_ist"], at("2026-05-04", "10:45"))

    def test_returns_none_when_no_slot_in_horizon(self):
        # Tiny work window + a busy event covering the whole window => no slot.
        p = make_policy(
            work_start="09:00",
            work_end="09:30",
            lunch_start="",
            lunch_end="",
            work_weekdays=[0, 1, 2, 3, 4, 5, 6],
        )
        busy = [(at("2026-05-04", "09:00"), at("2026-05-04", "09:30"))]
        slot = ap.next_compliant_slot(at("2026-05-04", "09:00"), busy=busy, policy=p, search_days=1)
        self.assertIsNone(slot)

    def test_skips_weekend_when_mon_fri_only(self):
        p = make_policy(gap_mins=0, lunch_start="", lunch_end="")
        # 2026-05-09 Saturday 10:00 → next slot should be Monday 2026-05-11 or skip Sun
        slot = ap.next_compliant_slot(at("2026-05-09", "10:00"), busy=[], policy=p)
        self.assertIsNotNone(slot)
        self.assertLess(slot["start_ist"].weekday(), 5)


class SaveLoadTests(unittest.TestCase):
    def test_load_rewrites_legacy_file_missing_work_weekdays(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = os.path.join(tmp, "slot_config.json")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "work_start": "09:00",
                        "work_end": "18:00",
                        "lunch_start": "",
                        "lunch_end": "",
                        "gap_mins": 0,
                        "holidays": [],
                    },
                    f,
                )
            with mock.patch.object(ap, "SLOT_CONFIG_FILE", tmp_path), mock.patch.object(
                ap, "CONFIG_DIR", tmp
            ):
                ap._cache["mtime"] = None
                ap._cache["policy"] = None
                p = ap.load_policy()
                self.assertEqual(p.work_weekdays, frozenset(range(5)))
                with open(tmp_path, encoding="utf-8") as f:
                    data = json.load(f)
                self.assertIn("work_weekdays", data)
                self.assertEqual(data["work_weekdays"], [0, 1, 2, 3, 4])

    def test_save_then_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = os.path.join(tmp, "slot_config.json")
            with mock.patch.object(ap, "SLOT_CONFIG_FILE", tmp_path), mock.patch.object(
                ap, "CONFIG_DIR", tmp
            ):
                ap._cache["mtime"] = None
                ap._cache["policy"] = None
                ap.save_policy(
                    {
                        "work_start": "10:00",
                        "work_end": "17:00",
                        "lunch_start": "13:00",
                        "lunch_end": "14:00",
                        "gap_mins": 15,
                        "work_weekdays": [0, 1, 2, 3, 4],
                        "holidays": ["2026-05-04|Spring holiday"],
                    }
                )
                p = ap.load_policy()
                self.assertEqual(p.work_start, time(10, 0))
                self.assertEqual(p.gap_mins, 15)
                self.assertEqual(p.work_weekdays, frozenset(range(5)))
                self.assertIn(date(2026, 5, 4), p.holidays)
                self.assertEqual(p.holiday_label(date(2026, 5, 4)), "Spring holiday")

    def test_invalid_save_raises_and_does_not_clobber(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = os.path.join(tmp, "slot_config.json")
            with mock.patch.object(ap, "SLOT_CONFIG_FILE", tmp_path), mock.patch.object(
                ap, "CONFIG_DIR", tmp
            ):
                ap._cache["mtime"] = None
                ap._cache["policy"] = None
                ap.save_policy({"work_start": "09:00", "work_end": "18:00"})
                with self.assertRaises(ValueError):
                    ap.save_policy({"work_start": "18:00", "work_end": "09:00"})
                # File should still be the previous good copy.
                p = ap.load_policy()
                self.assertEqual(p.work_start, time(9, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
