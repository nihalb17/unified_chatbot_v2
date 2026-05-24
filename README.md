# Groww AI Support Suite

A dual-portal AI-powered platform for mutual fund investors and the operations team behind them. Investors get a conversational assistant to answer questions and book advisor calls. The internal team gets a live dashboard to manage the system's knowledge, review customer feedback themes, and control advisor availability.

---

## Live Links

| Portal | URL |
|---|---|
| User Portal | [unified-chatbot-v2.vercel.app](https://unified-chatbot-v2.vercel.app/) |
| Internal Dashboard | [groww-internal-dashboard.vercel.app](https://groww-internal-dashboard.vercel.app/) |

---

## Who This Is For

**Investors** use the User Portal on the Groww platform to get instant answers about their funds and book calls with human advisors without leaving the chat.

**Operations and product teams** use the Internal Dashboard to keep the assistant's knowledge up to date, monitor what investors are asking and complaining about, and control when advisors are available for bookings.

---

## User Portal: What Investors Can Do

### Chat with the AI Assistant
Investors open a chat window and ask anything about their mutual funds. The assistant answers with specific, sourced information pulled directly from fund factsheets and official definitions. Every answer includes the source so investors can verify what they read.

### Voice Mode
Investors can switch from typing to speaking at any point. The assistant listens, understands, and speaks the answer back. The full conversation also appears as text, so nothing is lost. Both modes share the same chat history.

### Ask About Any Fund
Common questions the assistant handles:
- NAV, returns, and performance of specific funds
- Expense ratios, exit loads, and fee structures
- How SIPs, ELSS, and other fund types work
- Any term from the mutual fund glossary

The assistant does not just pull a number and stop. When an investor asks about exit load on a specific fund, for example, the answer combines the actual exit load percentage from that fund's factsheet with a plain-language explanation of what exit load means, when it applies, and how the lock-in period or redemption timeline affects it. Factual data and concept definitions are blended into a single, coherent response so the investor gets the full picture without needing to ask a follow-up.

### Book an Advisor Call
If an investor wants to speak with a human, a booking panel appears directly inside the chat. No new page, no new form. The investor picks a date and time from available slots and confirms the booking.

The moment a booking is confirmed, the following happens automatically:

- The investor receives a booking code as confirmation inside the chat
- A calendar event is created for the scheduled time
- A blank meeting notes document is created and attached to that calendar event, ready for the advisor to fill in during the call
- The broker or advisor receives an email notification with the booking details so they are prepared ahead of time
- If the investor opts in, they also receive a confirmation email with the date, time, topic, and booking code

The assistant automatically carries the topic from the conversation into the booking request. If the investor was asking about exit loads, that context is passed to the advisor automatically so they arrive at the call already briefed on what the investor needs help with.

### Known Issue Responses
If an investor raises a complaint that the operations team has already flagged as a known issue, the assistant responds with a direct acknowledgment: what the issue is, that the team is aware, and what is being done. No runaround, no generic deflection.

---

## Internal Dashboard: What the Operations Team Can Do

### Review Pulse (Home Page)
The homepage shows a live view of what investors are saying across the Play Store and App Store. The system groups feedback into themes automatically. Each theme card shows:
- The theme name and a short description
- Whether the overall sentiment is positive, negative, or mixed
- How many reviews mention it
- Which app store the mentions came from

Clicking a theme opens a detail panel with representative quotes from real reviews and a suggested action the team can take (for example, "Add an FAQ entry" or "Investigate login issues on Android").

The team can trigger a fresh analysis at any time using the Refresh button. The dashboard shows live progress and updates automatically when the analysis is complete.

### Mutual Fund FAQs (Knowledge Base)
This section is where the team manages what the AI assistant knows.

**Factsheets**: The team maintains a list of factsheet URLs, one per fund. They can add new funds or remove old ones. Clicking Refresh re-indexes all the linked factsheets so the assistant starts using the latest data immediately. No deployment required.

**Definitions**: The team manages a glossary of mutual fund terms, each linked to an explanatory source URL. These feed into the assistant's ability to explain concepts accurately.

Both sections show when the knowledge base was last updated and give per-URL progress feedback during a refresh.

### Scheduled Appointments
A full log of every advisor call booked through the User Portal.

**List View**: Appointments grouped by date, each showing the time, topic, booking code, a link to meeting notes, and a link to the calendar event.

**Calendar View**: A full monthly calendar with appointments marked on each day. Clicking a day shows all bookings for that date.

The top of the page shows total bookings, upcoming bookings, and how many are scheduled for today. The team can search by booking code or topic, and filter to show only upcoming appointments.

### Meeting Slot Configuration
The team controls exactly when investors can book advisor calls.

**Work Week**: Select which days of the week advisors are available. Choose from Mon to Fri, Mon to Sat, all days, or pick individual days.

**Business Hours**: Set the start and end time for the working day.

**Lunch Break**: Block out a midday window when no bookings can be made.

**Gap Between Meetings**: Set a minimum gap (in minutes) between consecutive calls.

**Holidays**: Add specific dates that should be blocked from bookings, with an optional label (for example, "Diwali" or "Republic Day"). Holidays can be edited or deleted at any time.

All changes are saved with a single click and take effect immediately for any new booking attempts in the User Portal.

---

## How the Two Portals Are Connected

The User Portal and Internal Dashboard are two faces of the same system. Changes made in the dashboard directly shape what happens in the user's chat, and actions taken by investors appear in the dashboard in real time.

### Knowledge Base: Admin Edits, Investor Benefits
When the operations team adds a new factsheet URL or updates a glossary term in the dashboard and clicks Refresh, the AI assistant immediately starts using that information. If a new fund is added today, investors can ask about it today.

### Booking Rules: Admin Controls, Investor Sees
When the team changes business hours, marks a holiday, or adjusts the gap between meetings, those rules are enforced the next time any investor tries to book a call. The investor only ever sees valid, available slots. The team never has to coordinate this manually.

### Appointments: Investor Books, Admin Tracks
Every appointment booked through the User Portal chat appears in the Scheduled Appointments section of the dashboard. The operations team and advisors have a single, searchable log of all upcoming calls, complete with topics and booking codes.

### Review Themes: Investor Feedback, Admin Insight, Assistant Response
When investors leave app reviews, the system analyses them in the background and groups them into themes. The operations team reads these themes in Review Pulse. If a theme represents a known issue, the team can address it. That same theme data also feeds into the assistant so it can respond directly and empathetically when an investor raises a matching complaint, rather than routing them elsewhere.

---

## Summary

| Feature | User Portal | Internal Dashboard |
|---|---|---|
| Chat with AI assistant | Yes | No |
| Voice conversation mode | Yes | No |
| Ask about fund details | Yes | No |
| Book an advisor call | Yes | No |
| Receive booking confirmation by email | Yes | No |
| Known-issue instant responses | Yes | No |
| View investor feedback themes | No | Yes |
| Trigger fresh review analysis | No | Yes |
| Manage factsheet knowledge base | No | Yes |
| Manage glossary definitions | No | Yes |
| View full appointment log | No | Yes |
| Calendar view of all bookings | No | Yes |
| Configure advisor availability rules | No | Yes |
| Manage holidays and blackout dates | No | Yes |
