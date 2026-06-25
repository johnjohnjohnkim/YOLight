import cv2
from ultralytics import YOLO

cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()

    if not ret:
        break   # No more frames -> exit loop

    cv2.imshow("Video", frame)

    # Press Q to quit
    if cv2.waitKey(25) & 0xFF == ord('q'):
        break

# Release resources
cap.release()
cv2.destroyAllWindows()