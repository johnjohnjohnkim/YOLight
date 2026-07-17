import cv2
import torch
from ultralytics import YOLO
import sys
import json
import os
import time
from enum import Enum

import server

DOOR_ZONE_FILE = "door_zone.json"


def load_model(weights):
    """Load a YOLO model from `weights` and move it to CUDA if available, else CPU."""
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Using device: {device}")

    model = YOLO(weights)
    model.to(device)
    return model


def open_camera():
    """Open the webcam. Camera index differs by platform."""
    if 'darwin' in sys.platform: # macOS (dev machine)
        return cv2.VideoCapture(0)
    elif 'win32' in sys.platform: # Windows (deployment target)
        return cv2.VideoCapture(1)


def load_door_zone():
    """Load a previously saved door zone from disk, if one exists."""
    if not os.path.exists(DOOR_ZONE_FILE):
        return None
    with open(DOOR_ZONE_FILE) as f:
        return tuple(json.load(f))


def save_door_zone(zone):
    with open(DOOR_ZONE_FILE, "w") as f:
        json.dump(zone, f)


def select_door_zone(camera):
    """Grab a frame and let the user drag a box around the door."""
    ret, frame = camera.read()
    if not ret:
        raise RuntimeError("Could not read a frame from the camera to select the door zone.")

    print("Draw a box around the door, then press ENTER/SPACE. Press 'c' to cancel.")
    x, y, w, h = cv2.selectROI("Select Door", frame, showCrosshair=False, fromCenter=False)
    cv2.destroyWindow("Select Door")

    if w == 0 or h == 0:
        raise RuntimeError("No door zone selected.")

    zone = (int(x), int(y), int(w), int(h))
    save_door_zone(zone)
    return zone


