"""OWNER: Lokesh (issue #3). Dwell time + counter-wait alert.

main.py already calls these functions. Keep the signatures.
"""
import os
import time


def _wait_seconds():
    raw = (os.getenv("COUNTER_WAIT_SECONDS") or "").split("#")[0].strip()
    try:
        v = float(raw)
        return v if v > 0 else 120.0
    except ValueError:
        return 120.0


COUNTER_WAIT_SECONDS = _wait_seconds()  # set 20 in .env for the demo
FORGET_AFTER = 5.0  # seconds unseen before a pid is dropped from wait tracking

_entered = {}       # pid -> time came in
_stays = []         # completed stay durations (s)
_wait_start = {}    # pid -> time feet entered counter-front zone
_alerted = set()    # pids already alerted for the current wait
_last_seen = {}     # pid -> last time seen in a frame
_waiting_now = 0


def _fmt(secs):
    secs = int(round(secs))
    m, s = divmod(secs, 60)
    return f"{m}m{s:02d}s"


def _fmt_wait(secs):
    if secs < 60:
        return f"{int(round(secs))} s"
    mins = secs / 60
    return f"{int(mins)} min" if mins == int(mins) else f"{mins:.1f} min"


def _feet_in(box, zone):
    if not zone:
        return False
    x1, y1, x2, y2 = box
    fx, fy = (x1 + x2) / 2, y2
    zx1, zy1, zx2, zy2 = zone
    return zx1 <= fx <= zx2 and zy1 <= fy <= zy2


def on_came_in(pid: int) -> None:
    """A customer crossed the door line inward."""
    _entered[pid] = time.time()


def on_left(pid: int) -> str:
    """A customer crossed outward. Return a log suffix like ' (stayed 3m12s)', or ''."""
    t0 = _entered.pop(pid, None)
    if t0 is None:
        return ""
    stay = time.time() - t0
    _stays.append(stay)
    return f" (stayed {_fmt(stay)})"


def on_frame(people: list, counter_front_zone, counter_zone) -> list[str]:
    """Return alert texts to fire this frame (each wait alerts once)."""
    global _waiting_now
    now = time.time()
    alerts = []

    for pid, _, _ in people:
        _last_seen[pid] = now
    for pid in [p for p, t in _last_seen.items() if now - t > FORGET_AFTER]:
        _last_seen.pop(pid, None)
        _wait_start.pop(pid, None)
        _alerted.discard(pid)

    if not counter_front_zone:
        _wait_start.clear()
        _alerted.clear()
        _waiting_now = 0
        return alerts

    employee_at_counter = any(emp and _feet_in(box, counter_zone) for _, box, emp in people)
    waiting = {pid for pid, box, emp in people if not emp and _feet_in(box, counter_front_zone)}
    _waiting_now = len(waiting)

    # reset anyone who left the zone
    seen_now = {pid for pid, _, _ in people}
    for pid in list(_wait_start):
        if pid in seen_now and pid not in waiting:
            _wait_start.pop(pid, None)
            _alerted.discard(pid)

    for pid in waiting:
        if employee_at_counter:
            _wait_start[pid] = now   # an employee is serving: restart the clock
            _alerted.discard(pid)
            continue
        start = _wait_start.setdefault(pid, now)
        if pid not in _alerted and now - start >= COUNTER_WAIT_SECONDS:
            _alerted.add(pid)
            alerts.append(f"customer waiting at counter {_fmt_wait(COUNTER_WAIT_SECONDS)}, no employee present")
    return alerts


def hud_lines() -> list[str]:
    """Extra lines for the video HUD."""
    lines = []
    if _stays:
        lines.append(f"Avg stay: {_fmt(sum(_stays) / len(_stays))}")
    if _waiting_now:
        lines.append(f"Waiting at counter: {_waiting_now}")
    return lines
