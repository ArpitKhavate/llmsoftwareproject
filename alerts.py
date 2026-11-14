"""OWNER: Arpit (issue #4). Twilio SMS + Claude-written alerts and summary.

main.py already calls these functions. Keep the signatures; fill in the bodies.
Rules: keys come from .env only; never block or crash the video loop (use a thread).
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

# Rate-limit SMS so the owner isn't flooded during a busy stretch.
_SMS_COOLDOWN_S = 30.0
_last_sms_at = 0.0
_sms_lock = threading.Lock()


def _env(*names: str) -> str | None:
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return None


def _claude_model() -> str:
    # AGENTS.md asks for claude-haiku-5-5; allow override if the account needs another id.
    return _env("CLAUDE_MODEL") or "claude-haiku-4-5-20251001"


def _twilio_ready() -> bool:
    return all(
        [
            _env("TWILIO_ACCOUNT_SID"),
            _env("TWILIO_AUTH_TOKEN"),
            _env("TWILIO_FROM"),
            _env("ALERT_TO"),
        ]
    )


def _claude_rewrite(text: str) -> str:
    """Turn a raw alert into a short SMS for the restaurant owner. Falls back to text."""
    api_key = _env("ANTHROPIC_API_KEY")
    if not api_key:
        return text
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=_claude_model(),
            max_tokens=120,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Rewrite this restaurant-floor alert as one short SMS for the owner "
                        "(under 160 characters, plain text, no quotes, no emoji):\n"
                        f"{text}"
                    ),
                }
            ],
        )
        parts = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
        rewritten = " ".join(parts).strip()
        return rewritten or text
    except Exception as exc:  # never crash the video loop
        print(f"(claude rewrite skipped: {exc})", flush=True)
        return text


def _send_sms(body: str) -> None:
    """Send one SMS via Twilio. Silent no-op if credentials are missing."""
    global _last_sms_at

    if not _twilio_ready():
        print(f"(SMS skipped — set TWILIO_* and ALERT_TO in .env) {body}", flush=True)
        return

    with _sms_lock:
        now = time.monotonic()
        if now - _last_sms_at < _SMS_COOLDOWN_S:
            print(f"(SMS rate-limited, skipped) {body}", flush=True)
            return
        _last_sms_at = now

    try:
        from twilio.rest import Client

        client = Client(_env("TWILIO_ACCOUNT_SID"), _env("TWILIO_AUTH_TOKEN"))
        client.messages.create(
            body=body[:320],
            from_=_env("TWILIO_FROM"),
            to=_env("ALERT_TO"),
        )
        print(f"(SMS sent) {body}", flush=True)
    except Exception as exc:
        print(f"(SMS failed: {exc})", flush=True)


def _alert_worker(text: str) -> None:
    try:
        message = _claude_rewrite(text)
        _send_sms(message)
    except Exception as exc:
        print(f"(alert worker failed: {exc})", flush=True)


def send_alert(text: str) -> None:
    """Non-blocking. Optionally have Claude rewrite `text` for the owner, then SMS it via Twilio
    to ALERT_TO. Rate-limit to 1 SMS per 30 s. On any failure, print and continue."""
    print(f"ALERT -> owner: {text}", flush=True)
    threading.Thread(target=_alert_worker, args=(text,), daemon=True).start()


def _claude_summary(log_text: str) -> str:
    api_key = _env("ANTHROPIC_API_KEY")
    fallback = (
        "Session summary unavailable (no ANTHROPIC_API_KEY or Claude error). "
        "Check events.log for raw traffic."
    )
    if not api_key:
        return fallback
    if not log_text.strip():
        return "No events logged this session yet."

    # Keep the prompt small and fast for the demo.
    clipped = log_text[-8000:]
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=_claude_model(),
            max_tokens=400,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "You are writing a 4–6 sentence end-of-session briefing for a restaurant "
                        "owner from this Surveillance.ai event log. Cover: customer traffic "
                        "(came in / left / in store), peak moments, average stay if mentioned, "
                        "staff coverage, and any alerts. Be concrete and use only numbers from "
                        "the log. Plain text, no markdown.\n\n"
                        f"LOG:\n{clipped}"
                    ),
                }
            ],
        )
        parts = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
        return " ".join(parts).strip() or fallback
    except Exception as exc:
        print(f"(claude summary failed: {exc})", flush=True)
        return fallback


def summarize_session(log_path: str = "events.log") -> None:
    """Called when the user presses 's' and on quit. Ask Claude for a short owner-friendly
    summary of the session from the log (traffic, peak, avg stay, staff coverage),
    print it, and optionally SMS it.

    Runs in a background thread so the video loop stays responsive on 's', but we join
    briefly so a quit-path summary still has time to finish before the process exits.
    """
    print(f"(summarizing {log_path}…)", flush=True)

    def _worker() -> None:
        try:
            path = Path(log_path)
            log_text = path.read_text(encoding="utf-8") if path.exists() else ""
            summary = _claude_summary(log_text)
            print("\n===== SESSION SUMMARY =====", flush=True)
            print(summary, flush=True)
            print("===========================\n", flush=True)
            if _twilio_ready() and summary and "unavailable" not in summary.lower():
                _send_sms(f"Surveillance.ai summary: {summary[:280]}")
        except Exception as exc:
            print(f"(summary worker failed: {exc})", flush=True)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    # Allow Claude/Twilio to finish when called on quit; 's' during the loop also gets a brief wait.
    thread.join(timeout=20.0)
