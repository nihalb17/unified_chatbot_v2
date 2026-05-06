"""
Phase 4 — Google Workspace MCP Client

Unified client for Google Calendar, Docs, Gmail, and Drive APIs.
All datetime parameters are accepted as IST and converted to UTC
internally before calling Google APIs.

Auth uses OAuth2 refresh token from environment variables.
"""

import base64
import html
import logging
import random
import string
import os
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional, List, Dict, Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# IST / UTC helpers                                                    #
# ------------------------------------------------------------------ #

_IST_OFFSET = timedelta(hours=5, minutes=30)

def _ist_to_utc(dt_ist: datetime) -> datetime:
    """Convert a naive IST datetime to a timezone-aware UTC datetime."""
    from datetime import timezone
    ist_tz = timezone(_IST_OFFSET)
    utc_tz = timezone.utc
    if dt_ist.tzinfo is None:
        dt_ist = dt_ist.replace(tzinfo=ist_tz)
    return dt_ist.astimezone(utc_tz)


def _utc_to_ist(dt_utc: datetime) -> datetime:
    """Convert a UTC datetime to IST (naive, no tzinfo)."""
    from datetime import timezone
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    ist_tz = timezone(_IST_OFFSET)
    return dt_utc.astimezone(ist_tz).replace(tzinfo=None)


def _format_ampm_time(dt: datetime) -> str:
    """Format time as '10:30 AM' without a leading zero on the hour."""
    s = dt.strftime("%I:%M %p")
    if len(s) >= 2 and s[0] == "0" and s[1].isdigit():
        s = s[1:]
    return s


def _format_user_booking_labels(date_str: str, time_str: str) -> Dict[str, str]:
    """Pretty labels for user confirmation email (IST)."""
    from zoneinfo import ZoneInfo

    empty = {
        "date_pretty": date_str or "N/A",
        "time_pretty": time_str or "N/A",
        "slot_range": "N/A",
    }
    if not date_str or not time_str:
        return empty
    try:
        ist = ZoneInfo("Asia/Kolkata")
        start = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ist)
        end = start + timedelta(minutes=30)
        date_pretty = f"{start.day} {start.strftime('%B %Y')}"
        time_pretty = _format_ampm_time(start)
        slot_range = f"{_format_ampm_time(start)} - {_format_ampm_time(end)} IST"
        return {
            "date_pretty": date_pretty,
            "time_pretty": time_pretty,
            "slot_range": slot_range,
        }
    except Exception:
        return empty


