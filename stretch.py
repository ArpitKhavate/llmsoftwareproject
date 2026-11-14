"""OWNER: Lokesh (issue #3). Dwell time + counter-wait alert.

main.py already calls these functions. Keep the signatures; fill in the bodies.

Dwell time:   on_came_in stamps the time, on_left returns ' (stayed 3m12s)', HUD shows the average.
Counter wait: a customer whose feet stay in the counter-front zone for COUNTER_WAIT_SECONDS while
              no employee is behind the counter triggers one alert per wait. main.py logs the
              returned text and passes it to alerts.send_alert (that is the on_alert hook).
"""
import os
import time

COUNTER_WAIT_SECONDS = float(os.getenv("COUNTER_WAIT_SECONDS", "120"))  # set 20 for the demo
GRACE_SECONDS = 2.0  # tracker can drop a person for a few frames; don't reset their wait for that

_came_in_at = {}   # pid -> time they crossed inward
_stays = []        # finished stays, seconds
_waits = {}        # pid -> {"start": t, "last_seen": t, "alerted": bool}


def _fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _feet_in(box, zone) -> bool:
    if not zone:
        return False
    x1, _, x2, y2 = box
    cx = (x1 + x2) / 2
    zx1, zy1, zx2, zy2 = zone
    return zx1 <= cx <= zx2 and zy1 <= y2 <= zy2


def on_came_in(pid: int) -> None:
    """A customer crossed the door line inward."""
    _came_in_at[pid] = time.time()


def on_left(pid: int) -> str:
    """A customer crossed outward. Return a suffix for the log line, e.g. ' (stayed 3m12s)', or ''."""
    start = _came_in_at.pop(pid, None)
    _waits.pop(pid, None)
    if start is None:  # was already inside when we started, or the tracker changed their ID
        return ""
    stay = time.time() - start
    _stays.append(stay)
    return f" (stayed {_fmt(stay)})"


def on_frame(people: list, counter_front_zone, counter_zone) -> list[str]:
    """Called every frame.

    people: list of (pid, (x1, y1, x2, y2), is_employee) in pixels.
    counter_front_zone / counter_zone: (x1, y1, x2, y2) in pixels, or None.
    Return a list of alert texts to fire this frame, e.g.
    ["customer waiting at counter 2 min, no employee present"]. Fire each alert once per wait.
    """
    if not counter_front_zone:
        return []
    now = time.time()

    # Staff present = an employee behind the counter (or anywhere, if no counter zone is set).
    employees = [box for _, box, emp in people if emp]
    staffed = any(_feet_in(b, counter_zone) for b in employees) if counter_zone else bool(employees)

    for pid, box, emp in people:
        if emp or not _feet_in(box, counter_front_zone):
            continue
        w = _waits.setdefault(pid, {"start": now, "last_seen": now, "alerted": False})
        w["last_seen"] = now
        if staffed and not w["alerted"]:
            w["start"] = now  # someone is serving them; the unattended clock restarts

    alerts = []
    for pid, w in list(_waits.items()):
        if now - w["last_seen"] > GRACE_SECONDS:  # walked away from the counter
            del _waits[pid]
            continue
        waited = now - w["start"]
        if not w["alerted"] and not staffed and waited >= COUNTER_WAIT_SECONDS:
            w["alerted"] = True
            alerts.append(f"customer #{pid} waiting at counter {_fmt(waited)}, no employee present")
    return alerts


def hud_lines() -> list[str]:
    """Extra lines to draw on the video HUD, e.g. ['Avg stay: 4m05s']."""
    lines = []
    if _stays:
        lines.append(f"Avg stay: {_fmt(sum(_stays) / len(_stays))} ({len(_stays)})")
    if _waits:
        now = time.time()
        pid, w = max(_waits.items(), key=lambda kv: now - kv[1]["start"])
        lines.append(f"Counter wait: #{pid} {_fmt(now - w['start'])}")
    return lines
