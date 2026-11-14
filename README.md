# Surveillance.ai: Who's Coming, Who's Leaving

LLMSoftware x UT Dallas Hackathon, Challenge 1. A live webcam feed is turned into counts: customers in the store, came in, left, and employees on the floor, plus an event log.

## Run
```
pip install -r requirements.txt
cp .env.example .env     # set CAMERA (Logitech is usually 1) and keys
python main.py           # q to quit
```

## How it works
- **Detect + track:** YOLOv8n with ByteTrack gives each person a stable ID.
- **Employee vs customer:** a black apron on the torso, or feet inside the counter zone. A majority vote over 15 frames stops the label flickering (`employee.py`).
- **In/out:** a customer crossing the door line changes Came in / Left. Employees are never counted.
- **Log:** every event is printed and appended to `events.log`.

## Privacy
No face recognition. No video is saved.
