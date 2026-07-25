"""Live MJPEG streaming engine — true real-time tracking.

One worker thread per direction runs YOLO + tracking continuously, fully
decoupled from Streamlit's rerun cycle. Annotated frames are served as MJPEG
over a tiny stdlib HTTP server; the browser plays them through a plain <img>
tag. Only OpenCV + the standard library — no av / aiortc / WebRTC.
"""

import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import cv2

from models.detector import load_model_fresh, run_tracking
from geometry.assignment import assign_to_shapes, counts_for_direction, filter_to_lanes
from tracking.pedestrian_wait import PedestrianWaitTracker
from visualization.annotate import annotate_frame
from video.sources import ImageSource, VideoSource, CameraSource


# ── Thread-safe shared state ──────────────────────────────────────────────
class _SharedState:
    def __init__(self):
        self.lock = threading.Lock()
        self.jpeg = {}     # direction -> latest JPEG bytes
        self.counts = {}   # direction -> latest counts
        self.meta = {}     # direction -> {n_dets, frame_idx, total}
        self.signal = {}   # direction -> lamp colour (written by decision panel)
        self.running = {}  # direction -> playing?
        self.alive = {}    # direction -> worker alive?
        self.port = None
        self.decision_result = None   


shared = _SharedState()
_threads = {}
_server = None
_server_lock = threading.Lock()

_LAMP_BGR = {"red": (60, 60, 255), "yellow": (10, 214, 255), "green": (0, 200, 80)}


# ── MJPEG HTTP server ─────────────────────────────────────────────────────
class _MJPEGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/video":
            self.send_response(404)
            self.end_headers()
            return
        direction = parse_qs(parsed.query).get("dir", [""])[0]
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        try:
            while True:
                with shared.lock:
                    jpeg = shared.jpeg.get(direction)
                if jpeg:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n")
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                time.sleep(0.033)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def log_message(self, *args):
        pass  # silence per-request logs


def ensure_server() -> int:
    """Start the MJPEG server once; return its port."""
    global _server
    with _server_lock:
        if _server is not None:
            return shared.port
        for port in range(8502, 8512):
            try:
                _server = ThreadingHTTPServer(("127.0.0.1", port), _MJPEGHandler)
                shared.port = port
                break
            except OSError:
                continue
        if _server is None:
            raise RuntimeError("No free port for the MJPEG server.")
        threading.Thread(target=_server.serve_forever, daemon=True).start()
    return shared.port


# ── Per-direction worker ──────────────────────────────────────────────────
def _process_loop(direction, source, model_name, tracker, conf, imgsz, speed_thresh, shapes):
    model = load_model_fresh(model_name)          # own model + tracker per thread
    track_history = defaultdict(lambda: deque(maxlen=15))
    ped_wait = PedestrianWaitTracker()
    fps = source.fps or 30.0
    dt = 1.0 / fps
    is_image = isinstance(source, ImageSource)

    while True:
        with shared.lock:
            if not shared.alive.get(direction, False):
                break
            playing = shared.running.get(direction, False)
            sig_straight = shared.signal.get(f"{direction}_straight", "red")
            sig_turn = shared.signal.get(f"{direction}_turn", "red")
            
            if sig_straight == "green" or sig_turn == "green":
                sig_display = "green"
            elif sig_straight == "yellow" or sig_turn == "yellow":
                sig_display = "yellow"
            else:
                sig_display = "red"
                
            has_counted = direction in shared.counts

        if not playing or (has_counted and sig_display in ("red", "flashing_red") and not is_image):
            time.sleep(0.05)
            continue

        ret, frame = source.read()
        if not ret or frame is None:
            if isinstance(source, VideoSource):
                source.restart()                   # loop the footage
                continue
            break

        # ── pipeline ──
        dets = run_tracking(frame, model, track_history, conf=conf, imgsz=imgsz,
                            speed_thresh=speed_thresh, tracker=tracker)
        dets = filter_to_lanes(dets, shapes)
        dets = ped_wait.update(dets, shapes, dt)
        dets = assign_to_shapes(dets, shapes, track_history)
        counts = counts_for_direction(dets, shapes)

        with shared.lock:
            sig_straight = shared.signal.get(f"{direction}_straight", "red")
            sig_turn = shared.signal.get(f"{direction}_turn", "red")
            sig_display = "green" if "green" in (sig_straight, sig_turn) else "yellow" if "yellow" in (sig_straight, sig_turn) else "red"

        annotated = annotate_frame(frame, dets, shapes)
        cv2.circle(annotated, (30, 30), 14, (18, 22, 30), -1)
        cv2.circle(annotated, (30, 30), 9, _LAMP_BGR.get(sig_display, _LAMP_BGR["red"]), -1)
        for det in dets:
            if det["category"] == "pedestrian" and det.get("ped_wait_time", 0) > 1:
                x = int(det["center"][0]) - 30
                y = max(int(det["bbox"][1]) - 24, 14)
                cv2.putText(annotated, f"wait {det['ped_wait_time']}s", (x, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 2)

        ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            with shared.lock:
                shared.jpeg[direction] = buf.tobytes()
                shared.counts[direction] = counts
                shared.meta[direction] = {
                    "n_dets": len(dets),
                    "frame_idx": source.position,
                    "total": source.total_frames,
                }

        if is_image:
            time.sleep(0.2)                        # don't hammer a still frame


def start_stream(direction, source, model_name, tracker, conf, imgsz, speed_thresh, shapes):
    """Start (or resume) the worker for a direction."""
    t = _threads.get(direction)
    if t is not None and t.is_alive() and shared.alive.get(direction):
        with shared.lock:
            shared.running[direction] = True       # resume from where it paused
        return
    with shared.lock:
        shared.alive[direction] = True
        shared.running[direction] = True
    thread = threading.Thread(
        target=_process_loop,
        args=(direction, source, model_name, tracker, conf, imgsz, speed_thresh, shapes),
        daemon=True,
    )
    _threads[direction] = thread
    thread.start()


def pause_all():
    with shared.lock:
        for d in shared.running:
            shared.running[d] = False


def resume_all():
    with shared.lock:
        for d in shared.alive:
            if shared.alive[d]:
                shared.running[d] = True


def stop_all():
    with shared.lock:
        for d in list(shared.alive):
            shared.alive[d] = False
            shared.running[d] = False


def clear_state():
    with shared.lock:
        shared.jpeg.clear()
        shared.counts.clear()
        shared.meta.clear()
        shared.signal.clear()