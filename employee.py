"""Employee vs customer: black apron on the torso, or feet inside the counter zone."""
import cv2

APRON_SHARE = 0.35   # tune to your camera / lighting
BLACK_V_MAX = 60     # HSV brightness ceiling for "black"


def is_employee(frame, box, counter_zone=None):
    x1, y1, x2, y2 = [int(v) for v in box]
    if counter_zone:
        cx, feet_y = (x1 + x2) / 2, y2
        zx1, zy1, zx2, zy2 = counter_zone
        if zx1 <= cx <= zx2 and zy1 <= feet_y <= zy2:
            return True
    h = y2 - y1
    torso = frame[max(y1 + int(h * 0.30), 0): y1 + int(h * 0.65), max(x1, 0):x2]
    if torso.size == 0:
        return False
    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
    apron = cv2.inRange(hsv, (0, 0, 0), (180, 255, BLACK_V_MAX))
    return apron.mean() / 255 > APRON_SHARE
