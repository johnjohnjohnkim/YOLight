import cv2
import torch
from ultralytics import YOLO

# Use CUDA only if an NVIDIA GPU is available, otherwise fall back to CPU
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"Using device: {device}")

model = YOLO('yolov8s.pt')
model.to(device)

camera = cv2.VideoCapture(1)

while camera.isOpened():
    ret, frame = camera.read()

    if not ret:
        break   # No more frames -> exit loop

    detections = model(frame)
    print(detections)

    cv2.imshow("Video", frame)

    # Press Q to quit
    if cv2.waitKey(25) & 0xFF == ord('q'):
        break

# Release resources
camera.release()
cv2.destroyAllWindows()