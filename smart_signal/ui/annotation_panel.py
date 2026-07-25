"""Annotation panel — one-click polygon/line drawing via a native Streamlit component."""

from geometry.auto_annotate import auto_suggest_lanes
import base64
import os
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from config.constants import DIRECTIONS, DIR_COLORS, CANVAS_HEIGHT
from theme.tokens import C, F_DISPLAY, F_BODY
from visualization.annotate import annotate_frame
from video import live_stream as ls



def _invalidate_control_room() -> None:
    """Stop live streams so the control room picks up freshly uploaded media."""
    ls.stop_all()
    ls.clear_state()
    st.session_state.pop("decision_flow", None)
    st.session_state.pop("_last_decision_t", None)
    st.session_state.live = False


# ── Register the drawing component ────────────────────────────────────────────
_TOOL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "polygon_tool")
_polygon_tool = components.declare_component("polygon_tool", path=_TOOL_DIR)


def draw_shape_tool(
    image_b64: str, width: int, height: int, mode: str, accent: str, key: str
) -> Optional[Dict[str, Any]]:
    """Render the pen-tool canvas. Returns {'points': [...], 'nonce': n} on save."""
    return _polygon_tool(
        image_b64=image_b64,
        width=width,
        height=height,
        mode=mode,
        accent=C["gold-bright"],  # bright gold pops against the photo
        key=key,
        default=None,
    )


def _frame_to_b64(frame: np.ndarray, disp_w: int, disp_h: int) -> str:
    resized = cv2.resize(frame, (disp_w, disp_h))
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    buf = BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _section_label(text: str) -> None:
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin:24px 0 12px;border-bottom:1px solid {C["border"]};padding-bottom:6px;">'
        f'<span style="width:6px;height:6px;transform:rotate(45deg);background:{C["gold"]};"></span>'
        f'<span style="font-family:{F_DISPLAY};font-size:14px;font-weight:400;letter-spacing:0.15em;'
        f'text-transform:uppercase;color:{C["gold"]};">{text}</span></div>',
        unsafe_allow_html=True,
    )


# ── Vertex editor (adjust saved shapes) ───────────────────────────────────────
def vertex_editor(direction: str, idx: int, shape: Dict[str, Any]) -> None:
    pts = shape["points"]
    with st.expander(f"Edit Vertices — {shape['label'].upper()} I.{idx + 1}", expanded=False):
        new_pts: List[Tuple[float, float]] = []
        for i in range(0, len(pts), 4):
            cols = st.columns(4)
            for j, col in enumerate(cols):
                k = i + j
                if k >= len(pts):
                    break
                with col:
                    x = st.number_input(f"Pt {k+1} X", value=float(pts[k][0]), step=1.0,
                                        key=f"vx_{direction}_{idx}_{k}",
                                        label_visibility="collapsed")
                    y = st.number_input(f"Pt {k+1} Y", value=float(pts[k][1]), step=1.0,
                                        key=f"vy_{direction}_{idx}_{k}",
                                        label_visibility="collapsed")
                    new_pts.append((x, y))

        b1, b2 = st.columns(2)
        with b1:
            if st.button("◆ APPLY ALTERATIONS", key=f"applyv_{direction}_{idx}",
                         use_container_width=True):
                st.session_state.config[direction]["shapes"][idx]["points"] = new_pts
                st.rerun()
        with b2:
            if st.button("◇ PURGE SHAPE", key=f"delv_{direction}_{idx}",
                         use_container_width=True):
                st.session_state.config[direction]["shapes"].pop(idx)
                st.rerun()


