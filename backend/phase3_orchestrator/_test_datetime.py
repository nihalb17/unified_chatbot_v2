"""Quick IST date-parsing smoke test for collect_booking_datetime_node."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

from graph import run_orchestrator

BASE_SESSION = {
    "last_intent": "booking",
    "current_scheme": None,
    "current_concept": None,
    "in_flight_booking": {"topic": "Exit Load", "date": None, "time": None},
}

CASES = [
    "tomorrow at 3pm",
    "day after tomorrow at 10am",
    "coming Friday at noon",
    "coming Monday at 2:30pm",
    "coming Tuesday at 9am",
    "8th May at 4pm",
    "3rd May at 11am",
    "May 8 at 3:30 PM",
]

print(f"\n{'Input':<45}  {'Type':<20}  Response snippet")
print("-" * 100)

all_pass = True
for case in CASES:
    import copy
    sess = copy.deepcopy(BASE_SESSION)
    resp, updated = run_orchestrator(case, [], sess)
    rtype = resp.get("type", "?")
    text  = resp.get("text", "")[:60]

    # PASS if booking was confirmed (type=booking) OR still collecting with a date/time set
    booked = updated.get("in_flight_booking", {})
    booking_req = updated.get("booking_request") or {}
    ok = (
        rtype == "booking"                                  # fully confirmed
        or (rtype == "booking_collecting"                   # still collecting
            and (booked.get("date") or booked.get("time")))
    )
    if not ok:
        all_pass = False
    marker = "OK  " if ok else "FAIL"
    print(f"[{marker}] {case:<43}  {rtype:<20}  {text}")

print()
print("All cases resolved." if all_pass else "Some cases FAILED — check above.")
