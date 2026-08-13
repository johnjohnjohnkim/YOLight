# Prototype for an "activation pose" gesture: both wrists raised above both
# shoulders, held continuously for HOLD_SECONDS. The idea is to require this
# pose before the clap toggle (see ClapDetector in tracker.py) is allowed to
# fire, so it doesn't get set off by hands merely being close together for
# some other reason (e.g. holding a phone with both hands). The hold-time
# requirement additionally guards against momentarily raising an arm while
# gesturing/stretching/etc.

import time

import cv2

from tracker import load_model, open_camera

# COCO pose keypoint indices
LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
LEFT_WRIST, RIGHT_WRIST = 9, 10

CONF_THRESHOLD = 0.5
HOLD_SECONDS = 1.0  # how long the pose must be held continuously to arm

model = load_model("yolo26n-pose.pt")
camera = open_camera()

armed = False  # True once the pose has been held for HOLD_SECONDS
raised_since = None  # timestamp the pose started being held, or None if not currently held

while camera.isOpened():
    ret, frame = camera.read()
    if not ret:
        break

    results = model(frame, stream=False, verbose=False)

    for r in results:
        annotated_frame = r.plot()

        raised_now = False

        if r.keypoints is not None and r.keypoints.conf is not None and len(r.keypoints) > 0:
            kpts = r.keypoints.xy[0]
            confs = r.keypoints.conf[0]

            required = (LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_WRIST, RIGHT_WRIST)
            if all(confs[i] > CONF_THRESHOLD for i in required):
                left_shoulder, right_shoulder = kpts[LEFT_SHOULDER], kpts[RIGHT_SHOULDER]
                left_wrist, right_wrist = kpts[LEFT_WRIST], kpts[RIGHT_WRIST]

                # Image y grows downward, so "above" means a smaller y value.
                raised_now = left_wrist[1] < left_shoulder[1] and right_wrist[1] < right_shoulder[1]

        if raised_now and raised_since is None:
            raised_since = time.time()
        elif not raised_now:
            raised_since = None

        armed_now = raised_since is not None and time.time() - raised_since >= HOLD_SECONDS

        if armed_now and not armed:
            print("activated")
        elif not armed_now and armed:
            print("deactivated")
        armed = armed_now

        if raised_now and not armed:
            held_for = time.time() - raised_since
            status = f"HOLDING {held_for:.1f}/{HOLD_SECONDS}s"
            color = (0, 255, 255)
        else:
            status = f"ARMED: {armed}"
            color = (0, 255, 0) if armed else (0, 0, 255)
        cv2.putText(annotated_frame, status, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        cv2.imshow("Pose", annotated_frame)

    if cv2.waitKey(25) & 0xFF == ord('q'):  # 'q' to quit
        break

camera.release()
cv2.destroyAllWindows()