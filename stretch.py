"""OWNER: Lokesh (issue #3). Dwell time + counter-wait alert.

main.py already calls these functions. Keep the signatures; fill in the bodies.
"""
import os
import time

COUNTER_WAIT_SECONDS = float(os.getenv("COUNTER_WAIT_SECONDS", "120"))  # set 20 for the demo


def on_came_in(pid: int) -> None:
    """A customer crossed the door line inward."""


def on_left(pid: int) -> str:
    """A customer crossed outward. Return a suffix for the log line, e.g. ' (stayed 3m12s)', or ''."""
    return ""


def on_frame(people: list, counter_front_zone, counter_zone) -> list[str]:
    """Called every frame.

    people: list of (pid, (x1, y1, x2, y2), is_employee) in pixels.
    counter_front_zone / counter_zone: (x1, y1, x2, y2) in pixels, or None.
    Return a list of alert texts to fire this frame, e.g.
    ["customer waiting at counter 2 min, no employee present"]. Fire each alert once per wait.
    """
    return []


def hud_lines() -> list[str]:
    """Extra lines to draw on the video HUD, e.g. ['Avg stay: 4m05s']."""
    return []
