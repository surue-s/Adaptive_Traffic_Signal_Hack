"""Assign detections to drawn shapes, filter to annotated lanes, and count traffic."""

from typing import Any, Dict, List, Optional

from geometry.shapes import point_in_polygon, crossed_line


# ─────────────────────────────────────────────────────────────────────────────
# LANE FILTER — a vehicle only exists if it sits inside a drawn lane
# ─────────────────────────────────────────────────────────────────────────────

def filter_to_lanes(
    dets: List[Dict[str, Any]],
    shapes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Keep only vehicles whose center lies inside a manually drawn lane.

    - Vehicles inside a drawn lane  → kept, tagged in_lane=True.
    - Vehicles outside every lane   → dropped entirely (not shown, not counted).
    - Pedestrians                   → always kept (they are governed by crossings).
    - No lanes drawn yet            → whole-frame monitoring fallback so the
                                      system still works before annotation.
    """
    lane_polys = [s["points"] for s in shapes if s["label"] == "lane"]

    # Pre-annotation fallback: nothing drawn → monitor the whole frame.
    if not lane_polys:
        for d in dets:
            d["in_lane"] = d["category"] == "vehicle"
        return dets

    kept: List[Dict[str, Any]] = []
    for d in dets:
        if d["category"] != "vehicle":
            d["in_lane"] = False
            kept.append(d)
            continue

        if any(point_in_polygon(d["center"], poly) for poly in lane_polys):
            d["in_lane"] = True
            kept.append(d)
        # else: outside every drawn lane → excluded

    return kept


# ─────────────────────────────────────────────────────────────────────────────
# SHAPE ASSIGNMENT
# ─────────────────────────────────────────────────────────────────────────────

def assign_to_shapes(
    dets: List[Dict[str, Any]],
    shapes: List[Dict[str, Any]],
    track_history: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    """Tag each detection with the lane / crossing / count-line it falls in."""
    lanes = [s for s in shapes if s["label"] == "lane"]
    crossings = [s for s in shapes if s["label"] == "zebra_crossing"]
    count_lines = [s for s in shapes if s["label"] == "count_line"]

    for d in dets:
        d["lane_id"] = None
        d["in_crossing"] = False
        d["crossed_count_line"] = False

        # Lane assignment (point-in-polygon on center)
        for lane in lanes:
            if point_in_polygon(d["center"], lane["points"]):
                d["lane_id"] = lane["id"]
                break

        # Crossing assignment
        for cx in crossings:
            if point_in_polygon(d["center"], cx["points"]):
                d["in_crossing"] = True
                break

        # Count-line crossing (needs the previous position from track history)
        if track_history and d["track_id"] in track_history:
            hist = track_history[d["track_id"]]
            if len(hist) >= 2:
                prev, curr = hist[-2], hist[-1]
                for cl in count_lines:
                    if len(cl["points"]) == 2:
                        if crossed_line(prev, curr, cl["points"][0], cl["points"][1]):
                            d["crossed_count_line"] = True
                            break

    return dets


# ─────────────────────────────────────────────────────────────────────────────
# COUNTING
# ─────────────────────────────────────────────────────────────────────────────

def counts_for_direction(
    dets: List[Dict[str, Any]],
    shapes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Count vehicles (in-lane, incoming + focus) and pedestrians.

    Vehicles that did not survive filter_to_lanes are already gone, so every
    vehicle here is inside a drawn lane. Among those, only incoming + focus
    lanes feed the signal decision.
    """
    lanes_by_id = {s["id"]: s for s in shapes if s["label"] == "lane"}
    has_lanes = bool(lanes_by_id)

    vehicle_count = 0
    vehicles_straight = 0
    vehicles_left = 0
    vehicles_right = 0
    pedestrian_count = 0
    waiting_vehicles = 0
    waiting_pedestrians = 0
    crossing_pedestrians = 0
    count_line_crossings = 0

    for d in dets:
        if d["category"] == "vehicle":
            if not d.get("in_lane", False):
                continue

            if not has_lanes:
                # Whole-frame fallback (no lanes drawn)
                vehicle_count += 1
                vehicles_straight += 1
                if d["state"] == "waiting":
                    waiting_vehicles += 1
            else:
                lane = lanes_by_id.get(d["lane_id"])
                if lane and lane.get("travel") == "incoming" and lane.get("focus", True):
                    vehicle_count += 1
                    turn = lane.get("turn", "Straight")
                    if turn == "Straight":
                        vehicles_straight += 1
                    elif turn == "Left":
                        vehicles_left += 1
                    elif turn == "Right":
                        vehicles_right += 1
                        
                    if d["state"] == "waiting":
                        waiting_vehicles += 1

            if d.get("crossed_count_line"):
                count_line_crossings += 1

        elif d["category"] == "pedestrian":
            pedestrian_count += 1
            if d["state"] == "waiting":
                waiting_pedestrians += 1
            if d.get("in_crossing") and d["state"] == "moving":
                crossing_pedestrians += 1

    return {
        "vehicle": vehicle_count,
        "vehicles_straight": vehicles_straight,
        "vehicles_left": vehicles_left,
        "vehicles_right": vehicles_right,
        "pedestrian": pedestrian_count,
        "waiting_vehicles": waiting_vehicles,
        "waiting_pedestrians": waiting_pedestrians,
        "crossing_pedestrians": crossing_pedestrians,
        "count_line_crossings": count_line_crossings,
    }