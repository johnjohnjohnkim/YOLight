# YOLight

**YOL**O + **Light** — automatic occupancy lighting powered by computer vision.

YOLight watches a camera feed with a YOLO pose model and turns your
[Govee](https://www.govee.com/) smart lights **on** when someone enters the
room and **off** after they've actually left — tracked by doorway crossings,
not just by whether they're currently visible in frame. A clap gesture can
also toggle the lights directly. No motion sensors, no smart plugs required —
YOLight talks to your lights over Govee's cloud API, falling back to the
local LAN API if the cloud is unreachable.

> **V3** — doorway occupancy tracking, gated single-clap toggle, and
> cloud-first light control.

---

## How it works

```
┌────────────┐   frames   ┌──────────────┐  door crossings /  ┌────────────┐  cloud API   ┌────────────┐
│   Camera   │ ─────────► │ YOLO pose    │  clap gesture      │  server /  │  (LAN backup)│   Govee    │
│ (webcam)   │            │ (tracker.py) │ ──────────────────►│  control   │ ───────────► │   lights   │
└────────────┘            └──────────────┘                    └────────────┘              └────────────┘
```

1. **`tracker.py`** captures frames from a webcam and runs them through a
   [YOLO pose model](https://docs.ultralytics.com/) (`yolo26n-pose.pt`),
   using CUDA if an NVIDIA GPU is available and falling back to CPU
   otherwise. A pose model still reports COCO **`person`** boxes (class id
   `0`) alongside body keypoints, so one inference pass covers both
   occupancy and gesture detection.
2. On first run (or whenever you ask it to), YOLight has you draw a **door
   zone** — a box around the doorway — on the camera view. It's saved to
   `door_zone.json` and reused on future runs.
3. An **`OccupancyTracker`** follows a single representative person centroid
   across frames against the left/right edges of the door zone: a person
   **appearing** in frame counts as a room entry, and a person who steps
   into the doorway from one side and then **vanishes mid-doorway** —
   crossed one line but never the other — counts as a room exit. This means
   occupancy tracks whether
   someone has actually **left the room**, not merely left the frame — a
   person briefly occluded (behind furniture, out of the shot) doesn't cause
   a false "room is empty" read, up to `MISSING_GRACE` (15 frames) of
   missing detections.
4. Raising both wrists above both shoulders and holding the pose for
   **0.3 s** — tuned by trial and error to feel natural without firing
   accidentally — **arms** a gesture toggle; a **single clap** (wrists
   brought together, with a 0.5 s cooldown against jittery re-triggers)
   then toggles the lights directly, overriding the occupancy-driven state
   until the next fresh room entry.
5. **`server.py`** turns the lights on/off: it tries Govee's **cloud HTTP
   API** first, and if that's unreachable it discovers Govee devices on the
   local network and falls back to the LAN API; **`control.py`** formats and
   sends the actual LAN "turn" command packets. Commands run on background
   threads and fan out to all devices in parallel, so multiple lights
   switch in sync without stalling detection.

### Reliability: the occlusion problem

The first cut of this project turned lights on and off **instantly** with
the camera's view. This looked great in a demo but failed constantly in real
use: any time a person was briefly hidden from the camera — reaching behind
a closet door for clothes, ducking behind a chair — the system read the room
as empty and cut the lights, only to snap them back on a second later.

That version added a flat **3-second debounce** on turn-off (turn on
instantly, but wait before turning off), which cut false turn-offs from an
average of **~31 per day** down to **~9 per day** — a ~70% reduction — while
keeping the "walk in, lights on" response feeling instant. Those numbers
describe that earlier time-based debounce specifically; they haven't been
re-measured against the current doorway-tracking approach, which replaces
the flat timer with the frame-count occlusion tolerance described above (a
person only needs to be "missing" for a while, not out of the room, to be
tolerated) plus, more importantly, entry/exit detection that doesn't rely on
current visibility at all.

The remaining failure mode is occlusion lasting longer than
`MISSING_GRACE` while a person is mid-doorway — the tracker sees them vanish
from a section it can't yet call "inside" or "outside." Reducing that
further is the direction for future tuning (see
[the roadmap](#version-history--roadmap)).

---

## Project layout

| File                        | Responsibility                                                                                          |
| ---------------------------- | -------------------------------------------------------------------------------------------------------- |
| `tracker.py`                | Main entry point. Camera capture, YOLO pose inference, door-zone setup, occupancy tracking, and gesture detection. |
| `server.py`                 | Govee light control: cloud HTTP API (primary) with LAN multicast discovery + control (fallback).         |
| `control.py`                | Builds and sends the per-device Govee LAN "turn" command over UDP (used by the LAN fallback path).        |
| `config.py`                 | Loads settings (`IP_ADDR`, `GOVEE_API`) from a `.env` file via pydantic.                                  |
| `requirements.txt`          | Python dependencies.                                                                                      |
| `YOLODoorwayDetection.ipynb`| Experimental notebook for custom-training a model to auto-detect doorways. Not currently wired into `tracker.py`. |

`door_zone.json` (your saved door zone) and the `.pt` model weight files are
generated/downloaded locally and are git-ignored.

---

## The Govee protocol

YOLight controls lights two ways, in this order:

1. **Cloud HTTP API** (`https://openapi.api.govee.com`) — used first if a
   `GOVEE_API` key is configured and reachable.
2. **LAN UDP API** (fallback) — used if the cloud call fails. This requires
   the lights to have **LAN Control enabled** in the Govee Home app (Device
   Settings → LAN Control).

| Port   | Direction        | Purpose                                             |
| ------ | ---------------- | --------------------------------------------------- |
| `4001` | app → devices    | Send port — devices listen here for scan requests.  |
| `4002` | devices → group  | Listen port — devices reply to the multicast group. |
| `4003` | app → devices    | Control port — direct on/off/color commands.        |

LAN discovery works by sending a `scan` request to the multicast group
`239.255.255.250` and collecting every device that replies.

---

## Requirements

- Python 3.12+ (the pinned `numpy`/`scipy` require ≥3.12; verified on 3.14)
- A webcam
- A [Govee Developer API key](https://developer.govee.com/reference/apply-you-govee-api-key)
  (see [Setup](#setup)), and/or one or more Govee lights with **LAN
  Control** enabled on the same network as the machine running YOLight
- Optional: an NVIDIA GPU with CUDA for faster inference (CPU works too)

Key dependencies (see `requirements.txt` for the full pinned list):
`ultralytics`, `torch` / `torchvision`, `opencv-python`, `pydantic-settings`,
`requests`.

> **Note:** `requirements.txt` pins the standard (CPU) PyPI builds of
> `torch`/`torchvision` so it installs anywhere. For CUDA inference on an
> NVIDIA GPU, reinstall them from the PyTorch CUDA index afterwards, e.g.
> `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126`.

> **Note:** the YOLO weights file (`yolo26n-pose.pt`) is git-ignored and
> downloaded automatically by Ultralytics on first run.

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

3. **Get a Govee API key.** Install the Govee Home app and request a
   developer API key from within the app, following
   [Govee's API key application instructions](https://developer.govee.com/reference/apply-you-govee-api-key).
   The whole process — request to key arriving in your inbox — typically
   takes less than 5 minutes.

4. **Create a `.env` file** in the project root:
   ```env
   IP_ADDR=192.168.1.42
   GOVEE_API=your-govee-api-key
   ```
   - `IP_ADDR` is the local IP of the network interface that shares a subnet
     with your Govee lights, used for the LAN fallback path. This is set
     explicitly so multicast traffic doesn't leak out of a VPN/WSL/Hyper-V
     adapter on Windows.
   - `GOVEE_API` is the developer key from step 3, used for the primary
     cloud control path.

---

## Usage

**Discover your lights over LAN** (a quick sanity check that the network is
set up right for the fallback path):

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

YOLight will pick a camera (index `0` on macOS, index `1` on Windows). If no
door zone has been saved yet, it'll grab a frame and ask you to drag a box
around the doorway (press ENTER/SPACE to confirm, `c` to cancel); on later
runs it shows the saved zone and lets you press `r` to redraw it, or any
other key to keep it.

Once running, a video window shows the live feed with an overlay: the
door-zone box, gesture-arming status, and current lights state. Walk through
the doorway and the lights track room occupancy; raise both wrists for
0.3 s to arm the gesture toggle, then clap once to toggle the lights
on/off directly. Press **`q`** in the
video window to quit.

---

## Configuration notes

- **Camera index** is chosen by platform in `tracker.py`. If the wrong
  camera opens (or none does), adjust the `cv2.VideoCapture(...)` index.
- **Door zone**: redraw it (press `r` on startup, or delete
  `door_zone.json`) any time the camera moves — the saved coordinates are
  tied to the camera's exact position and framing.
- **Occlusion tolerance** for the doorway tracker defaults to
  `OccupancyTracker.MISSING_GRACE = 15` frames of missing detections before
  a mid-doorway disappearance is *not* counted as an exit. Higher = more
  tolerant of long occlusions, but slower to register a genuine exit.
- **Model**: `yolo26n-pose.pt` is used for both occupancy (person boxes) and
  gesture detection (keypoints), since a pose model reports both from one
  inference pass.

---

## Testing (local dev only)

`tests/` (unit tests for the occupancy state machine) is git-ignored and not
part of the tracked repo, so it won't come along with a fresh clone.
`serverTest.py` — a two-line manual smoke-test that turns the lights off via
`server.py` — is tracked. The occupancy unit tests mock out `cv2`/`torch`/
`ultralytics`/`server` to exercise `tracker.py`'s decision logic without a
camera or real lights; they currently target an earlier version of the
tracking logic and are not all passing against the current doorway-tracking
implementation (6 of 11 fail as of this writing).

---

## Version history & roadmap

### V1 — Frame presence, LAN only

- Person enters the frame → lights **on**; person leaves the frame → lights
  **off**. Plain YOLO person detection — no pose model.
- No Govee cloud API support — lights were controlled purely over the Govee
  LAN UDP API.
- Failed constantly under occlusion: any brief disappearance read as "room
  empty" and cut the lights (see
  [Reliability](#reliability-the-occlusion-problem)).

### V2 — Pose model + clap toggle

- Implemented the YOLO **pose model**; a clap became the action that flips
  the lights.
- Extremely buggy: hands merely held together for long stretches (e.g.
  being on your phone) counted as claps, so the lights flickered — which
  made things much worse.

### V3 — Cloud control + activation gate ✅ *(current)*

- **Govee cloud API** added, so YOLight can reach your lights from
  anywhere; the LAN API remains as an automatic fallback.
- An **activation pose** (both wrists raised, held **0.3 s**) gates the
  clap toggle so false claps no longer flicker the lights. The timing was
  tuned through trial and error — long enough to block accidental
  activations, short enough to feel natural.
- With the gate in place, the toggle switched from a double clap to a
  **single clap** (with a 0.5 s cooldown).
- Light commands run on background threads and fan out to every device in
  parallel, so multiple lights toggle at the same time.
- **Known problem:** it's currently very hard to re-toggle the lights
  through the camera.

### V4 — Frontend *(planned, two updates)*

1. A **localhost React** app.
2. TBD.

This will also open up user customization — e.g. changing the activation
hold time — with more settings to come.

### V5 — Richer pose + light control *(planned)*

- Control the **brightness** of the lights and change their **colours**
  via poses.
- Under consideration (may be too advanced): let users take pose/stance
  photos of themselves pointing at a specific light, then bind actions to
  that exact light.

### Unscheduled — depth sensing for low-light / darkness

Fix the biggest functional gap: a plain RGB camera is **blind in the dark**,
so the one moment you most want automatic lighting — walking into a
pitch-black room — is exactly when detection fails and you're forced to
flip the switch by hand. The plan is to use an **Intel RealSense D435**,
whose active-IR depth stream sees in **total darkness** without any visible
light.

- Detect people on the **depth / IR stream** when the RGB frame is too dark,
  then hand back to normal RGB + YOLO once the lights are on.
- Uses `pyrealsense2` to pull aligned depth + color frames from the D435.
- Not started yet — no `pyrealsense2` usage exists in the codebase today.

### Unscheduled — smaller improvements

- Configurable occlusion tolerance and camera index via `.env`
- **Mic + camera fusion**: cross-confirm the clap with audio so a stretch
  isn't misread as a clap and an unrelated noise isn't misread as one either
- **Auto-doorway detection**: custom-train a model (see
  `YOLODoorwayDetection.ipynb`, currently unused/experimental) to detect the
  doorway automatically, removing the manual box-drawing step
- Multi-room support keyed by which devices to control
- Headless / service mode
- Bring the `tests/` suite up to date with the current doorway-tracking
  logic and track it in git

---

*V3 — built with a YOLO pose model, OpenCV, and the Govee cloud + LAN APIs.*
