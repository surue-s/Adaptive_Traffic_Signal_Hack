"""Control Room — real-time MJPEG live tracking dashboard.

Layout: control rail (left) · monitor wall (center) · decision telemetry (right).
Feeds use object-fit:contain so the entire frame is always visible.
"""

from engine.decision_flow import DecisionFlow, MAX_HOLD_TIME, YELLOW_TIME, MIN_GREEN_TIME

import time

import streamlit as st

from config.constants import DIRECTIONS, DIR_META
from engine.decision_flow import DecisionFlow, MAX_HOLD_TIME, YELLOW_TIME, MIN_GREEN_TIME, ALL_RED_TIME, PHASES
from theme.tokens import C, F_DISPLAY, F_BODY
from ui.traffic_light import traffic_light_html
from video import live_stream as ls
from video.sources import ImageSource, VideoSource, CameraSource

MODE_LABEL = {"image": "STILL IMAGE", "video": "MOTION PICTURE", "live": "LIVE APPARATUS"}
DOCK_HEIGHT = {"2 × 2": 40, "1 × 4": 40, "4 × 1": 19}
MODEL_LABELS = {
    "AUTA_Aerial_N_Rapid.pt": "AUTA-Aerial N · Rapid",
    "AUTA_Aerial_S_Balanced.pt": "AUTA-Aerial S · Balanced",
    "AUTA_Aerial_N_v2_Swift.pt": "AUTA-Aerial N v2 · Swift",
    "AUTA_Aerial_S_v2_Precise.pt": "AUTA-Aerial S v2 · Precise",
}
TRACKER_LABELS = {"botsort.yaml": "BoT-SORT · STABLE", "bytetrack.yaml": "ByteTrack · RAPID"}



