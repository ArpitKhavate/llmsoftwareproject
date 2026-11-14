"""OWNER: Arpit (issue #4). Twilio SMS + Claude-written alerts and summary.

main.py already calls these functions. Keep the signatures; fill in the bodies.
Rules: keys come from .env only; never block or crash the video loop (use a thread).
"""


def send_alert(text: str) -> None:
    """Non-blocking. Optionally have Claude rewrite `text` for the owner, then SMS it via Twilio
    to ALERT_TO. Rate-limit to 1 SMS per 30 s. On any failure, print and continue."""
    print(f"(alert not sent yet, alerts.py is a stub) {text}")


def summarize_session(log_path: str = "events.log") -> None:
    """Called when the user presses 's' and on quit. Ask Claude for a short owner-friendly
    summary of the session from the log (traffic, peak, avg stay, staff coverage),
    print it, and optionally SMS it."""
    print("(summary not implemented yet, alerts.py is a stub)")