class GoogleWorkspaceMCP:
    """Unified Google Workspace MCP client for Calendar, Docs, Gmail, and Drive."""

    def __init__(self):
        self.creds = None
        self.calendar_service = None
        self.docs_service = None
        self.gmail_service = None
        self.sheets_service = None
        self.drive_service = None
        self.calendar_id = None
        self._authenticate()

    def _authenticate(self) -> None:
        """Authenticate with Google using OAuth2 credentials from env vars."""
        client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "")
        calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "")

        if not all([client_id, client_secret, refresh_token]):
            logger.error("Google OAuth credentials not configured")
            raise ValueError("Google OAuth credentials not configured. Check .env file.")

        self.creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
        )

        self.calendar_service = build("calendar", "v3", credentials=self.creds)
        self.docs_service = build("docs", "v1", credentials=self.creds)
        self.gmail_service = build("gmail", "v1", credentials=self.creds)
        self.drive_service = build("drive", "v3", credentials=self.creds)

        self.calendar_id = calendar_id or "primary"
        logger.info("Google Workspace MCP authenticated successfully")

    # ==================== Booking Code ====================

    def generate_booking_code(self) -> str:
        """Generate a 4-digit booking code. Caller should check collisions."""
        return "".join(random.choices(string.digits, k=4))

    # ==================== Calendar Operations ====================

    def check_slot_availability(
        self,
        start_ist: datetime,
        end_ist: datetime,
    ) -> Dict[str, Any]:
        """Check if a time slot is available.

        Args:
            start_ist: Proposed start time (IST, naive).
            end_ist: Proposed end time (IST, naive).

        Returns:
            {"available": bool, "conflicting_events": [...]}
        """
        start_utc = _ist_to_utc(start_ist)
        end_utc = _ist_to_utc(end_ist)

        try:
            events_result = self.calendar_service.events().list(
                calendarId=self.calendar_id,
                timeMin=start_utc.isoformat(),
                timeMax=end_utc.isoformat(),
                maxResults=50,
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            events = events_result.get("items", [])
            conflicting = []

            for event in events:
                ev_start_str = event["start"].get("dateTime", event["start"].get("date"))
                ev_end_str = event["end"].get("dateTime", event["end"].get("date"))

                if "T" in ev_start_str:
                    ev_start = datetime.fromisoformat(ev_start_str.replace("Z", "+00:00"))
                    ev_end = datetime.fromisoformat(ev_end_str.replace("Z", "+00:00"))
                else:
                    continue  # skip all-day events

                if ev_start < end_utc and ev_end > start_utc:
                    conflicting.append({
                        "id": event["id"],
                        "summary": event.get("summary", ""),
                        "start_ist": _utc_to_ist(ev_start).isoformat(),
                        "end_ist": _utc_to_ist(ev_end).isoformat(),
                    })

            return {
                "available": len(conflicting) == 0,
                "conflicting_events": conflicting,
            }

        except HttpError as e:
            logger.error(f"Failed to check slot availability: {e}")
            raise

    def list_busy_intervals(
        self,
        start_ist: datetime,
        end_ist: datetime,
    ) -> list[tuple[datetime, datetime]]:
        """Return [(busy_start_ist, busy_end_ist), ...] in the given window.

        Used by the policy-aware ``next_compliant_slot`` so all rule checks
        live in one place. Skips all-day events (no time component).
        """
        start_utc = _ist_to_utc(start_ist)
        end_utc = _ist_to_utc(end_ist)

        try:
            events_result = self.calendar_service.events().list(
                calendarId=self.calendar_id,
                timeMin=start_utc.isoformat(),
                timeMax=end_utc.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=2500,
            ).execute()
        except HttpError as e:
            logger.error("Failed to list events for slot search: %s", e)
            raise

        intervals: list[tuple[datetime, datetime]] = []
        for event in events_result.get("items", []):
            ev_start_str = event["start"].get("dateTime")
            ev_end_str = event["end"].get("dateTime")
            if not ev_start_str or not ev_end_str:
                continue
            ev_start = datetime.fromisoformat(ev_start_str.replace("Z", "+00:00"))
            ev_end = datetime.fromisoformat(ev_end_str.replace("Z", "+00:00"))
            intervals.append((_utc_to_ist(ev_start), _utc_to_ist(ev_end)))
        return intervals

    def find_next_available_slot(
        self,
        after_ist: datetime,
        duration_mins: int = 30,
        search_days: int = 7,
        business_hours: bool = True,
        business_start_hour: int = 9,
        business_end_hour: int = 18,
        skip_weekends: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Find the next available `duration_mins` slot after the given IST time.

        Implementation notes:
        - Fetches all events in [after_ist, after_ist + search_days] in ONE
          calendar API call, then evaluates candidate slots locally. This is
          O(events) rather than O(slots), and avoids per-slot round-trips.
        - When `business_hours` is True, candidate slots must fully fit inside
          [business_start_hour, business_end_hour] IST and skip Sat/Sun.
          This keeps suggestions usable (no 3am Wednesday).
        - The scan is forward-only by design, matching the spec in
          docs/Information/summary_architecture_book_appointment.md.

        Returns: {"start_ist": datetime, "end_ist": datetime} or None
        """
        from datetime import timezone, time as dtime

        # Window: from `after_ist` to `after_ist + search_days` (IST naive).
        window_start_ist = after_ist
        window_end_ist = after_ist + timedelta(days=search_days)

        window_start_utc = _ist_to_utc(window_start_ist)
        window_end_utc = _ist_to_utc(window_end_ist)

        try:
            events_result = self.calendar_service.events().list(
                calendarId=self.calendar_id,
                timeMin=window_start_utc.isoformat(),
                timeMax=window_end_utc.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=2500,
            ).execute()
        except HttpError as e:
            logger.error(f"Failed to list events for slot search: {e}")
            return None

        # Build a list of (start_ist_naive, end_ist_naive) intervals for
        # busy events. Skip all-day events (no time component).
        busy: list[tuple[datetime, datetime]] = []
        for event in events_result.get("items", []):
            ev_start_str = event["start"].get("dateTime")
            ev_end_str = event["end"].get("dateTime")
            if not ev_start_str or not ev_end_str:
                continue
            ev_start = datetime.fromisoformat(ev_start_str.replace("Z", "+00:00"))
            ev_end = datetime.fromisoformat(ev_end_str.replace("Z", "+00:00"))
            busy.append((_utc_to_ist(ev_start), _utc_to_ist(ev_end)))

        def _conflicts(slot_start: datetime, slot_end: datetime) -> bool:
            """True if [slot_start, slot_end) overlaps any busy interval."""
            for ev_s, ev_e in busy:
                if ev_s < slot_end and ev_e > slot_start:
                    return True
            return False

        def _round_up_to_30_min(dt: datetime) -> datetime:
            """Round up to the next :00 or :30 boundary so candidates align."""
            minute = (dt.minute + 29) // 30 * 30
            base = dt.replace(second=0, microsecond=0, minute=0)
            return base + timedelta(minutes=minute) if minute < 60 else base + timedelta(hours=1)

        candidate = _round_up_to_30_min(window_start_ist)

        # Cap inner loop so we never spin forever on misconfigured input.
        # Even at 30-min resolution across 7 days, that's <= 336 iterations.
        max_iterations = (search_days + 1) * 24 * 2
        for _ in range(max_iterations):
            if candidate >= window_end_ist:
                return None

            if business_hours:
                if skip_weekends and candidate.weekday() >= 5:
                    # Jump to the next Monday at business_start_hour.
                    days_to_monday = 7 - candidate.weekday()
                    candidate = (candidate + timedelta(days=days_to_monday)).replace(
                        hour=business_start_hour, minute=0, second=0, microsecond=0
                    )
                    continue
                # Outside business hours: snap to the day's business window.
                if candidate.hour < business_start_hour:
                    candidate = candidate.replace(
                        hour=business_start_hour, minute=0, second=0, microsecond=0
                    )
                # Slot must end by business_end_hour, so start by end_hour - duration.
                latest_start = candidate.replace(
                    hour=business_end_hour, minute=0, second=0, microsecond=0
                ) - timedelta(minutes=duration_mins)
                if candidate > latest_start:
                    next_day = candidate + timedelta(days=1)
                    candidate = next_day.replace(
                        hour=business_start_hour, minute=0, second=0, microsecond=0
                    )
                    continue

            slot_end = candidate + timedelta(minutes=duration_mins)
            if not _conflicts(candidate, slot_end):
                return {"start_ist": candidate, "end_ist": slot_end}

            candidate += timedelta(minutes=30)

        return None

    def create_calendar_event(
        self,
        topic: str,
        start_ist: datetime,
        end_ist: datetime,
        booking_code: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a calendar event.

        Args:
            topic: Appointment topic.
            start_ist: Start time (IST, naive).
            end_ist: End time (IST, naive).
            booking_code: 4-digit booking code.
            description: Optional event description.

        Returns:
            {"event_id", "event_link", "summary", "start_ist", "end_ist"}
        """
        start_utc = _ist_to_utc(start_ist)
        end_utc = _ist_to_utc(end_ist)

        summary = f"[#{booking_code}] {topic}"

        event_body = {
            "summary": summary,
            "description": description or f"Appointment for {topic}. Booking Code: #{booking_code}",
            "start": {
                "dateTime": start_utc.isoformat(),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": end_utc.isoformat(),
                "timeZone": "UTC",
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 60},
                    {"method": "popup", "minutes": 15},
                ],
            },
        }

        try:
            event = self.calendar_service.events().insert(
                calendarId=self.calendar_id,
                body=event_body,
            ).execute()

            logger.info(f"Created calendar event: {event['id']} for booking #{booking_code}")

            return {
                "event_id": event["id"],
                "event_link": event.get("htmlLink"),
                "summary": summary,
                "start_ist": start_ist.isoformat(),
                "end_ist": end_ist.isoformat(),
            }
        except HttpError as e:
            logger.error(f"Failed to create calendar event: {e}")
            raise

    def update_calendar_event_with_doc(
        self,
        event_id: str,
        doc_link: str,
    ) -> bool:
        """Update a calendar event to attach a Google Doc link.

        Returns True if successful, False otherwise.
        """
        try:
            event = self.calendar_service.events().get(
                calendarId=self.calendar_id,
                eventId=event_id,
            ).execute()

            current_desc = event.get("description", "")
            event["description"] = f"{current_desc}\n\nMeeting Notes: {doc_link}"

            self.calendar_service.events().update(
                calendarId=self.calendar_id,
                eventId=event_id,
                body=event,
            ).execute()

            logger.info(f"Updated calendar event {event_id} with doc link")
            return True
        except HttpError as e:
            logger.error(f"Failed to update calendar event with doc: {e}")
            return False

    def find_event_by_booking_code(self, booking_code: str) -> Optional[Dict[str, Any]]:
        """Find a calendar event by its booking code.

        Returns event details dict or None.
        """
        from datetime import timezone
        now_utc = datetime.now(timezone.utc)
        time_min = now_utc - timedelta(days=90)
        time_max = now_utc + timedelta(days=90)

        try:
            events_result = self.calendar_service.events().list(
                calendarId=self.calendar_id,
                q=booking_code,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                maxResults=10,
                singleEvents=True,
            ).execute()

            for event in events_result.get("items", []):
                summary = event.get("summary", "")
                description = event.get("description", "")
                if booking_code in summary or (description and booking_code in description):
                    start_str = event["start"].get("dateTime", event["start"].get("date"))
                    end_str = event["end"].get("dateTime", event["end"].get("date"))

                    if "T" in start_str:
                        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                        end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                        start_ist = _utc_to_ist(start_dt)
                        end_ist = _utc_to_ist(end_dt)
                    else:
                        start_ist = datetime.fromisoformat(start_str)
                        end_ist = datetime.fromisoformat(end_str)

                    return {
                        "event_id": event["id"],
                        "event_link": event.get("htmlLink"),
                        "summary": summary,
                        "start_ist": start_ist.isoformat(),
                        "end_ist": end_ist.isoformat(),
                    }

            return None
        except HttpError as e:
            logger.error(f"Failed to find event by booking code: {e}")
            return None

    # ==================== Google Docs Operations ====================

    def create_meeting_notes_doc(
        self,
        topic: str,
        booking_code: str,
        meeting_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a Google Doc for meeting notes.

        Returns:
            {"doc_id", "doc_link", "title"}
        """
        title = f"Meeting Notes - #{booking_code} - {topic}"
        folder_id = os.getenv("GOOGLE_DOCS_FOLDER_ID", "")

        try:
            # Create the document
            doc = self.docs_service.documents().create(
                body={"title": title},
            ).execute()
            doc_id = doc["documentId"]
            doc_link = f"https://docs.google.com/document/d/{doc_id}/edit"

            # Insert template content
            content = f"Meeting Notes\n\n"
            content += f"Topic: {topic}\n"
            content += f"Booking Code: #{booking_code}\n"
            if meeting_time:
                content += f"Scheduled Time: {meeting_time}\n"
            content += "\n---\n\n"
            content += "Agenda:\n\n"
            content += "Notes:\n\n"
            content += "Action Items:\n\n"

            self.docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={
                    "requests": [
                        {
                            "insertText": {
                                "location": {"index": 1},
                                "text": content,
                            }
                        }
                    ]
                },
            ).execute()

            # Move to configured folder if set
            if folder_id:
                try:
                    self.drive_service.files().update(
                        fileId=doc_id,
                        addParents=folder_id,
                        fields="id, parents",
                    ).execute()
                except HttpError as e:
                    logger.warning(f"Could not move doc to folder: {e}")

            logger.info(f"Created Google Doc: {doc_id} for booking #{booking_code}")
            return {
                "doc_id": doc_id,
                "doc_link": doc_link,
                "title": title,
            }

        except HttpError as e:
            logger.error(f"Failed to create Google Doc: {e}")
            raise

    # ==================== Gmail Operations ====================

    def send_booking_email(
        self,
        topic: str,
        booking_code: str,
        meeting_time: str,
        doc_link: Optional[str] = None,
        event_link: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a booking notification email to the broker.

        Returns:
            {"message_id", "recipient"}
        """
        recipient = os.getenv("MF_DISTRIBUTOR_EMAIL", "")
        if not recipient:
            logger.error("MF_DISTRIBUTOR_EMAIL not configured")
            raise ValueError("MF_DISTRIBUTOR_EMAIL not configured")

        subject = f"[#{booking_code}] New Appointment: {topic}"

        body_text = f"New appointment booked.\n\n"
        body_text += f"Booking Code: #{booking_code}\n"
        body_text += f"Topic: {topic}\n"
        body_text += f"Scheduled Time: {meeting_time}\n"
        if doc_link:
            body_text += f"Meeting Notes: {doc_link}\n"
        if event_link:
            body_text += f"Calendar Event: {event_link}\n"

        body_html = f"""<html><body>
<h3>New Appointment Booked</h3>
<p><strong>Booking Code:</strong> #{booking_code}</p>
<p><strong>Topic:</strong> {topic}</p>
<p><strong>Scheduled Time:</strong> {meeting_time}</p>
"""
        if doc_link:
            body_html += f'<p><strong>Meeting Notes:</strong> <a href="{doc_link}">Open Doc</a></p>'
        if event_link:
            body_html += f'<p><strong>Calendar Event:</strong> <a href="{event_link}">Open Event</a></p>'
        body_html += "</body></html>"

        message = MIMEMultipart("alternative")
        message["to"] = recipient
        message["subject"] = subject
        message.attach(MIMEText(body_text, "plain"))
        message.attach(MIMEText(body_html, "html"))

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        try:
            sent = self.gmail_service.users().messages().send(
                userId="me",
                body={"raw": raw},
            ).execute()

            logger.info(f"Sent booking email to {recipient}, message_id: {sent['id']}")
            return {
                "message_id": sent["id"],
                "recipient": recipient,
            }
        except HttpError as e:
            logger.error(f"Failed to send booking email: {e}")
            raise

    def send_user_booking_email(
        self,
        recipient: str,
        topic: str,
        booking_code: str,
        date_str: str,
        time_str: str,
    ) -> Dict[str, Any]:
        """Send booking confirmation email to the user (user-initiated, optional).

        Intentionally does not include calendar or meeting-notes links (distributor
        notification remains separate in send_booking_email).

        Args:
            recipient: User's email address.
            topic: Appointment topic.
            booking_code: 4-digit booking code.
            date_str: Booking date (YYYY-MM-DD).
            time_str: Booking time (HH:MM, IST).

        Returns:
            {"message_id", "recipient"}
        """
        labels = _format_user_booking_labels(date_str, time_str)
        date_pretty = labels["date_pretty"]
        time_pretty = labels["time_pretty"]
        slot_range = labels["slot_range"]
        office = os.getenv("BOOKING_OFFICE_LOCATION", "Groww HQ, Bengaluru")
        year = datetime.now().year

        subject = f"Your Groww appointment is confirmed - {date_pretty}, {time_pretty}"

        safe_topic = html.escape(topic or "")
        safe_code = html.escape(booking_code or "")
        safe_office = html.escape(office)

        body_text = (
            "Groww Investor Appointments\n"
            "Booking confirmed\n\n"
            "Your appointment is locked in.\n"
            "We are excited to host you at the Groww office. "
            "Keep your booking code handy when you arrive.\n\n"
            f"Booking code: {booking_code}\n"
            "Share this code at the Groww office reception to start your appointment.\n\n"
            f"Topic: {topic}\n"
            f"Date: {date_pretty}\n"
            f"Time: {time_pretty}\n"
            f"Time slot: {slot_range}\n"
            f"Location: {office}\n\n"
            "You are receiving this email because you booked an investor appointment.\n"
            f"© {year} Groww. All rights reserved.\n"
        )

        body_html = f"""<html>
<body style="margin:0;padding:0;background-color:#f4f4f5;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f4f4f5;padding:24px 12px;">
  <tr>
    <td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e4e4e7;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
        <tr>
          <td style="padding:28px 28px 8px 28px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
            <p style="margin:0 0 4px 0;font-size:12px;letter-spacing:0.02em;text-transform:uppercase;color:#71717a;font-weight:600;">Groww Investor · Appointments</p>
            <h1 style="margin:0 0 8px 0;font-size:22px;line-height:1.25;color:#18181b;font-weight:700;">Booking confirmed</h1>
            <p style="margin:0 0 6px 0;font-size:15px;line-height:1.5;color:#3f3f46;">Your appointment is locked in.</p>
            <p style="margin:0;font-size:15px;line-height:1.5;color:#52525b;">We are excited to host you at the Groww office. Keep your booking code handy when you arrive.</p>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 28px 24px 28px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
            <div style="background:linear-gradient(135deg,#ecfdf5 0%,#d1fae5 100%);border:1px solid #a7f3d0;border-radius:10px;padding:20px;text-align:center;">
              <p style="margin:0 0 6px 0;font-size:11px;letter-spacing:0.06em;text-transform:uppercase;color:#047857;font-weight:600;">Booking code</p>
              <p style="margin:0;font-size:32px;line-height:1.1;font-weight:800;letter-spacing:0.08em;color:#065f46;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;">{safe_code}</p>
            </div>
            <p style="margin:16px 0 0 0;font-size:14px;line-height:1.5;color:#52525b;text-align:center;">Share this code at the <strong>Groww office reception</strong> to start your appointment.</p>
          </td>
        </tr>
        <tr>
          <td style="padding:0 28px 28px 28px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-size:14px;color:#18181b;">
              <tr><td colspan="2" style="padding:0 0 12px 0;border-bottom:1px solid #e4e4e7;font-weight:600;color:#71717a;font-size:12px;text-transform:uppercase;letter-spacing:0.04em;">Appointment details</td></tr>
              <tr><td style="padding:12px 8px 8px 0;color:#71717a;width:36%;vertical-align:top;">Topic</td><td style="padding:12px 0 8px 0;vertical-align:top;font-weight:500;">{safe_topic}</td></tr>
              <tr><td style="padding:8px 8px 8px 0;color:#71717a;vertical-align:top;">Date</td><td style="padding:8px 0;vertical-align:top;font-weight:500;">{html.escape(date_pretty)}</td></tr>
              <tr><td style="padding:8px 8px 8px 0;color:#71717a;vertical-align:top;">Time</td><td style="padding:8px 0;vertical-align:top;font-weight:500;">{html.escape(time_pretty)}</td></tr>
              <tr><td style="padding:8px 8px 8px 0;color:#71717a;vertical-align:top;">Time slot</td><td style="padding:8px 0;vertical-align:top;font-weight:500;">{html.escape(slot_range)}</td></tr>
              <tr><td style="padding:8px 8px 0 0;color:#71717a;vertical-align:top;">Location</td><td style="padding:8px 0 0 0;vertical-align:top;font-weight:500;">{safe_office}</td></tr>
            </table>
            <p style="margin:24px 0 0 0;font-size:12px;line-height:1.5;color:#a1a1aa;text-align:center;">You are receiving this email because you booked an investor appointment.</p>
            <p style="margin:8px 0 0 0;font-size:12px;line-height:1.5;color:#a1a1aa;text-align:center;">© {year} Groww. All rights reserved.</p>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>"""

        message = MIMEMultipart("alternative")
        message["to"] = recipient
        message["subject"] = subject
        message.attach(MIMEText(body_text, "plain"))
        message.attach(MIMEText(body_html, "html"))

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        try:
            sent = self.gmail_service.users().messages().send(
                userId="me",
                body={"raw": raw},
            ).execute()

            logger.info(f"Sent user booking email to {recipient}, message_id: {sent['id']}")
            return {
                "message_id": sent["id"],
                "recipient": recipient,
            }
        except HttpError as e:
            logger.error(f"Failed to send user booking email: {e}")
            raise


# ==================== Singleton ==================== #

_workspace_mcp: Optional[GoogleWorkspaceMCP] = None


def get_workspace_mcp() -> GoogleWorkspaceMCP:
    """Get or create the GoogleWorkspaceMCP singleton."""
    global _workspace_mcp
    if _workspace_mcp is None:
        _workspace_mcp = GoogleWorkspaceMCP()
    return _workspace_mcp