def _inject_dashboard_css() -> None:
    st.markdown(
        f"""
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Josefin+Sans:wght@300;400;600&family=Marcellus&display=swap');

          div[data-testid="stButton"] button, .stButton > button {{
              border-radius: 0px !important;
              border: 1px solid {C['border-h']} !important;
              background: transparent !important;
              color: {C['gold']} !important;
              font-family: {F_DISPLAY} !important;
              font-weight: 400 !important;
              letter-spacing: 0.15em !important;
              text-transform: uppercase !important;
              transition: all 0.4s ease;
              min-height: 44px;
          }}
          div[data-testid="stButton"] button:hover {{
              background: {C['gold']} !important;
              color: {C['bg']} !important;
              box-shadow: 0 0 15px rgba(212, 175, 55, 0.4) !important;
              transform: translateY(-2px);
          }}
          div[data-testid="stButton"] button[kind="primary"] {{
              background: rgba(212, 175, 55, 0.12) !important;
              border: 2px solid {C['gold']} !important;
              color: {C['gold-light']} !important;
          }}
          div[data-testid="stButton"] button[kind="primary"]:hover {{
              background: {C['gold']} !important;
              color: {C['bg']} !important;
              box-shadow: 0 0 22px rgba(212, 175, 55, 0.6) !important;
          }}

          div[data-testid="stRadio"] label, div[data-testid="stSelectbox"] label,
          div[data-testid="stSlider"] label, div[data-testid="stNumberInput"] label {{
              font-family: {F_BODY} !important;
              font-size: 11px !important;
              letter-spacing: 0.12em !important;
              text-transform: uppercase !important;
              color: {C['text-dim']} !important;
          }}
          .stSelectbox div[data-baseweb="select"], .stNumberInput input {{
              background-color: transparent !important;
              border: none !important;
              border-bottom: 2px solid {C['border-h']} !important;
              border-radius: 0px !important;
              color: {C['text']} !important;
              font-family: {F_BODY} !important;
              box-shadow: none !important;
          }}

          /* side rails */
          .ss-rail {{ height: calc(100vh - 130px); overflow-y: auto; padding-right: 4px; }}
          .ss-rail-card {{
              background: {C['surface']}; border: 1px solid {C['border']};
              border-radius: 0px; padding: 14px 16px; margin-bottom: 14px;
              transition: border-color 0.4s ease;
          }}
          .ss-rail-card:hover {{ border-color: {C['border-h']}; }}

          /* monitor docks */
          .ss-card {{
              background: {C['surface']}; border: 1px solid {C['border']};
              border-radius: 0px; padding: 16px; margin-bottom: 16px;
              transition: all 0.4s ease; position: relative;
          }}
          .ss-card:hover {{
              border-color: {C['border-h']};
              box-shadow: 0 5px 20px rgba(212, 175, 55, 0.12);
          }}

          ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
          ::-webkit-scrollbar-track {{ background: {C['bg']}; border-left: 1px solid {C['border']}; }}
          ::-webkit-scrollbar-thumb {{ background: {C['border-h']}; border-radius: 0px; }}
          @keyframes ss-flash {{ 0% {{ opacity: 1; }} 100% {{ opacity: 0.3; }} }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _rail_header(label: str) -> None:
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:9px;margin-bottom:12px;'
        f'border-bottom:1px solid {C["border"]};padding-bottom:7px;">'
        f'<span style="width:6px;height:6px;transform:rotate(45deg);background:{C["gold"]};flex:none;"></span>'
        f'<span style="font-family:{F_DISPLAY};font-size:13px;letter-spacing:0.18em;'
        f'text-transform:uppercase;color:{C["gold"]};">{label}</span></div>',
        unsafe_allow_html=True,
    )


def _live_dock(direction: str, port: int, h_vh: int, rotation: int = 0) -> str:
    """A camera monitor: full frame visible (contain), viewfinder corner brackets."""
    meta = DIR_META[direction]
    url = f"http://127.0.0.1:{port}/video?dir={direction}"
    bracket = f"width:16px;height:16px;position:absolute;"
    return (
        f'<div class="ss-dock" style="height:{h_vh}vh;position:relative;border-radius:0px;overflow:hidden;'
        f'border:1px solid {C["border-h"]};background:#000;'
        f'box-shadow:0 0 0 1px rgba(212,175,55,0.12), 0 10px 28px rgba(0,0,0,0.65);">'
        f'<img src="{url}" style="width:100%;height:100%;object-fit:contain;display:block;background:#000;transform:rotate({rotation}deg);"/>'
        # top OSD strip
        f'<div style="position:absolute;top:0;left:0;right:0;display:flex;align-items:center;'
        f'justify-content:space-between;padding:7px 14px;pointer-events:none;'
        f'background:linear-gradient(180deg,rgba(10,10,10,0.92),rgba(10,10,10,0));">'
        f'<div style="display:flex;align-items:center;gap:9px;">'
        f'<span style="width:7px;height:7px;transform:rotate(45deg);background:{C["gold"]};'
        f'box-shadow:0 0 8px {C["gold"]};animation:pulse 2s infinite;"></span>'
        f'<span style="font-family:{F_DISPLAY};font-size:13px;letter-spacing:0.2em;color:{C["gold"]};">'
        f'{meta["arrow"]} {direction.upper()}</span></div>'
        f'<span style="font-family:{F_BODY};font-size:9px;letter-spacing:0.24em;color:{C["text-dim"]};'
        f'text-transform:uppercase;">LIVE</span></div>'
        # viewfinder corner brackets
        f'<div style="{bracket}top:0;left:0;border-top:2px solid {C["gold"]};border-left:2px solid {C["gold"]};"></div>'
        f'<div style="{bracket}top:0;right:0;border-top:2px solid {C["gold"]};border-right:2px solid {C["gold"]};"></div>'
        f'<div style="{bracket}bottom:0;left:0;border-bottom:2px solid {C["gold"]};border-left:2px solid {C["gold"]};"></div>'
        f'<div style="{bracket}bottom:0;right:0;border-bottom:2px solid {C["gold"]};border-right:2px solid {C["gold"]};"></div>'
        f'</div>'
    )


def _idle_dock(direction: str, h_vh: int) -> str:
    meta = DIR_META[direction]
    return (
        f'<div class="ss-dock" style="height:{h_vh}vh;border-radius:0px;position:relative;'
        f'display:flex;align-items:center;justify-content:center;background:#050505;'
        f'border:1px dashed {C["border-h"]};">'
        f'<div style="text-align:center;">'
        f'<div style="font-family:{F_DISPLAY};font-size:26px;color:{C["gold"]};opacity:0.35;">{meta["arrow"]}</div>'
        f'<div style="font-family:{F_DISPLAY};font-size:13px;letter-spacing:0.22em;color:{C["gold"]};'
        f'opacity:0.55;margin-top:8px;">{direction.upper()} · AWAITING SIGNAL</div></div></div>'
    )


def _card_title(label: str) -> str:
    return (
        f'<div class="ss-card-title" style="display:flex;align-items:center;gap:10px;'
        f'font-family:{F_DISPLAY};font-size:14px;font-weight:400;letter-spacing:0.15em;'
        f'text-transform:uppercase;color:{C["gold"]};margin-bottom:12px;border-bottom:1px solid {C["border"]};padding-bottom:6px;">'
        f'<span style="width:6px;height:6px;transform:rotate(45deg);background:{C["gold"]};"></span>{label}</div>'
    )


def _empty(msg: str) -> str:
    return (
        f'<div style="font-family:{F_BODY};font-size:11px;color:{C["text-faint"]};'
        f'letter-spacing:0.08em;text-transform:uppercase;padding:6px 0;">{msg}</div>'
    )

def _label(d):
    if not d: return "—"
    if "-" in d: return d.replace("-", " & ").upper()
    return DIR_META.get(d, {}).get("label", str(d).upper())
def _decision_rail(result, counts_by_dir=None) -> str:
    dec = result["decision"] if "decision" in result else result
    cur = dec.get("current_dir")
    phase = dec.get("phase", "green")
    pending = dec.get("pending_dir")
    held = dec.get("green_held_for", 0.0)
    yellow_timer = dec.get("yellow_timer", 0.0)
    dir_counts = dec.get("dir_counts", {})
    dir_wait = dec.get("dir_wait", {})
    signal_state = dec.get("signal_state", {})

    is_yellow = phase == "yellow"
    is_all_red = phase == "all_red"
    if is_yellow:
        light_state = "yellow"
    elif is_all_red:
        light_state = "red"
    else:
        light_state = "green"
        
    op_mode = st.session_state.get("op_mode", "AUTO")
    if op_mode == "POWER_OUTAGE":
        light_state = "flashing_red"
    
    light = traffic_light_html(light_state, scale=1.15)

    if op_mode == "POWER_OUTAGE":
        title = f'SYSTEM OFFLINE'
        title_color = C["ruby"]
        subtitle = f'POWER OUTAGE · 4-WAY FLASHING RED'
        bar_pct = 100
        bar_color = C["ruby"]
    elif op_mode == "NIGHT":
        title = f'NIGHT MODE'
        title_color = C["topaz"]
        subtitle = f'FLASHING AMBER (MAIN) / RED (MINOR)'
        bar_pct = 100
        bar_color = C["topaz"]
    elif is_yellow:
        yellow_remaining = max(0.0, YELLOW_TIME - yellow_timer)
        title = f'{DIR_META.get(cur, {}).get("arrow", "")} {_label(cur)} · CLEARING'
        title_color = C["topaz"]
        subtitle = f'CHANGING TO {_label(pending)} · {yellow_remaining:.0f}s'
        bar_pct = min(yellow_timer / YELLOW_TIME, 1.0) * 100
        bar_color = C["topaz"]
    elif is_all_red:
        all_red_timer = dec.get("all_red_timer", 0.0)
        red_remaining = max(0.0, ALL_RED_TIME - all_red_timer)
        title = f'ALL-RED CLEARANCE'
        title_color = C["ruby"]
        subtitle = f'CHANGING TO {_label(pending)} · {red_remaining:.0f}s'
        bar_pct = min(all_red_timer / ALL_RED_TIME, 1.0) * 100
        bar_color = C["ruby"]
    else:
        held_disp = min(held, MAX_HOLD_TIME)
        title = f'{DIR_META.get(cur, {}).get("arrow", "")} {_label(cur)}'
        title_color = C["emerald"]
        subtitle = f'FLOW ENABLED · {held_disp:.0f}s / {MAX_HOLD_TIME}s'
        bar_pct = min(held / MAX_HOLD_TIME, 1.0) * 100
        bar_color = C["emerald"]

    active = (
        f'<div class="ss-card ss-card-active">{_card_title("Active Phase")}'
        f'<div style="display:flex;align-items:center;gap:16px;">{light}'
        f'<div style="flex:1;">'
        f'<div style="font-family:{F_DISPLAY};font-size:20px;letter-spacing:0.07em;color:{title_color};">{title}</div>'
        f'<div style="font-family:{F_BODY};font-size:10px;color:{C["text-dim"]};margin-top:4px;letter-spacing:0.1em;text-transform:uppercase;">'
        f'{subtitle}</div></div></div>'
        f'<div style="margin-top:14px;height:4px;background:{C["bg"]};overflow:hidden;'
        f'border:1px solid {C["border"]};"><div style="width:{bar_pct:.0f}%;height:100%;background:{bar_color};'
        f'transition:width .3s;"></div></div>'
        f'<div style="margin-top:12px;font-size:10px;color:{C["text-dim"]};font-family:{F_BODY};letter-spacing:0.05em;text-transform:uppercase;">'
        f'<span style="color:{C["gold"]};">{dec.get("last_rule", "")}</span><br/>'
        f'{dec.get("last_reason", "")}</div></div>'
    )

    # ── Signal heads — 8 phases ────────────────────────────────
    sig_rows = ""
    heads = ["north_straight", "north_turn", "south_straight", "south_turn",
             "east_straight", "east_turn", "west_straight", "west_turn"]
    for h in heads:
        d, t = h.split("_")
        meta = DIR_META[d]
        label = f"{meta['label']} {'(STR & LFT)' if t == 'straight' else '(R-TURN)'}"
        state = signal_state.get(h, "red")
        is_next = pending and h in PHASES.get(pending, [])
        if state == "green":
            pill = f'<span style="color:{C["emerald"]};font-family:{F_DISPLAY};font-size:11px;letter-spacing:0.1em;">START</span>'
            edge = f"border-left:3px solid {C['emerald']};"
            dim = ""
        elif state == "yellow":
            pill = f'<span style="color:{C["topaz"]};font-family:{F_DISPLAY};font-size:11px;letter-spacing:0.1em;">WAIT</span>'
            edge = f"border-left:3px solid {C['topaz']};"
            dim = ""
        elif state == "flashing_red":
            pill = f'<span style="color:{C["ruby"]};font-family:{F_DISPLAY};font-size:11px;letter-spacing:0.1em;animation:ss-flash 1s infinite alternate;">FLASH STOP</span>'
            edge = f"border-left:3px solid {C['ruby']};"
            dim = ""
        elif state == "flashing_yellow":
            pill = f'<span style="color:{C["topaz"]};font-family:{F_DISPLAY};font-size:11px;letter-spacing:0.1em;animation:ss-flash 1s infinite alternate;">FLASH WAIT</span>'
            edge = f"border-left:3px solid {C['topaz']};"
            dim = ""
        elif is_next:
            pill = f'<span style="color:{C["gold"]};font-family:{F_DISPLAY};font-size:11px;letter-spacing:0.1em;">NEXT</span>'
            edge = f"border-left:3px dashed {C['gold']};"
            dim = ""
        else:
            pill = f'<span style="color:{C["ruby"]};font-family:{F_DISPLAY};font-size:11px;letter-spacing:0.1em;">STOP</span>'
            edge = f"border-left:3px solid {C['ruby']};"
            dim = "opacity:.65;"
            
        light_icon = traffic_light_html(state if state else "red", scale=0.35, horizontal=True)
            
        sig_rows += (
            f'<div style="display:flex;align-items:center;justify-content:space-between;'
            f'padding:6px 12px;margin:4px 0;background:{C["bg"]};{edge}{dim}">'
            f'<div style="display:flex;align-items:center;gap:12px;">'
            f'{light_icon}'
            f'<span style="font-family:{F_DISPLAY};font-size:11px;letter-spacing:0.12em;color:{C["text"]};">'
            f'{meta["arrow"]}&nbsp; {label}</span></div>{pill}</div>'
        )
    signal_card = (
        f'<div class="ss-card">{_card_title("Signal Heads")}{sig_rows}'
        f'<div style="font-size:9px;font-family:{F_BODY};color:{C["text-faint"]};margin-top:10px;line-height:1.6;text-transform:uppercase;letter-spacing:0.05em;">'
        f'One phase released at a time · amber {YELLOW_TIME}s between phases.</div></div>'
    )

    # ── Volume per approach ───────────────────────────────────────────────
    max_c = max([cd.get("vehicle", 0) for cd in counts_by_dir.values()]) if counts_by_dir else 1
    bars = ""
    for d in ("north", "east", "south", "west"):
        c = counts_by_dir.get(d, {}).get("vehicle", 0) if counts_by_dir else 0
        pct = int(c / max_c * 100) if max_c else 0
        
        turn_html = ""
        if counts_by_dir and d in counts_by_dir:
            ct = counts_by_dir[d]
            s = ct.get("vehicles_straight", 0)
            l = ct.get("vehicles_left", 0)
            r = ct.get("vehicles_right", 0)
            if s > 0 or l > 0 or r > 0:
                turn_html = (
                    f'<div style="font-family:{F_BODY};font-size:9px;color:{C["text-faint"]};margin-top:4px;'
                    f'letter-spacing:0.1em;display:flex;gap:8px;">'
                    f'<span>↑ {s}</span><span>← {l}</span><span>→ {r}</span></div>'
                )
                
        bars += (
            f'<div style="display:flex;align-items:center;gap:12px;margin:10px 0;">'
            f'<span style="width:24px;font-family:{F_DISPLAY};font-size:14px;color:{C["gold"]};">{DIR_META[d]["arrow"]}</span>'
            f'<div style="flex:1;">'
            f'<div style="height:4px;background:{C["bg"]};border:1px solid {C["border"]};">'
            f'<div style="width:{pct}%;height:100%;background:{C["gold"]};transition:width .4s ease-out;"></div></div>'
            f'{turn_html}</div>'
            f'<span style="width:30px;text-align:right;font-family:{F_BODY};font-size:14px;color:{C["text"]};">{c}</span></div>'
        )
    load_card = f'<div class="ss-card">{_card_title("Volume Tracking")}{bars}</div>'

    # ── Delay per approach ────────────────────────────────────────────────
    wcells = ""
    for p in ("ns_straight", "ns_turn", "ew_straight", "ew_turn"):
        w = dir_wait.get(p, 0.0)
        alert = w > 90
        b_color = C["gold"] if alert else C["border"]
        t_color = C["gold-light"] if alert else C["text-dim"]
        p_label = "N-S STR" if p == "ns_straight" else "N-S TRN" if p == "ns_turn" else "E-W STR" if p == "ew_straight" else "E-W TRN"
        wcells += (f'<div style="flex:1;text-align:center;padding:10px 4px;background:{C["bg"]};'
                   f'border:1px solid {b_color};"><div style="font-family:{F_DISPLAY};font-size:10px;color:{C["text-faint"]};">{p_label}</div>'
                   f'<div style="font-family:{F_BODY};font-size:16px;margin-top:3px;color:{t_color};">{w:.0f}s</div></div>')
    wait_card = (f'<div class="ss-card">{_card_title("Delay Metrics")}'
                 f'<div style="font-family:{F_BODY};font-size:9px;color:{C["text-faint"]};margin-bottom:10px;text-transform:uppercase;letter-spacing:0.1em;">STARVATION &gt; 90s</div>'
                 f'<div style="display:flex;gap:8px;">{wcells}</div></div>')

    # ── Logic chain ───────────────────────────────────────────────────────
    chain = ""
    row_style = (f'font-family:{F_BODY};font-size:10px;margin-bottom:6px;border-bottom:1px solid '
                 f'rgba(154,123,30,0.15);padding-bottom:4px;text-transform:uppercase;letter-spacing:0.05em;')
    for step in dec["steps"]:
        name = step["name"]
        if name == "DECISION":
            chain += (f'<div style="{row_style}"><span style="color:{C["text-dim"]};">DECISION →</span> '
                      f'<b style="color:{C["gold-light"]};">{_label(step["detail"]["dir"])}</b> '
                      f'· <span style="color:{C["text"]};">{step["detail"]["rule"]}</span></div>')
        elif name == "PHASE" and step.get("alert"):
            chain += (f'<div style="{row_style}"><span style="color:{C["text-dim"]};">PHASE →</span> '
                      f'<b style="color:{C["topaz"]};">{step["detail"]}</b></div>')
        elif step.get("alert") and name in ("CONGESTION", "STARVATION", "PEDESTRIANS"):
            color = {"CONGESTION": C["topaz"], "STARVATION": C["ruby"], "PEDESTRIANS": C["gold"]}[name]
            chain += (f'<div style="{row_style}"><span style="color:{C["text-dim"]};">{name} →</span> '
                      f'<b style="color:{color};">{step["detail"]}</b></div>')
    chain_card = f'<div class="ss-card">{_card_title("Logic Chain")}{chain or _empty("Awaiting directives")}</div>'

    # ── Audit ledger ──────────────────────────────────────────────────────
    log = ""
    for e in reversed(dec["decision_log"][-6:]):
        log += (f'<div style="font-family:{F_BODY};font-size:10px;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.05em;">'
                f'<span style="color:{C["text-faint"]};">[{e["time"]:.0f}s]</span> '
                f'<b style="color:{C["gold"]};">{_label(e["to"])}</b> '
                f'<span style="color:{C["text-dim"]};">← {e["rule"]}</span></div>')
    log_card = f'<div class="ss-card">{_card_title("Audit Ledger")}{log or _empty("No entries found")}</div>'

    rules = (f'<div class="ss-card">{_card_title("Operational Mandates")}'
             f'<div style="font-family:{F_BODY};font-size:10px;color:{C["gold"]};text-transform:uppercase;letter-spacing:0.1em;text-align:center;padding:10px;border:1px solid {C["border"]};">'
             f'LOW ≤ 5 · HIGH ≥ 15<br><br>MIN GREEN {MIN_GREEN_TIME}s · HOLD {MAX_HOLD_TIME}s<br><br>AMBER {YELLOW_TIME}s · STARVE 90s</div></div>')

    return (f'<div class="ss-rail">{active}{signal_card}{load_card}{wait_card}'
            f'{chain_card}{log_card}{rules}</div>')

def _get_flow() -> DecisionFlow:
    if "decision_flow" not in st.session_state:
        st.session_state.decision_flow = DecisionFlow()
    return st.session_state.decision_flow


@st.fragment(run_every=0.5)
def decision_panel(dirs):
    with ls.shared.lock:
        counts_by_dir = {d: dict(ls.shared.counts[d]) for d in dirs if d in ls.shared.counts}
    if not counts_by_dir:
        st.markdown(
            f'<div class="ss-card" style="text-align:center;padding:30px 10px;border:1px dashed {C["border-h"]};">'
            f'<div style="font-family:{F_DISPLAY};font-size:13px;letter-spacing:0.2em;'
            f'color:{C["gold"]};opacity:0.6;">AWAITING SENSOR INPUT…</div></div>',
            unsafe_allow_html=True,
        )
        return

    now = time.time()
    last = st.session_state.get("_last_decision_t", now)
    dt = max(now - last, 0.05)
    st.session_state._last_decision_t = now

    op_mode = st.session_state.get("op_mode", "AUTO")
    manual_dir = st.session_state.get("manual_dir", "north")
    result = _get_flow().evaluate(counts_by_dir, dt, op_mode=op_mode, manual_dir=manual_dir)

    with ls.shared.lock:
        for d, s in result["signal_state"].items():
            ls.shared.signal[d] = s
        ls.shared.decision_result = result   # banner reads this

    st.markdown(_decision_rail(result, counts_by_dir), unsafe_allow_html=True)

@st.fragment(run_every=0.5)
def decision_banner(dirs):
    """Large, always-visible verdict strip above the monitor wall."""
    with ls.shared.lock:
        result = ls.shared.decision_result
    if result is None:
        st.markdown(
            f'<div style="background:{C["surface"]};border:1px solid {C["border"]};border-left:5px solid {C["gold"]};'
            f'padding:16px 20px;margin-bottom:14px;text-align:center;">'
            f'<div style="font-family:{F_DISPLAY};font-size:18px;letter-spacing:0.2em;color:{C["gold"]};">'
            f'AWAITING FIRST DECISION</div>'
            f'<div style="font-family:{F_BODY};font-size:10px;color:{C["text-dim"]};margin-top:5px;'
            f'letter-spacing:0.14em;text-transform:uppercase;">Initiate to begin live signal control</div></div>',
            unsafe_allow_html=True,
        )
        return

    dec = result["decision"] if "decision" in result else result
    cur = dec.get("current_dir")
    phase = dec.get("phase", "green")
    pending = dec.get("pending_dir")
    held = dec.get("green_held_for", 0.0)
    yellow_timer = dec.get("yellow_timer", 0.0)
    meta = DIR_META.get(cur, {})

    op_mode = st.session_state.get("op_mode", "AUTO")
    if op_mode == "POWER_OUTAGE":
        accent = C["ruby"]
        headline = f'SYSTEM OFFLINE'
        sub = f'POWER OUTAGE · ALL DIRECTIONS FLASHING RED'
        pct = 100
        big = f'PWR'
    elif op_mode == "NIGHT":
        accent = C["topaz"]
        headline = f'NIGHT MODE'
        sub = f'CAUTION · MAIN AMBER / MINOR RED'
        pct = 100
        big = f'NTE'
    elif phase == "yellow":
        remaining = max(0.0, YELLOW_TIME - yellow_timer)
        accent = C["topaz"]
        headline = f'{meta.get("arrow","")} {meta.get("label","").upper()} — CLEARING'
        sub = f'AMBER · CHANGING TO {DIR_META.get(pending, {}).get("label","").upper()} · {remaining:.0f}s'
        pct = min(yellow_timer / YELLOW_TIME, 1.0) * 100
        big = f'{remaining:.0f}s'
    elif phase == "all_red":
        all_red_timer = dec.get("all_red_timer", 0.0)
        remaining = max(0.0, ALL_RED_TIME - all_red_timer)
        accent = C["ruby"]
        headline = f'ALL-RED CLEARANCE'
        sub = f'CHANGING TO {DIR_META.get(pending, {}).get("label","").upper()} · {remaining:.0f}s'
        pct = min(all_red_timer / ALL_RED_TIME, 1.0) * 100
        big = f'{remaining:.0f}s'
    else:
        remaining = max(0.0, MAX_HOLD_TIME - held)
        accent = C["emerald"]
        headline = f'{meta.get("arrow","")} {meta.get("label","").upper()} — FLOW ENABLED'
        sub = f'{dec.get("last_rule","")} · HELD {min(held, MAX_HOLD_TIME):.0f}s / {MAX_HOLD_TIME}s'
        pct = min(held / MAX_HOLD_TIME, 1.0) * 100
        big = f'{remaining:.0f}s'

    st.markdown(
        f'<div style="background:{C["surface"]};border:1px solid {C["border"]};border-left:6px solid {accent};'
        f'padding:14px 22px;margin-bottom:14px;box-shadow:0 4px 18px rgba(42,35,20,0.10);">'
        f'<div style="display:flex;align-items:center;justify-content:space-between;gap:18px;">'
        f'<div style="min-width:0;">'
        f'<div style="font-family:{F_DISPLAY};font-size:27px;letter-spacing:0.07em;color:{accent};white-space:nowrap;">{headline}</div>'
        f'<div style="font-family:{F_BODY};font-size:11px;color:{C["text-dim"]};margin-top:5px;'
        f'letter-spacing:0.12em;text-transform:uppercase;">{sub}</div></div>'
        f'<div style="font-family:{F_DISPLAY};font-size:38px;color:{accent};flex:none;line-height:1;">{big}</div>'
        f'</div>'
        f'<div style="margin-top:11px;height:5px;background:{C["bg"]};border:1px solid {C["border"]};overflow:hidden;">'
        f'<div style="width:{pct:.0f}%;height:100%;background:{accent};transition:width .3s;"></div></div></div>',
        unsafe_allow_html=True,
    )

def _make_source(direction: str, mode: str):
    cfg = st.session_state.config[direction]
    if mode == "image" and cfg["frame"] is not None:
        return ImageSource(cfg["frame"])
    if mode == "video" and cfg["media_bytes"]:
        return VideoSource(cfg["media_bytes"])
    if mode == "live":
        return CameraSource(st.session_state.get(f"cam_index_{direction}", 0))
    return None


def control_room() -> None:
    _inject_dashboard_css()
    active = st.session_state.get("active_directions", list(DIRECTIONS))

    # ── slim command header ───────────────────────────────────────────────
    st.markdown(
        f'''
        <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 18px;margin-bottom:14px;
                    background:{C["surface"]};border:1px solid {C["border"]};border-left:3px solid {C["gold"]};">
          <div style="display:flex;align-items:center;gap:14px;">
            <div style="width:12px;height:12px;transform:rotate(45deg);border:2px solid {C["gold"]};
                        box-shadow:0 0 12px {C["gold"]};animation:pulse 2s infinite;flex:none;"></div>
            <div style="font-family:{F_DISPLAY};font-size:20px;letter-spacing:0.26em;color:{C["gold"]};">CONTROL ROOM</div>
          </div>
          <div style="font-family:{F_BODY};font-size:10px;color:{C["text-dim"]};letter-spacing:0.2em;text-transform:uppercase;">
            Adaptive Signal Operations
          </div>
        </div>
        <style>@keyframes pulse{{0%,100%{{opacity:1;box-shadow:0 0 12px {C["gold"]};}}50%{{opacity:.4;box-shadow:0 0 4px {C["gold"]};}}}}</style>
        ''',
        unsafe_allow_html=True,
    )

    # ── three-zone console: controls │ monitor wall │ telemetry ───────────
    left_col, center_col, right_col = st.columns([21, 58, 21], gap="small")

    # ══ LEFT RAIL — CONTROLS ══
    with left_col:
        with st.container(border=True):
            _rail_header("Detection Array")
            model_name = st.selectbox("AUTA Detection Model", list(MODEL_LABELS),
                                      format_func=MODEL_LABELS.get, key="model_name")
            tracker_name = "botsort.yaml"
            det_conf = st.slider("Precision Threshold", 0.10, 0.70, 0.25, 0.05, key="det_conf")
            imgsz = st.selectbox("Inference Resolution", [416, 640, 960], index=0, key="imgsz")
        current_key = (model_name, tracker_name, imgsz)
        with st.container(border=True):
            _rail_header("Signal Source")
            mode = st.radio("Origin", ["image", "video", "live"],
                            format_func=lambda m: {"image": "Archival", "video": "Motion", "live": "Live"}[m],
                            horizontal=True, key="cr_mode")
            st.radio("Monitor Wall", ["Junction", "2 × 2", "1 × 4", "4 × 1"], horizontal=True, key="feed_layout")
            
        with st.container(border=True):
            _rail_header("Operational Directives")
            op_mode = st.radio("Signal Mode", ["AUTO", "NIGHT", "POWER_OUTAGE", "MANUAL"], 
                               format_func=lambda m: {"AUTO": "Automatic", "NIGHT": "Night Mode (Flash)", "POWER_OUTAGE": "Power Outage", "MANUAL": "Police Override"}[m], 
                               key="op_mode")
            if op_mode == "MANUAL":
                st.radio("Force Green", list(DIRECTIONS), format_func=lambda d: DIR_META[d]["label"], horizontal=True, key="manual_dir")

        with st.container(border=True):
            _rail_header("Transport")
            if st.button("◆ INITIATE", type="primary", use_container_width=True):
                port = ls.ensure_server()
                st.session_state.mjpeg_port = port
                st.session_state.active_model_key = current_key
                for d in active:
                    src = _make_source(d, mode)
                    if src is not None:
                        shapes = st.session_state.config[d]["shapes"]
                        ls.start_stream(d, src, model_name, tracker_name,
                                        det_conf, imgsz, 3.0, shapes)
                st.session_state.live = True
                st.rerun()
            t1, t2 = st.columns(2)
            with t1:
                if st.button("■ SUSPEND", use_container_width=True):
                    ls.pause_all()
                    st.session_state.live = False
            with t2:
                if st.button("◇ PURGE", use_container_width=True):
                    ls.stop_all()
                    ls.clear_state()
                    st.session_state.pop("decision_flow", None)
                    st.session_state.pop("_last_decision_t", None)
                    st.session_state.live = False
                    st.rerun()

        if st.session_state.get("live") and st.session_state.get("active_model_key") != current_key:
            ls.stop_all()
            ls.clear_state()
            st.session_state.pop("decision_flow", None)
            st.session_state.live = False
            st.info("Parameters modified — INITIATE to bind.")

    # ══ resolve available sources ══
    if mode == "image":
        avail = [d for d in active if st.session_state.config[d]["media_type"] == "image"
                 and st.session_state.config[d]["frame"] is not None]
    elif mode == "video":
        avail = [d for d in active if st.session_state.config[d]["media_type"] == "video"
                 and st.session_state.config[d]["media_bytes"]]
    else:
        avail = list(active)

    # live camera channels go in the left rail
    if mode == "live" and avail:
        with left_col:
            with st.container(border=True):
                _rail_header("Optic Channels")
                for d in avail:
                    st.number_input(f"{d.upper()} CAM", 0, 9,
                                    value=st.session_state.get(f"cam_index_{d}", 0),
                                    key=f"cam_index_{d}")

    # ══ CENTER — MONITOR WALL ══
    with center_col:
        if not avail:
            st.markdown(
                f'<div style="height:70vh;display:flex;align-items:center;justify-content:center;'
                f'border:1px dashed {C["border-h"]};background:{C["surface"]};">'
                f'<div style="text-align:center;">'
                f'<div style="font-family:{F_DISPLAY};font-size:18px;letter-spacing:0.2em;color:{C["gold"]};">NO SIGNALS ACQUIRED</div>'
                f'<div style="font-family:{F_BODY};font-size:11px;color:{C["text-dim"]};margin-top:10px;letter-spacing:0.1em;text-transform:uppercase;">'
                f'Configure media in the Setup survey</div></div></div>',
                unsafe_allow_html=True,
            )
        else:
            decision_banner(avail)
            layout = st.session_state.get("feed_layout", "Junction")
            h = {"Junction": 25, "2 × 2": 36, "1 × 4": 36, "4 × 1": 17}.get(layout, 36)
            port = st.session_state.get("mjpeg_port")

            if layout == "Junction":
                r1 = st.columns([1.2,1.5,1.2], gap="small")
                r2 = st.columns([1.5,2,1.5], gap="small")
                r3 = st.columns([1.2,1.5,1.2], gap="small")
                
                with r2[1]:
                    st.markdown(
                        f'<div style="height:{h}vh;display:flex;align-items:center;justify-content:center;'
                        f'border:1px dashed {C["border"]};background:{C["bg"]};">'
                        f'<div style="text-align:center;">'
                        f'<div style="width:14px;height:14px;transform:rotate(45deg);border:2px solid {C["gold"]};margin:0 auto 12px;box-shadow:0 0 12px {C["gold"]};"></div>'
                        f'<div style="font-family:{F_DISPLAY};font-size:12px;letter-spacing:0.2em;color:{C["gold"]};">JUNCTION</div>'
                        f'</div></div>', unsafe_allow_html=True
                    )
                    
                rotations = {"north": 180, "south": 0, "west": 90, "east": -90}
                for d in avail:
                    slot = {"north": r1[1], "south": r3[1], "west": r2[0], "east": r2[2]}.get(d)
                    if slot:
                        with slot:
                            if port:
                                base_rot = st.session_state.config[d].get("rotation", 0)
                                total_rot = (base_rot + rotations[d]) % 360
                                st.markdown(_live_dock(d, port, h, total_rot), unsafe_allow_html=True)
                            else:
                                st.markdown(_idle_dock(d, h), unsafe_allow_html=True)
            else:
                if layout == "2 × 2":
                    r1 = st.columns(2, gap="small")
                    r2 = st.columns(2, gap="small")
                    slots = [r1[0], r1[1], r2[0], r2[1]]
                elif layout == "1 × 4":
                    slots = st.columns(max(len(avail), 1), gap="small")
                else:
                    slots = [st.columns(1)[0] for _ in avail]
    
                for i, d in enumerate(avail):
                    with slots[i % len(slots)]:
                        if port:
                            base_rot = st.session_state.config[d].get("rotation", 0)
                            st.markdown(_live_dock(d, port, h, base_rot), unsafe_allow_html=True)
                        else:
                            st.markdown(_idle_dock(d, h), unsafe_allow_html=True)

    # ══ RIGHT RAIL — DECISION TELEMETRY ══
    with right_col:
        decision_panel(avail if avail else active)