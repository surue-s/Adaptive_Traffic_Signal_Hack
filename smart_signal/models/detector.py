"""YOLO model loading, tracking, and motion classification (thread-safe)."""

import math
from collections import deque
from typing import Any, Dict, List, Tuple

import numpy as np
import streamlit as st


CATEGORY_MAP: Dict[str, str] = {
    "person": "pedestrian",
    "bicycle": "vehicle", "car": "vehicle", "motorcycle": "vehicle",
    "bus": "vehicle", "truck": "vehicle",
}


@st.cache_resource
def load_model(model_name: str = "AUTA_Aerial_N_Rapid.pt", tracker: str = "botsort.yaml"):
    """Cached single instance — fine for main-thread use only."""
    from ultralytics import YOLO
    return YOLO(model_name)


def load_model_fresh(model_name: str = "AUTA_Aerial_N_Rapid.pt"):
    """A dedicated YOLO instance with its own predictor + tracker.

    Each worker thread needs its own instance — concurrent .track() calls on a
    shared model would corrupt the tracker state.
    """
    from ultralytics import YOLO
    return YOLO(model_name)


def classify_motion(track_id: int, center: Tuple[float, float], thresh: float,
                    history: Dict[int, deque]) -> str:
    """moving / waiting / unknown from displacement over recent frames."""
    hist = history[track_id]
    hist.append(center)
    if len(hist) < 5:
        return "unknown"
    dx = hist[-1][0] - hist[0][0]
    dy = hist[-1][1] - hist[0][1]
    speed = math.sqrt(dx * dx + dy * dy) / len(hist)
    return "moving" if speed > thresh else "waiting"


def run_tracking(frame: np.ndarray, model, track_history: Dict[int, deque],
                 conf: float = 0.25, imgsz: int = 640,
                 speed_thresh: float = 3.0, tracker: str = "botsort.yaml") -> List[Dict[str, Any]]:
    """Detect + track one frame. track_history is injected (thread-safe)."""
    results = model.track(frame, conf=conf, imgsz=imgsz, iou=0.45,
                          persist=True, tracker=tracker, verbose=False)[0]
    dets: List[Dict[str, Any]] = []
    if results.boxes is None or results.boxes.id is None:
        return dets
    for box in results.boxes:
        cls_name = model.names[int(box.cls[0])]
        if cls_name not in CATEGORY_MAP:
            continue
        tid = int(box.id[0])
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
        dets.append({
            "track_id": tid, "class_name": cls_name,
            "category": CATEGORY_MAP[cls_name],
            "bbox": [x1, y1, x2, y2], "center": center,
            "confidence": float(box.conf[0]),
            "state": classify_motion(tid, center, speed_thresh, track_history),
        })
    return dets