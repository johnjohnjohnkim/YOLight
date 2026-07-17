import time

import cv2

from tracker import load_model, open_camera

# COCO pose keypoint indices
LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
LEFT_WRIST, RIGHT_WRIST = 9, 10

CONF_THRESHOLD = 0.5
CLAP_WINDOW = 2.0  # seconds within which two "together" events count as a clap

model = load_model("yolo26n-pose.pt")
camera = open_camera()

wrists_were_together = False
together_timestamps = []

while camera.isOpened():
    ret, frame = camera.read()
    if not ret:
        break

    results = model(frame, stream=False, verbose=False)

    for r in results:
        annotated_frame = r.plot()

        if r.keypoints is not None and r.keypoints.conf is not None and len(r.keypoints) > 0:
            kpts = r.keypoints.xy[0]
            confs = r.keypoints.conf[0]

            if confs[LEFT_WRIST] > CONF_THRESHOLD and confs[RIGHT_WRIST] > CONF_THRESHOLD:
                left_wrist, right_wrist = kpts[LEFT_WRIST], kpts[RIGHT_WRIST]
                wrist_dist = ((left_wrist[0] - right_wrist[0]) ** 2 + (left_wrist[1] - right_wrist[1]) ** 2) ** 0.5

                # Scale the "together" threshold to shoulder width so it holds regardless of distance from camera.
                threshold = 60
                if confs[LEFT_SHOULDER] > CONF_THRESHOLD and confs[RIGHT_SHOULDER] > CONF_THRESHOLD:
                    left_shoulder, right_shoulder = kpts[LEFT_SHOULDER], kpts[RIGHT_SHOULDER]
                    shoulder_width = ((left_shoulder[0] - right_shoulder[0]) ** 2 + (left_shoulder[1] - right_shoulder[1]) ** 2) ** 0.5
                    if shoulder_width > 0:
                        threshold = shoulder_width * 0.6

                wrists_together_now = wrist_dist < threshold

                if wrists_together_now and not wrists_were_together:
                    now = time.time()
                    together_timestamps = [t for t in together_timestamps if now - t < CLAP_WINDOW] + [now]
                    if len(together_timestamps) >= 2:
                        print("clapped")
                        together_timestamps = []

                wrists_were_together = wrists_together_now

        cv2.imshow("Pose", annotated_frame)

    if cv2.waitKey(25) & 0xFF == ord('q'):  # 'q' to quit
        break

camera.release()
cv2.destroyAllWindows()