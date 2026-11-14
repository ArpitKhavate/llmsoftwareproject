"""Surveillance.ai: live customer in/out counter (LLMSoftware x UTD Challenge 1).

Run:  python main.py            (webcam index from CAMERA in .env, default 0)
Keys: q = quit
"""
import os
import time
from collections import defaultdict, deque

import cv2
from dotenv import load_dotenv
from ultralytics import YOLO

from employee import is_employee

load_dotenv()

# CAMERA can be a webcam index ("0", "1") or a path/URL ("nest_backup.mp4")
_src = os.getenv("CAMERA", "0")
SOURCE = int(_src) if _src.isdigit() else _src

# Door line: horizontal line at DOOR_Y as a fraction of frame height (tune for your camera)
DOOR_Y_FRAC = float(os.getenv("DOOR_Y_FRAC", "0.5"))
INSIDE_IS_BELOW = os.getenv("INSIDE_IS_BELOW", "1") == "1"  # flip if the door faces the other way
# Counter zone (x1,y1,x2,y2 as fractions of frame), anyone whose feet are inside = employee
COUNTER_ZONE = os.getenv("COUNTER_ZONE")  # e.g. "0.6,0.0,1.0,0.4"
COUNTER_ZONE = tuple(float(v) for v in COUNTER_ZONE.split(",")) if COUNTER_ZONE else None

VOTE_WINDOW = 15  # frames of employee/customer votes kept per person (stops label flicker)


def log(msg, state):
    line = (f"[{time.strftime('%I:%M:%S %p')}] {msg:<28} | In store: {state['in_store']} | "
            f"Came in: {state['came_in']} | Left: {state['left']} | Employees: {state['employees']}")
    print(line, flush=True)
    with open("events.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    cap = cv2.VideoCapture(SOURCE, cv2.CAP_DSHOW) if isinstance(SOURCE, int) else cv2.VideoCapture(SOURCE)
    model = YOLO("yolov8n.pt")  # class 0 = person
    last_side = {}
    votes = defaultdict(lambda: deque(maxlen=VOTE_WINDOW))
    state = {"in_store": 0, "came_in": 0, "left": 0, "employees": 0}

    while True:
        ok, frame = cap.read()
        if not ok:
            print("camera offline, reconnecting...")
            time.sleep(0.5)
            cap = cv2.VideoCapture(SOURCE)
            continue

        h, w = frame.shape[:2]
        door_y = int(h * DOOR_Y_FRAC)
        zone_px = None
        if COUNTER_ZONE:
            zx1, zy1, zx2, zy2 = COUNTER_ZONE
            zone_px = (int(zx1 * w), int(zy1 * h), int(zx2 * w), int(zy2 * h))

        res = model.track(frame, classes=[0], persist=True, verbose=False, tracker="bytetrack.yaml")[0]
        employees_now = 0

        if res.boxes.id is not None:
            for box, pid in zip(res.boxes.xyxy.tolist(), res.boxes.id.int().tolist()):
                votes[pid].append(is_employee(frame, box, zone_px))
                employee = sum(votes[pid]) > len(votes[pid]) / 2
                if employee:
                    employees_now += 1

                cy = (box[1] + box[3]) / 2
                below = cy > door_y
                side = "inside" if below == INSIDE_IS_BELOW else "outside"
                if not employee and pid in last_side and last_side[pid] != side:
                    if side == "inside":
                        state["came_in"] += 1
                        log(f"CUSTOMER #{pid} came in", {**state, "in_store": max(state["came_in"] - state["left"], 0), "employees": employees_now})
                    else:
                        state["left"] += 1
                        log(f"CUSTOMER #{pid} left", {**state, "in_store": max(state["came_in"] - state["left"], 0), "employees": employees_now})
                last_side[pid] = side

                color = (0, 140, 255) if employee else (0, 200, 0)
                label = f"{'EMPLOYEE' if employee else 'CUSTOMER'} #{pid}"
                x1, y1, x2, y2 = map(int, box)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, label, (x1, max(y1 - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        state["employees"] = employees_now
        state["in_store"] = max(state["came_in"] - state["left"], 0)

        cv2.line(frame, (0, door_y), (w, door_y), (0, 0, 255), 2)
        if zone_px:
            cv2.rectangle(frame, zone_px[:2], zone_px[2:], (255, 120, 0), 2)
        hud = [f"Customers in store: {state['in_store']}", f"Came in: {state['came_in']}",
               f"Left: {state['left']}", f"Employees on floor: {state['employees']}"]
        cv2.rectangle(frame, (0, 0), (330, 30 + 28 * len(hud)), (0, 0, 0), -1)
        for i, t in enumerate(hud):
            cv2.putText(frame, t, (10, 28 + 28 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.imshow("Surveillance.ai", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
