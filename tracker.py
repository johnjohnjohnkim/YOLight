import cv2
import torch
from ultralytics import YOLO
import sys
import time

# Use CUDA only if an NVIDIA GPU is available, otherwise fall back to CPU
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"Using device: {device}")

if 'darwin' in sys.platform: #For my own quick testing, macbook vs PC
    camera = cv2.VideoCapture(0)
elif 'win32' in sys.platform:
    camera = cv2.VideoCapture(1)

model = YOLO("yolo26n.pt")
model.to(device)

# --- Debounce settings so brief detection glitches don't flicker the lights ---
EMPTY_SECONDS = 5.0   # require the room to look empty this long before turning off
PRESENT_SECONDS = 1.0  # require a person this long before turning back on

lights_on = True       # assume lights start on
empty_since = None     # timestamp we first saw 0 people (None = not currently empty)
present_since = None   # timestamp we first saw a person (None = not currently present)


def turn_lights_off():
    print("[lights] OFF")
    # TODO: real API call to turn the lights off


def turn_lights_on():
    print("[lights] ON")
    # TODO: real API call to turn the lights on


while camera.isOpened():
    ret, frame = camera.read()
    if not ret:
        break

    # Run inference (class 0 = person)
    results = model.predict(frame, classes=[0], verbose=False)
    num_people = len(results[0].boxes)  # people detected in this frame

    annotated_frame = results[0].plot()

    # Display the annotated frame instead of the raw one
    cv2.imshow("Video", annotated_frame)

    if cv2.waitKey(25) & 0xFF == ord('q'): # Changed to 1ms delay for smoother live video
        break

# Release resources
camera.release()
cv2.destroyAllWindows()