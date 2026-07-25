"""Rule-based signal decision engine — per-direction signals with realistic phases.

Each of the four approaches (NORTH, SOUTH, EAST, WEST) owns its own signal head.
Exactly one direction is released at a time; every change sequences through
green → yellow → red before the next direction goes green.

Rules evaluated while green, in priority order:
  1. Starvation guard       — a direction waiting > MAX_WAIT is forced green.
  2. Max-hold rotate        — a direction green ≥ MAX_HOLD_TIME yields to the longest-waiting other.
  3. Low-traffic fast-track — a direction ≤ LOW_THRESHOLD with fewer vehicles clears first.
  4. Default demand         — switch only to a direction with strictly fewer vehicles.
A minimum green time (MIN_GREEN_TIME) stops counts from flipping the light too fast,
and pedestrian safety overrides any change (never cut off a crossing mid-walk).
"""

from typing import Any, Dict, List

from config.constants import DIRECTIONS, DIR_META

LOW_THRESHOLD   = 5
HIGH_THRESHOLD  = 15
MAX_HOLD_TIME   = 40
MAX_WAIT        = 90
MIN_GREEN_TIME  = 15   # a direction holds at least this long before counts may switch it
YELLOW_TIME     = 3    # seconds of amber between green and red
ALL_RED_TIME    = 3    # seconds of all-red clearance between direction switches



PHASES = {
    "ns_straight": ["north_straight", "south_straight"],
    "ns_turn": ["north_turn", "south_turn"],
    "ew_straight": ["east_straight", "west_straight"],
    "ew_turn": ["east_turn", "west_turn"]
}

def _get_phase_heads(phase: str) -> List[str]:
    return PHASES.get(phase, [])

def _label(d: str) -> str:
    if not d: return "—"
    if d == "ns_straight": return "NORTH & SOUTH (STRAIGHT)"
    if d == "ns_turn": return "NORTH & SOUTH (RIGHT TURN)"
    if d == "ew_straight": return "EAST & WEST (STRAIGHT)"
    if d == "ew_turn": return "EAST & WEST (RIGHT TURN)"
    
    parts = d.split("_")
    if len(parts) == 2:
        return f"{DIR_META.get(parts[0], {}).get('label', parts[0].upper())} ({parts[1].upper()})"
    return DIR_META.get(d, {}).get("label", str(d).upper())


def decide_green(counts: dict, wait_time: dict, current_green: str, green_held_for: float) -> str:
    starved = [p for p, w in wait_time.items() if w > MAX_WAIT]
    if starved:
        return max(starved, key=lambda p: wait_time[p])

    others = [p for p in counts if p != current_green]
    if not others:
        return current_green

    if green_held_for >= MAX_HOLD_TIME:
        return max(others, key=lambda p: wait_time.get(p, 0))

    low = [p for p in others if counts[p] <= LOW_THRESHOLD]
    if low:
        quietest = min(low, key=lambda p: counts[p])
        if counts[quietest] < counts.get(current_green, 0):
            return quietest

    fewest = min(others, key=lambda p: counts[p])
    if counts[fewest] < counts.get(current_green, 0):
        return fewest
    return current_green


def _which_rule(counts, wait_time, current_green, green_held_for, nxt):
    if nxt == current_green:
        return "HOLD", f"{_label(current_green)} retains green (heaviest or tied demand)"
    starved = [p for p, w in wait_time.items() if w > MAX_WAIT]
    if nxt in starved:
        return "STARVATION GUARD", f"{_label(nxt)} waited {wait_time[nxt]:.0f}s (> {MAX_WAIT}s) — forced green"
    if green_held_for >= MAX_HOLD_TIME:
        return "MAX HOLD ROTATE", f"{_label(current_green)} held {green_held_for:.0f}s — rotate to {_label(nxt)}"
    if counts.get(nxt, 0) <= LOW_THRESHOLD:
        return "LOW-TRAFFIC FAST-TRACK", f"{_label(nxt)} ≤ {LOW_THRESHOLD} vehicles — clear it first"
    return "DEMAND — CLEAR FASTEST", (
        f"{_label(nxt)} has fewer ({counts.get(nxt, 0)} vs {counts.get(current_green, 0)}) — goes first"
    )


