# YOLight

**YOL**O + **Light** — automatic occupancy lighting powered by computer vision.

YOLight watches a camera feed with a YOLO object-detection model and turns your
[Govee](https://www.govee.com/) smart lights **on** when a person walks into
frame and **off** shortly after everyone leaves. No motion sensors, no smart
plugs, no cloud account — everything runs locally on your machine and talks to
the lights directly over your LAN using Govee's UDP LAN API.

> **V1** — first working release.

---

## How it works

```
┌────────────┐   frames   ┌─────────────┐   on/off    ┌────────────┐   UDP    ┌────────────┐
│   Camera   │ ─────────► │ YOLO model  │ ──────────► │  server /  │ ───────► │   Govee    │
│ (webcam)   │            │ (tracker.py)│  occupancy  │  control   │  LAN API │   lights   │
└────────────┘            └─────────────┘             └────────────┘          └────────────┘
```

1. **`tracker.py`** captures frames from a webcam and runs them through the
   [Ultralytics YOLOv8](https://docs.ultralytics.com/) model (`yolov8s.pt`),
   using CUDA if an NVIDIA GPU is available and falling back to CPU otherwise.
2. Each frame is checked for the COCO **`person`** class (class id `0`).
3. A small occupancy state machine decides when to switch the lights:
   - **Person appears** → lights turn **on** immediately.
   - **Person leaves** → a **3-second grace period** starts (debounce), and if no
     one returns before it elapses, the lights turn **off**.
4. **`server.py`** discovers Govee devices on the network and broadcasts on/off
   commands; **`control.py`** formats and sends the actual Govee LAN API
   packets to each device.

### Reliability: the occlusion problem

The first cut turned lights on and off **instantly** with the camera's view. This
looked great in a demo but failed constantly in real use: any time the person was
briefly hidden from the camera — reaching behind a closet door for clothes, ducking
behind a chair — the system read the room as empty and cut the lights, only to
snap them back on a second later.

Adding the **3-second debounce** on turn-off (turn on instantly, but wait before
turning off) cut these false turn-offs from an average of **~31 per day** down to
**~9 per day** — a ~70% reduction — while keeping the "walk in, lights on" response
feeling instant.

The remaining failures are longer occlusions that outlast the grace period.
Eliminating them entirely is the goal of **V2's doorway occupancy counting**
(see the [Roadmap](#roadmap)), which tracks whether a person has actually *left
the room* rather than merely *left the frame*.

---

## Project layout

| File              | Responsibility                                                                 |
| ----------------- | ------------------------------------------------------------------------------ |
| `tracker.py`      | Main entry point. Camera capture, YOLO inference, and the occupancy state machine. |
| `server.py`       | Govee device discovery via multicast + high-level `turn_lights_on/off` helpers. |
| `control.py`      | Builds and sends the per-device Govee LAN "turn" command over UDP.             |
| `config.py`       | Loads settings (your local network IP) from a `.env` file via pydantic.        |
| `requirements.txt`| Python dependencies.                                                            |

---

## The Govee LAN protocol

YOLight speaks Govee's local UDP API, so the lights must have **LAN Control
enabled** in the Govee Home app (Device Settings → LAN Control).

| Port   | Direction        | Purpose                                             |
| ------ | ---------------- | --------------------------------------------------- |
| `4001` | app → devices    | Send port — devices listen here for scan requests.  |
| `4002` | devices → group  | Listen port — devices reply to the multicast group. |
| `4003` | app → devices    | Control port — direct on/off/color commands.        |

Discovery works by sending a `scan` request to the multicast group
`239.255.255.250` and collecting every device that replies.

---

## Requirements

- Python 3.11+ (developed against a 3.14 virtual environment)
- A webcam
- One or more Govee lights with **LAN Control** enabled, on the **same network**
  as the machine running YOLight
- Optional: an NVIDIA GPU with CUDA for faster inference (CPU works too)

Key dependencies (see `requirements.txt` for the full pinned list):
`ultralytics`, `torch` / `torchvision`, `opencv-python`, `pydantic-settings`.

> **Note:** the YOLO weights file (`yolov8s.pt`) is git-ignored and downloaded
> automatically by Ultralytics on first run.

---

## Setup

1. **Clone and enter the repo**
   ```bash
   git clone <your-repo-url> YOLight
   cd YOLight
   ```

2. **Create a virtual environment and install dependencies**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS / Linux
   source venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Create a `.env` file** in the project root with the local IP of the network
   interface that shares a subnet with your Govee lights. This is set explicitly
   so multicast traffic doesn't leak out of a VPN/WSL/Hyper-V adapter on Windows.
   ```env
   IP_ADDR=192.168.1.42
   ```

---

## Usage

**Discover your lights** (a quick sanity check that the network is set up right):

```bash
python server.py
```

You should see something like:

```
Scanning for Govee devices...
  + Found H6199 at 192.168.1.55
Done scanning. Found 1 device(s).
```

**Run the full occupancy-lighting system:**

```bash
python tracker.py
```

YOLight will pick a camera (index `0` on macOS, index `1` on Windows), discover
your Govee devices, and start watching. Walk into frame and the lights come on;
step away and, after the grace period, they turn off. Press **`q`** in the video
window to quit.

To watch what the model sees, uncomment the `annotated_frame` / `cv2.imshow`
lines near the bottom of `tracker.py`.

---

## Configuration notes

- **Camera index** is chosen by platform in `tracker.py`. If the wrong camera
  opens (or none does), adjust the `cv2.VideoCapture(...)` index.
- **Grace period** for turning lights off after the last person leaves defaults
  to **3 seconds**, set by the timeout comparison in the occupancy state machine
  in `tracker.py`. Longer = fewer false turn-offs from occlusion, but lights
  linger longer after you actually leave. Tune it to taste.
- **Model size**: `yolov8s.pt` (small) balances speed and accuracy. Swap it for
  `yolov8n.pt` (nano, faster) or a larger variant depending on your hardware.

---

## Roadmap

Ordered by priority, not just by version number.

### V1 — Instant occupancy lighting ✅ *(current)*

Real-time person detection drives the lights, with a 3-second turn-off debounce
that cut false turn-offs from ~31/day to ~9/day (see
[Reliability](#reliability-the-occlusion-problem)).

### V2 — Doorway occupancy counting *(next)*

Eliminate occlusion false-offs entirely by tracking whether a person actually
**left the room** rather than merely **left the frame**:

- User sets a **doorway line/region** on the camera view during setup.
- The existing YOLO **tracker** (persistent track IDs) counts people crossing
  the line — inward increments occupancy, outward decrements it.
- Lights stay on while `occupancy > 0`, regardless of who's currently visible.

This is the killer feature: it turns "lights that follow the camera" into
"lights that follow the room."

### V3 — Gesture & pose control

Swap in **YOLOv8-pose** to trigger custom actions from body movement, e.g. wave
your arms down to **dim** the lights after they've turned on.

- Gestures like "clap twice to turn off" fuse **camera + mic**: the two signals
  cross-confirm each other to reject false positives — the mic rules out the
  vision model mistaking a stretch for a clap, and the camera rules out an
  accidental crashing noise being read as a deliberate double-clap.
- Stretch: **custom-train** a model to auto-detect doorways, removing the manual
  setup step from V2.

### V4 — Govee Cloud backend *(nice-to-have, any time)*

Support bulbs that **don't** expose the LAN API by adding cloud control. Lower
risk and independent of the vision work, so it can slot in whenever:

- Introduce a `LightBackend` abstraction with `LANBackend` and `CloudBackend`
  implementations, so the detection logic doesn't care how a light is reached.
- Authenticate against the Govee Cloud API and route commands per-device.

### Smaller improvements (any time)

- Configurable grace period and camera index via `.env`
- Color / brightness control (the LAN API supports more than on/off)
- Multi-room support keyed by which devices to control
- Headless / service mode

---

*V1 — built with YOLOv8, OpenCV, and the Govee LAN API.*
