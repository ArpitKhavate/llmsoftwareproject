"""Employee vs customer: black apron on the torso, or feet inside the counter zone.

Optional AI check (Claude vision, runs in a background thread, cached per track ID).
To enable it in main.py: add `import employee as emp_ai` at the top, then in the detection loop
replace the `people.append(...)` line with these 2 lines:

    emp_ai.ai_verify(pid, frame, box); ai = emp_ai.ai_label(pid)
    people.append((pid, tuple(box), ai if ai is not None else sum(votes[pid]) > len(votes[pid]) / 2))

Only the torso crop is sent, never the face.
"""
import base64
import os
import threading

import cv2
import numpy as np

APRON_SHARE = 0.35   # share of torso pixels that must be "black"
BLACK_V_MAX = 60     # HSV brightness ceiling for black
BLACK_S_MAX = 120    # black fabric is low-saturation (rejects dark blue/red)
MIN_BOX_H = 40       # ignore tiny / far-away detections
AMBIGUOUS = (0.20, 0.50)


def _torso(frame, box):
    """Chest-to-waist band, central 60% of width, clamped to frame. Returns crop or None."""
    fh, fw = frame.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    x1, x2 = max(0, min(x1, fw)), max(0, min(x2, fw))
    y1, y2 = max(0, min(y1, fh)), max(0, min(y2, fh))
    h, w = y2 - y1, x2 - x1
    if h < MIN_BOX_H or w < 8:
        return None
    ty1, ty2 = y1 + int(h * 0.30), y1 + int(h * 0.65)
    tx1, tx2 = x1 + int(w * 0.20), x2 - int(w * 0.20)
    crop = frame[ty1:ty2, tx1:tx2]
    return crop if crop.size else None


def apron_share(frame, box):
    torso = _torso(frame, box)
    if torso is None:
        return 0.0
    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 0, 0), (180, BLACK_S_MAX, BLACK_V_MAX))
    return float(mask.mean() / 255)


def is_employee(frame, box, counter_zone=None):
    x1, y1, x2, y2 = [int(v) for v in box]
    if y2 - y1 < MIN_BOX_H:
        return False
    if counter_zone:
        cx, feet_y = (x1 + x2) / 2, y2
        zx1, zy1, zx2, zy2 = counter_zone
        if zx1 <= cx <= zx2 and zy1 <= feet_y <= zy2:
            return True
    return apron_share(frame, box) > APRON_SHARE


# ---------- optional Claude vision verification ----------
_ai_cache: dict = {}      # pid -> True / False / None (pending or failed)
_ai_lock = threading.Lock()
_client = None


def _ask_claude(pid, jpg_b64):
    global _client
    try:
        if _client is None:
            import anthropic
            _client = anthropic.Anthropic()
        r = _client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-haiku-5-5"),
            max_tokens=1024,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": jpg_b64}},
                {"type": "text", "text": "Is this person wearing a dark/black apron? Answer YES or NO."},
            ]}],
        )
        ans = next((c.text for c in r.content if c.type == "text"), "").strip().upper()
        if not ans:
            raise ValueError("no text answer")
        result = ans.startswith("YES")
        print(f"AI-verified #{pid}: {'EMPLOYEE' if result else 'CUSTOMER'}", flush=True)
    except Exception as e:  # never crash the video loop
        print(f"AI verify failed for #{pid}: {type(e).__name__}", flush=True)
        result = None
    with _ai_lock:
        _ai_cache[pid] = result


def ai_verify(pid, frame, box):
    """Fire one background Claude call per pid, only when the color check is ambiguous."""
    with _ai_lock:
        if pid in _ai_cache:
            return
    share = apron_share(frame, box)
    if not (AMBIGUOUS[0] <= share <= AMBIGUOUS[1]):
        return
    torso = _torso(frame, box)  # torso only: no face is ever sent
    if torso is None:
        return
    ok, buf = cv2.imencode(".jpg", torso)
    if not ok:
        return
    with _ai_lock:
        _ai_cache[pid] = None  # mark pending so we only ask once
    b64 = base64.b64encode(buf.tobytes()).decode()
    threading.Thread(target=_ask_claude, args=(pid, b64), daemon=True).start()


def ai_label(pid):
    """True/False once Claude has answered for this pid, else None."""
    with _ai_lock:
        return _ai_cache.get(pid)