class DecisionFlow:
    def __init__(self):
        self.current_phase = None
        self.phase = "green"          # "green" | "yellow" | "all_red"
        self.pending_phase = None
        self.yellow_timer = 0.0
        self.all_red_timer = 0.0
        self.green_held_for = 0.0
        self.phase_wait = {p: 0.0 for p in PHASES}
        self.decision_log: List[Dict[str, Any]] = []
        self.total_elapsed = 0.0
        self.last_rule = ""
        self.last_reason = ""

    def _signal_state(self, op_mode: str = "AUTO", manual_dir: str = "north") -> Dict[str, str]:
        heads = sum(PHASES.values(), [])
        if op_mode == "POWER_OUTAGE":
            return {h: "flashing_red" for h in heads}
        if op_mode == "NIGHT":
            return {h: "flashing_yellow" if h.startswith(("north", "south")) else "flashing_red" for h in heads}
        if op_mode == "MANUAL":
            return {h: "green" if h.startswith(manual_dir) else "red" for h in heads}

        state = {}
        active_heads = _get_phase_heads(self.current_phase) if self.current_phase else []
        for h in heads:
            if h in active_heads:
                if self.phase == "yellow":
                    state[h] = "yellow"
                elif self.phase == "all_red":
                    state[h] = "red"
                else:
                    state[h] = "green"
            else:
                state[h] = "red"
        return state

    def _begin_yellow(self, nxt, rule, reason):
        self.phase = "yellow"
        self.pending_phase = nxt
        self.yellow_timer = 0.0
        self.last_rule, self.last_reason = rule, reason
        self.decision_log.append({
            "time": round(self.total_elapsed, 1),
            "from": self.current_phase, "to": nxt, "rule": rule, "reason": reason,
        })
        self.decision_log = self.decision_log[-40:]

    def _complete_yellow(self):
        self.phase = "all_red"
        self.all_red_timer = 0.0

    def _complete_transition(self):
        self.current_phase = self.pending_phase
        self.phase = "green"
        self.pending_phase = None
        self.yellow_timer = 0.0
        self.all_red_timer = 0.0
        self.green_held_for = 0.0
        self.phase_wait[self.current_phase] = 0.0

    def _decide(self, phase_counts, crossing_dirs):
        if self.current_phase is None:
            first_phase = list(phase_counts.keys())[0] if phase_counts else "ns_straight"
            nxt = decide_green(phase_counts, self.phase_wait, first_phase, 0)
            self.current_phase = nxt
            self.green_held_for = 0.0
            self.phase_wait[nxt] = 0.0
            self.last_rule, self.last_reason = "INITIAL PHASE", f"opening with {_label(nxt)}"
            self.decision_log.append({
                "time": round(self.total_elapsed, 1), "from": None, "to": nxt,
                "rule": "INITIAL PHASE", "reason": f"opening with {_label(nxt)}",
            })
            return

        nxt = decide_green(phase_counts, self.phase_wait, self.current_phase, self.green_held_for)
        rule, reason = _which_rule(phase_counts, self.phase_wait, self.current_phase, self.green_held_for, nxt)
        forced = rule in ("STARVATION GUARD", "MAX HOLD ROTATE")

        if not forced and self.green_held_for < MIN_GREEN_TIME and nxt != self.current_phase:
            nxt = self.current_phase
            rule, reason = "MINIMUM GREEN", (
                f"{_label(self.current_phase)} within minimum green "
                f"({self.green_held_for:.0f}s < {MIN_GREEN_TIME}s) — hold"
            )

        if crossing_dirs and nxt != self.current_phase:
            nxt = self.current_phase
            rule, reason = "PEDESTRIAN HOLD", f"pedestrians crossing — hold green"

        if nxt != self.current_phase:
            self._begin_yellow(nxt, rule, reason)
        else:
            self.last_rule, self.last_reason = rule, reason

    def evaluate(self, counts_by_dir, dt, op_mode="AUTO", manual_dir="north", force=False):
        self.total_elapsed += dt
        
        active_dirs = list(counts_by_dir.keys())
        if not active_dirs:
            active_dirs = list(DIRECTIONS)
            
        active_phases = [p for p, heads in PHASES.items() if any(h.split("_")[0] in active_dirs for h in heads)]
        if self.current_phase and self.current_phase not in active_phases:
            self.current_phase = None

        crossing_dirs = set()
        head_counts = {}
        for d in active_dirs:
            ct = counts_by_dir.get(d, {})
            head_counts[f"{d}_straight"] = ct.get("vehicles_straight", 0) + ct.get("vehicles_left", 0)
            head_counts[f"{d}_turn"] = ct.get("vehicles_right", 0)
            if ct.get("crossing_pedestrians", 0) > 0:
                crossing_dirs.add(d)
                
        phase_counts = {}
        for phase in active_phases:
            heads = PHASES[phase]
            phase_counts[phase] = sum(head_counts.get(h, 0) for h in heads if h.split("_")[0] in active_dirs)

        if op_mode == "MANUAL":
            self.last_rule = "MANUAL OVERRIDE"
            self.last_reason = f"Traffic police forced {_label(manual_dir)} to green"
            for p in active_phases:
                self.phase_wait[p] = self.phase_wait.get(p, 0.0) + dt
        elif op_mode in ("NIGHT", "POWER_OUTAGE"):
            for p in active_phases:
                self.phase_wait[p] = self.phase_wait.get(p, 0.0) + dt
        else:
            for p in active_phases:
                if p == self.current_phase:
                    self.phase_wait[p] = 0.0
                else:
                    self.phase_wait[p] = self.phase_wait.get(p, 0.0) + dt

            if self.phase == "yellow":
                self.yellow_timer += dt
                if self.yellow_timer >= YELLOW_TIME:
                    self._complete_yellow()
            elif self.phase == "all_red":
                self.all_red_timer += dt
                if self.all_red_timer >= ALL_RED_TIME:
                    self._complete_transition()
            else:
                self.green_held_for += dt
                self._decide(phase_counts, crossing_dirs)

        signal_state = self._signal_state(op_mode, manual_dir)
        starved = [p for p in active_phases if self.phase_wait.get(p, 0.0) > MAX_WAIT]
        congested = [p for p, c in phase_counts.items() if c >= HIGH_THRESHOLD]

        steps = [
            {"name": "VEHICLE COUNTS", "detail": dict(phase_counts)},
            {"name": "CONGESTION", "alert": bool(congested),
             "detail": ", ".join(_label(p) for p in congested) if congested else "normal flow"},
            {"name": "STARVATION", "alert": bool(starved),
             "detail": {p: round(self.phase_wait.get(p, 0.0), 1) for p in active_phases}},
            {"name": "PEDESTRIANS", "alert": bool(crossing_dirs),
             "detail": ", ".join(_label(d) for d in crossing_dirs) if crossing_dirs else "none crossing"},
            {"name": "PHASE", "alert": self.phase in ("yellow", "all_red"),
             "detail": (f"{_label(self.current_phase)} YELLOW → {_label(self.pending_phase)}" if self.phase == "yellow"
                        else f"ALL-RED CLEARANCE → {_label(self.pending_phase)}" if self.phase == "all_red"
                        else f"{_label(self.current_phase)} GREEN")},
            {"name": "DECISION", "detail": {"dir": self.current_phase,
                                            "rule": self.last_rule, "reason": self.last_reason}},
            {"name": "SIGNAL STATE", "detail": signal_state},
        ]

        return {
            "steps": steps,
            "signal_state": signal_state,
            "current_dir": self.current_phase,
            "phase": self.phase,
            "pending_dir": self.pending_phase,
            "green_held_for": self.green_held_for,
            "yellow_timer": self.yellow_timer,
            "all_red_timer": self.all_red_timer,
            "hold_remaining": max(0.0, MAX_HOLD_TIME - self.green_held_for),
            "dir_counts": phase_counts,
            "dir_wait": dict(self.phase_wait),
            "last_rule": self.last_rule,
            "last_reason": self.last_reason,
            "decision_log": list(self.decision_log),
        }