"""Surveillance.ai: live customer in/out counter (LLMSoftware x UTD Challenge 1).

OWNER: Jamshed (issue #1). Other modules plug in through fixed functions:
  employee.py (Nandhan), stretch.py (Lokesh), alerts.py (Arpit).

Run:  python main.py      Keys: q = quit, s = AI session summary
"""
import os
import time
from collections import defaultdict, deque

import cv2
from dotenv import load_dotenv
from ultralytics import YOLO

load_dotenv()

import alerts  # noqa: E402  (after load_dotenv so modules can read env at import)
import stretch  # noqa: E402
from employee import is_employee  # noqa: E402

# CAMERA can be a webcam index ("0", "1") or a path/URL ("nest_backup.mp4")
_src = os.getenv("CAMERA", "1")
SOURCE = int(_src) if _src.isdigit() else _src

DOOR_Y_FRAC = float(os.getenv("DOOR_Y_FRAC", "0.5"))          # door line height, fraction of frame
INSIDE_IS_BELOW = os.getenv("INSIDE_IS_BELOW", "1") == "1"     # flip if the door faces the other way


def _zone(name):
    v = (os.getenv(name) or "").split("#")[0].strip()
    try:
        z = tuple(float(x) for x in v.split(","))
        return z if len(z) == 4 else None
    except ValueError:
        return None


COUNTER_ZONE = _zone("COUNTER_ZONE")              # behind the counter -> employee
COUNTER_FRONT_ZONE = _zone("COUNTER_FRONT_ZONE")  # where customers wait (used by stretch.py)
VOTE_WINDOW = 15  # per-person employee votes kept (stops label flicker)


def stamp():
    return time.strftime("%I:%M:%S %p")


def log(msg, state=None):
    line = f"[{stamp()}] {msg}"
    if state is not None:
        line = (f"[{stamp()}] {msg:<34} | In store: {state['in_store']} | Came in: {state['came_in']} | "
                f"Left: {state['left']} | Employees: {state['employees']}")
    print(line, flush=True)
    with open("events.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def to_px(zone, w, h):
    if not zone:
        return None
    x1, y1, x2, y2 = zone
    return int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)


def open_cap():
    if isinstance(SOURCE, int):
        cap = cv2.VideoCapture(SOURCE, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        return cap
    return cv2.VideoCapture(SOURCE)


def main():
    cap = open_cap()
    model = YOLO("yolov8n.pt")  # class 0 = person
    last_side = {}
    counted = defaultdict(set)  # pid -> directions already counted
    votes = defaultdict(lambda: deque(maxlen=VOTE_WINDOW))
    state = {"in_store": 0, "came_in": 0, "left": 0, "employees": 0}
    cv2.namedWindow("Surveillance.ai", cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow("Surveillance.ai", 1280, 720)

    while True:
        ok, frame = cap.read()
        if not ok:
            print("camera offline, reconnecting...")
            time.sleep(0.5)
            cap = open_cap()
            continue

        h, w = frame.shape[:2]
        door_y = int(h * DOOR_Y_FRAC)
        zone_px = to_px(COUNTER_ZONE, w, h)
        front_px = to_px(COUNTER_FRONT_ZONE, w, h)

        res = model.track(frame, classes=[0], persist=True, verbose=False, tracker="bytetrack.yaml")[0]
        people = []
        if res.boxes.id is not None:
            for box, pid in zip(res.boxes.xyxy.tolist(), res.boxes.id.int().tolist()):
                votes[pid].append(bool(is_employee(frame, box, zone_px, pid=pid)))
                people.append((pid, tuple(box), sum(votes[pid]) > len(votes[pid]) / 2))

        state["employees"] = sum(1 for _, _, emp in people if emp)

        margin = int(h * 0.05)  # dead band so jitter on the line doesn't count
        for pid, box, employee in people:
            cy = (box[1] + box[3]) / 2
            if abs(cy - door_y) < margin:
                side = last_side.get(pid)  # inside the dead band: keep the previous side
            else:
                side = "inside" if (cy > door_y) == INSIDE_IS_BELOW else "outside"
            prev = last_side.get(pid)
            if (side and prev and prev != side and not employee
                    and side not in counted[pid]):  # each direction once per person
                counted[pid].add(side)
                if side == "inside":
                    state["came_in"] += 1
                    state["in_store"] = max(state["came_in"] - state["left"], 0)
                    stretch.on_came_in(pid)
                    log(f"CUSTOMER #{pid} came in", state)
                else:
                    state["left"] += 1
                    state["in_store"] = max(state["came_in"] - state["left"], 0)
                    log(f"CUSTOMER #{pid} left{stretch.on_left(pid)}", state)
            if side:
                last_side[pid] = side

            color = (0, 140, 255) if employee else (0, 200, 0)
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"{'EMPLOYEE' if employee else 'CUSTOMER'} #{pid}", (x1, max(y1 - 6, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        for alert in stretch.on_frame(people, front_px, zone_px):
            log(f"ALERT: {alert}")
            alerts.send_alert(alert)

        # overlay
        cv2.line(frame, (0, door_y), (w, door_y), (0, 0, 255), 2)
        if zone_px:
            cv2.rectangle(frame, zone_px[:2], zone_px[2:], (255, 120, 0), 2)
        if front_px:
            cv2.rectangle(frame, front_px[:2], front_px[2:], (255, 255, 0), 1)
        hud = [f"Customers in store: {state['in_store']}", f"Came in: {state['came_in']}",
               f"Left: {state['left']}", f"Employees on floor: {state['employees']}"] + stretch.hud_lines()
        cv2.rectangle(frame, (0, 0), (340, 18 + 28 * len(hud)), (0, 0, 0), -1)
        for i, t in enumerate(hud):
            cv2.putText(frame, t, (10, 28 + 28 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.imshow("Surveillance.ai", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("s"):
            alerts.summarize_session("events.log")
        if key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    alerts.summarize_session("events.log")


if __name__ == "__main__":
    main()
