"""Model-assisted annotation — draft lane polygons from vehicle detections.

Runs the detection model on the uploaded frame, clusters detected vehicles into
lane bands, and returns suggested lane polygons as a starting point. Refine
them with the vertex editor, then export the layout for reuse.
"""

from collections import defaultdict, deque
from typing import List

import numpy as np

from models.detector import load_model_fresh, run_tracking


def auto_suggest_lanes(frame: np.ndarray, model_name: str = "AUTA_Aerial_N_Rapid.pt",
                       orientation: str = "vertical", min_vehicles: int = 2) -> List[List[tuple]]:
    """Detect vehicles and cluster them into lane band polygons.

    orientation: "vertical"   → lanes run top↕bottom, clustered by x
                 "horizontal" → lanes run left↔right, clustered by y
    Returns polygons in original frame coordinates.
    """
    h, w = frame.shape[:2]
    model = load_model_fresh(model_name)
    track_history = defaultdict(lambda: deque(maxlen=15))
    dets = run_tracking(frame, model, track_history, conf=0.20, imgsz=640,
                        speed_thresh=3.0, tracker="bytetrack.yaml")
    vehicles = [d for d in dets if d["category"] == "vehicle"]
    if len(vehicles) < min_vehicles:
        return []

    if orientation == "vertical":
        key = lambda d: d["center"][0]
        span = lambda d: (d["bbox"][0], d["bbox"][2])   # left, right
    else:
        key = lambda d: d["center"][1]
        span = lambda d: (d["bbox"][1], d["bbox"][3])   # top, bottom

    vehicles.sort(key=key)

    # Cluster gap derived from the median vehicle size
    sizes = [span(d)[1] - span(d)[0] for d in vehicles]
    median_size = float(np.median(sizes)) if sizes else 40.0
    gap = median_size * 1.8

    clusters = [[vehicles[0]]]
    for v in vehicles[1:]:
        if key(v) - key(clusters[-1][-1]) <= gap:
            clusters[-1].append(v)
        else:
            clusters.append([v])

    polys, pad = [], median_size * 0.5
    for cl in clusters:
        if len(cl) < min_vehicles:
            continue
        lo = min(span(d)[0] for d in cl) - pad
        hi = max(span(d)[1] for d in cl) + pad
        if orientation == "vertical":
            polys.append([(lo, 0), (hi, 0), (hi, h), (lo, h)])
        else:
            polys.append([(0, lo), (w, lo), (w, hi), (0, hi)])
    return polys