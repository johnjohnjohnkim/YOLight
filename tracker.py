import cv2
import torch
from ultralytics import YOLO
import sys
import time

import server


# --- Model setup ---------------------------------------------------------

# Use CUDA only if an NVIDIA GPU is available, otherwise fall back to CPU
# really unnecessary to be honest
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"Using device: {device}")

model = YOLO('yolov8s.pt')
model.to(device)


# --- Camera setup ---------------------------------------------------------

if 'darwin' in sys.platform: # macOS (dev machine)
    camera = cv2.VideoCapture(0)
elif 'win32' in sys.platform: # Windows (deployment target)
    camera = cv2.VideoCapture(1)


# --- Govee device discovery ------------------------------------------------

server.discover_devices()


# --- Occupancy state --------------------------------------------------------

person_present = False
safety_timestamp = None


# --- Main tracking loop ------------------------------------------------------

while camera.isOpened():
    ret, frame = camera.read()
    if not ret:
        break

    # Run inference
    results = model.track(frame, stream=False, verbose=False)

    # class 0 = person in the COCO classes YOLO is trained on
    for r in results:
        was_present = person_present
        person_present = 0 in r.boxes.cls.tolist()

        # Occupancy state machine: turn on immediately on arrival, but debounce
        # departure with a 10s grace period before turning off.
        if person_present and not was_present:
            server.turn_lights_on()
            safety_timestamp = None
        elif was_present and not person_present:
            safety_timestamp = time.monotonic()
        elif not was_present and not person_present and safety_timestamp is not None:
            if time.monotonic() >= safety_timestamp+10:
                server.turn_lights_off()
                safety_timestamp = None

        # Uncomment to view the annotated feed for debugging
        # annotated_frame = r.plot()

        # cv2.imshow("Video", annotated_frame)

    if cv2.waitKey(25) & 0xFF == ord('q'): # 'q' to quit
        break

# Release resources
camera.release()
cv2.destroyAllWindows()