# ── Main panel ────────────────────────────────────────────────────────────────
def annotation_panel(direction: str) -> None:
    cfg = st.session_state.config[direction]

    # ── Art Deco Header ───────────────────────────────────────────────────
    st.markdown(
        f'''
        <div style="padding:18px 24px;margin-bottom:20px;
                    background:{C["surface"]};border:1px solid {C["border-h"]};
                    border-radius:0px;position:relative;">
          <div style="position:absolute;top:4px;left:4px;width:8px;height:8px;border-top:1px solid {C["gold"]};border-left:1px solid {C["gold"]};"></div>
          <div style="position:absolute;bottom:4px;right:4px;width:8px;height:8px;border-bottom:1px solid {C["gold"]};border-right:1px solid {C["gold"]};"></div>
          <div style="font-family:{F_DISPLAY};font-size:22px;font-weight:400;letter-spacing:0.2em;
                      color:{C["text"]};">{direction.upper()} <span style="color:{C["gold"]};
                      font-size:16px;letter-spacing:0.1em;">SECTOR</span></div>
          <div style="font-family:{F_BODY};font-size:11px;color:{C["text-dim"]};margin-top:6px;text-transform:uppercase;letter-spacing:0.1em;">
            Upload blueprint media, sketch vectors, and commit.
          </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    # ── Upload (re-decode only when the file actually changes) ─────────────
    uploaded = st.file_uploader(
        f"Transmit visual data — {direction.title()}",
        type=["jpg", "jpeg", "png", "mp4", "mov", "avi"],
        key=f"upload_{direction}",
    )
    if uploaded is not None:
        file_sig = (uploaded.name, uploaded.size)
        sig_key = f"upload_sig_{direction}"
        if st.session_state.get(sig_key) != file_sig:
            st.session_state[sig_key] = file_sig

            is_video = bool(uploaded.type and uploaded.type.startswith("video"))
            cfg["media_type"] = "video" if is_video else "image"

            decoded = None
            if is_video:
                tmp = f"/tmp/ss_{direction}_{uploaded.name}"
                with open(tmp, "wb") as f:
                    f.write(uploaded.getbuffer())
                cap = cv2.VideoCapture(tmp)
                ok, decoded = cap.read()
                cap.release()
                if ok:
                    cfg["media_bytes"] = tmp
            else:
                buf = np.frombuffer(uploaded.getbuffer(), np.uint8)
                decoded = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                if decoded is not None:
                    cfg["media_bytes"] = uploaded.getbuffer()

            if decoded is None:
                st.error("Could not decipher media payload.")
                cfg["frame"] = None
            else:
                cfg["frame"] = decoded
                _invalidate_control_room()

    # ── Always read the persisted frame and guard before use ───────────────
    frame = cfg.get("frame")
    if frame is None:
        st.info("Awaiting optical input to commence mapping.")
        return

    # ── Compute display scale ─────────────────────
    h, w = frame.shape[:2]
    scale = CANVAS_HEIGHT / h
    cfg["scale"] = scale
    disp_w, disp_h = int(w * scale), CANVAS_HEIGHT

    # ── Model-assisted drafting ───────────────────────────────────────────
    _section_label("Model-Assisted Drafting")
    a1, a2 = st.columns([2, 1.5])
    with a1:
        orientation = st.radio(
            "Lane orientation", ["vertical", "horizontal"],
            horizontal=True, key=f"orient_{direction}", label_visibility="collapsed")
    with a2:
        if st.button("◆ AUTO-DRAFT LANES", key=f"auto_{direction}", use_container_width=True):
            with st.spinner("Running detection model…"):
                polys = auto_suggest_lanes(
                    frame, st.session_state.get("model_name", "yolov8n.pt"), orientation)
            if not polys:
                st.warning("No lane clusters found — ensure vehicles are visible, or draft manually.")
            else:
                n = len(cfg["shapes"])
                for i, poly in enumerate(polys):
                    cfg["shapes"].append({
                        "label": "lane", "points": poly,
                        "id": f"{direction}_lane_{n + i + 1}",
                        "side": direction, "travel": "incoming", "focus": True,
                    })
                st.rerun()
    st.caption("vertical = lanes run top↕bottom · horizontal = lanes run left↔right · suggestions are a starting point — refine below")

    # ── Tool selection ─────────────────────────────────────────────────────
    _section_label("DRAFTING IMPLEMENT")
    draw_choice = st.radio(
        "Annotation tool",
        ["Lane (polygon)", "Zebra crossing (polygon)",
         "Stop line (line — 2 pts)", "Count line (line — 2 pts)"],
        key=f"drawmode_{direction}",
        horizontal=True,
        label_visibility="collapsed",
    )
    if "Lane" in draw_choice:
        shape_label, draw_mode = "lane", "polygon"
    elif "Zebra" in draw_choice:
        shape_label, draw_mode = "zebra_crossing", "polygon"
    elif "Stop" in draw_choice:
        shape_label, draw_mode = "stop_line", "line"
    else:
        shape_label, draw_mode = "count_line", "line"

    # ── Lane properties ────────────────────────────────────────────────────
    lane_id = side = travel = turn = None
    is_focus = False
    if shape_label == "lane":
        _section_label("VECTOR METADATA")
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            lane_id = st.text_input(
                "LANE DESIGNATION",
                value=f"{direction}_lane_{len([s for s in cfg['shapes'] if s['label']=='lane']) + 1}",
                key=f"laneid_{direction}")
        with c2:
            side = st.selectbox("CARDINAL SIDE", DIRECTIONS, index=DIRECTIONS.index(direction),
                                key=f"side_{direction}")
        with c3:
            travel = st.selectbox("VECTOR FLOW", ["incoming", "outgoing"],
                                  key=f"travel_{direction}")
        with c4:
            turn = st.selectbox("ROUTING", ["Straight", "Left", "Right"], key=f"turn_{direction}")
        with c5:
            st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
            is_focus = st.checkbox("PRIMARY FOCUS", value=True, key=f"focus_{direction}")

    # ── The pen-tool canvas (one-click save) ──────────────────────────────
    _section_label("SCHEMATIC CANVAS")
    image_b64 = _frame_to_b64(frame, disp_w, disp_h)
    result = draw_shape_tool(
        image_b64=image_b64,
        width=disp_w,
        height=disp_h,
        mode=draw_mode,
        accent=C["gold"],
        key=f"tool_{direction}_{shape_label}",
    )

    # Commit the shape exactly once per save (nonce guard)
    if result and isinstance(result, dict) and "points" in result:
        nonce_key = f"tool_nonce_{direction}_{shape_label}"
        if st.session_state.get(nonce_key) != result.get("nonce"):
            st.session_state[nonce_key] = result.get("nonce")
            raw_pts = result["points"]
            min_pts = 2 if draw_mode == "line" else 3
            if len(raw_pts) >= min_pts:
                original_pts = [(p[0] / scale, p[1] / scale) for p in raw_pts]
                entry: Dict[str, Any] = {"label": shape_label, "points": original_pts}
                if shape_label == "lane":
                    entry.update({
                        "id": lane_id or f"{direction}_lane_{len(cfg['shapes']) + 1}",
                        "side": side or direction,
                        "travel": travel or "incoming",
                        "turn": turn or "Straight",
                        "focus": is_focus,
                    })
                cfg["shapes"].append(entry)
                st.success(f"Archived {shape_label} comprising {len(original_pts)} nodes.")

    # ── Saved shapes + editor ─────────────────────────────────────────────
    _section_label(f"STORED TOPOLOGY · {len(cfg['shapes'])}")
    if not cfg["shapes"]:
        st.markdown(
            f'<div style="font-family:{F_DISPLAY};font-size:12px;letter-spacing:0.15em;color:{C["gold"]};'
            f'padding:20px;text-align:center;background:{C["surface"]};border:1px dashed {C["border-h"]};border-radius:0px;">'
            f'NO TOPOLOGICAL VECTORS DEFINED</div>',
            unsafe_allow_html=True,
        )
    else:
        for i, s in enumerate(cfg["shapes"]):
            if s["label"] == "lane":
                turn_str = f" / {s.get('turn', 'Straight').upper()}" if s.get('travel') == 'incoming' else ""
                desc = (f"{s.get('id','?')} · {s.get('side','?')}/{s.get('travel','?')}{turn_str}"
                        f"{'  [FOCAL]' if s.get('focus') else ''}")
            elif s["label"] == "zebra_crossing":
                desc = f"ZEBRA CROSSING ({len(s['points'])} NODES)"
            elif s["label"] == "stop_line":
                desc = "ARREST LINE"
            elif s["label"] == "count_line":
                desc = "ENUMERATION LINE"
            else:
                desc = s["label"].replace("_", " ").upper()
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:12px;padding:12px 16px;'
                f'margin-bottom:6px;background:{C["surface"]};border:1px solid {C["border"]};'
                f'border-radius:0px;">'
                f'<span style="font-family:{F_DISPLAY};font-size:14px;color:{C["gold"]};'
                f'min-width:24px;">I.{i + 1:02d}</span>'
                f'<span style="width:6px;height:6px;transform:rotate(45deg);background:{C["gold"]};'
                f'flex:none;"></span>'
                f'<span style="font-family:{F_BODY};font-size:12px;color:{C["text"]};letter-spacing:0.1em;">{desc}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            vertex_editor(direction, i, s)

    # ── Preview overlay ───────────────────────────────────────────────────
    if cfg["shapes"]:
        _section_label("COMPOSITE PREVIEW")
        preview = annotate_frame(frame, [], cfg["shapes"])
        st.image(cv2.cvtColor(preview, cv2.COLOR_BGR2RGB),
                 caption=f"{direction.upper()} OVERLAY",
                 width="stretch")