def get_door_zone(camera):
    """Return the door zone, prompting the user to (re)draw it if needed.

    Coordinates are tied to camera position/framing, so moving the camera
    invalidates a saved zone and requires redrawing it.
    """
    existing = load_door_zone()
    if existing is None:
        print("No door zone saved yet.")
        return select_door_zone(camera)

    ret, frame = camera.read()
    if not ret:
        return existing

    x, y, w, h = existing
    preview = frame.copy()
    cv2.rectangle(preview, (x, y), (x + w, y + h), (0, 255, 0), 2)
    cv2.putText(preview, "Press 'r' to redraw the door zone, any other key to keep it",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.imshow("Door Zone", preview)
    key = cv2.waitKey(0) & 0xFF
    cv2.destroyWindow("Door Zone")

    if key == ord('r'):
        return select_door_zone(camera)
    return existing


class Section(Enum):
    LEFT = "left"
    DOORWAY = "doorway"
    RIGHT = "right"


class OccupancyTracker:
    """Tracks room occupancy using door-zone line crossings.

    Rather than tracking each person individually, we follow a single
    representative centroid across frames: whichever detection is closest to
    where that centroid was last seen. This is far simpler than per-person
    tracking (no ids, no per-track state) at the cost of accuracy when
    multiple people cross the door at the same time.

    A representative centroid disappearing from detections could mean either
    "walked out the door" or "occluded somewhere inside the room" -- both
    look the same to the raw per-frame detections. Only a disappearance while
    last seen mid-doorway, having crossed one line but not the other, counts
    as an exit.
    """

    MISSING_GRACE = 15  # frames tolerated before declaring the tracked centroid gone

    def __init__(self, door_zone):
        dx, dy, dw, dh = door_zone
        self.left_line = dx
        self.right_line = dx + dw
        self.section = None  # Section of the last-seen centroid, or None if nobody's tracked
        self.cx = None
        self.entered_doorway_from = None  # Section they were in before entering the doorway
        self.frames_missing = 0
        self.room_count = 0

    def _section_of(self, cx):
        if cx < self.left_line:
            return Section.LEFT
        if cx > self.right_line:
            return Section.RIGHT
        return Section.DOORWAY

    def update(self, centroids):
        """Update state given this frame's person detections.

        `centroids` is an iterable of centroid_x values for class-0 boxes.
        Returns the visible_count.
        """
        if not centroids:
            if self.section is not None:
                self.frames_missing += 1
                if self.frames_missing >= self.MISSING_GRACE:
                    if self.section == Section.DOORWAY and self.entered_doorway_from is not None:
                        self.room_count -= 1  # crossed one line, vanished before crossing the other -> exited
                    self.section = None
                    self.entered_doorway_from = None
            self.room_count = max(self.room_count, 0)
            return 0

        self.frames_missing = 0

        # Follow whichever centroid is closest to the last-known position, so a
        # single tracked person doesn't jump between detections frame to frame.
        # If nobody's tracked yet, pick whichever is closest to the door.
        if self.cx is not None:
            cx = min(centroids, key=lambda c: abs(c - self.cx))
        else:
            zone_center = (self.left_line + self.right_line) / 2
            cx = min(centroids, key=lambda c: abs(c - zone_center))

        new_section = self._section_of(cx)

        if self.section is None:
            if new_section != Section.DOORWAY:
                self.room_count += 1  # appeared already inside a section -> entry
        elif self.section != Section.DOORWAY and new_section == Section.DOORWAY:
            self.entered_doorway_from = self.section
        elif self.section == Section.DOORWAY and new_section != Section.DOORWAY:
            if self.entered_doorway_from is None:
                self.room_count += 1  # first seen mid-doorway -> confirmed entry now
            self.entered_doorway_from = None

        self.section = new_section
        self.cx = cx
        self.room_count = max(self.room_count, 0)
        return len(centroids)


class ClapDetector:
    """Detects a clap gesture: left and right wrists meeting twice within CLAP_WINDOW seconds."""

    CONF_THRESHOLD = 0.5
    CLAP_WINDOW = 2.0  # seconds within which two "together" events count as a clap

    LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
    LEFT_WRIST, RIGHT_WRIST = 9, 10

    def __init__(self):
        self.wrists_were_together = False
        self.together_timestamps = []

    def update(self, keypoints):
        """Check this frame's pose keypoints for a wrists-together event.

        `keypoints` is the ultralytics Keypoints object for the frame (or None).
        Returns True the instant a clap is detected.
        """
        if keypoints is None or keypoints.conf is None or len(keypoints) == 0:
            return False

        kpts = keypoints.xy[0]
        confs = keypoints.conf[0]

        if confs[self.LEFT_WRIST] <= self.CONF_THRESHOLD or confs[self.RIGHT_WRIST] <= self.CONF_THRESHOLD:
            return False

        left_wrist, right_wrist = kpts[self.LEFT_WRIST], kpts[self.RIGHT_WRIST]
        wrist_dist = ((left_wrist[0] - right_wrist[0]) ** 2 + (left_wrist[1] - right_wrist[1]) ** 2) ** 0.5

        # Scale the "together" threshold to shoulder width so it holds regardless of distance from camera.
        threshold = 60
        if confs[self.LEFT_SHOULDER] > self.CONF_THRESHOLD and confs[self.RIGHT_SHOULDER] > self.CONF_THRESHOLD:
            left_shoulder, right_shoulder = kpts[self.LEFT_SHOULDER], kpts[self.RIGHT_SHOULDER]
            shoulder_width = ((left_shoulder[0] - right_shoulder[0]) ** 2 + (left_shoulder[1] - right_shoulder[1]) ** 2) ** 0.5
            if shoulder_width > 0:
                threshold = shoulder_width * 0.6

        wrists_together_now = wrist_dist < threshold
        clapped = False

        if wrists_together_now and not self.wrists_were_together:
            now = time.time()
            self.together_timestamps = [t for t in self.together_timestamps if now - t < self.CLAP_WINDOW] + [now]
            if len(self.together_timestamps) >= 2:
                clapped = True
                self.together_timestamps = []

        self.wrists_were_together = wrists_together_now
        return clapped


def main():
    # A pose model still detects person boxes (for occupancy) alongside
    # keypoints (for the clap gesture), so one model/one inference pass covers both.
    model = load_model('yolo26n-pose.pt')
    camera = open_camera()

    door_zone = get_door_zone(camera)
    dx, dy, dw, dh = door_zone
    occupancy = OccupancyTracker(door_zone)
    clap_detector = ClapDetector()

    # Discover Govee devices before we start watching.
    server.discover_devices()

    # --- Occupancy state ---
    lights_on = False
    clapped_bool = False  # True while a clap is overriding the presence-based auto-on

    # --- Main tracking loop ---
    while camera.isOpened():
        ret, frame = camera.read()
        if not ret:
            break

        # Run inference
        results = model(frame, stream=False, verbose=False)

        # class 0 = person, the only class pose models detect
        for r in results:
            boxes = r.boxes
            centroids = [
                (xyxy[0] + xyxy[2]) / 2
                for cls, xyxy in zip(boxes.cls.tolist(), boxes.xyxy.tolist())
                if int(cls) == 0
            ]

            if clap_detector.update(r.keypoints):
                print("clapped")
                lights_on = not lights_on
                if lights_on:
                    server.turn_lights_on()
                else:
                    server.turn_lights_off()
                clapped_bool = True

            room_count_before = occupancy.room_count
            visible_count = occupancy.update(centroids)
            if occupancy.room_count > room_count_before:
                clapped_bool = False  # a fresh entry cancels the clap override

            # Lights stay on if someone is visible right now, or if the room
            # is still occupied (someone visible earlier hasn't been seen
            # exit through the door -- they may just be occluded). A clap
            # toggles them and overrides this until the next fresh entry.
            if not clapped_bool:
                should_be_on = visible_count > 0 or occupancy.room_count > 0
                if should_be_on and not lights_on:
                    server.turn_lights_on()
                    lights_on = True
                elif not should_be_on and lights_on:
                    server.turn_lights_off()
                    lights_on = False

            # Uncomment to view the annotated feed for debugging
            annotated_frame = r.plot()
            cv2.rectangle(annotated_frame, (dx, dy), (dx + dw, dy + dh), (0, 255, 0), 2)

            cv2.imshow("Video", annotated_frame)

        if cv2.waitKey(25) & 0xFF == ord('q'): # 'q' to quit
            break

    # Release resources
    camera.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
