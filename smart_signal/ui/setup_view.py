"""Setup view — top-down intersection layout, Art Deco styling."""

from typing import List
import json
import cv2
import streamlit as st

from config.constants import DIRECTIONS, DIR_META
from theme.tokens import C, F_DISPLAY, F_BODY
from ui.annotation_panel import annotation_panel

def _get_active() -> List[str]:
    if "active_directions" not in st.session_state:
        st.session_state.active_directions = list(DIRECTIONS)
    return st.session_state.active_directions


def _toggle_direction(d: str) -> None:
    active = _get_active()
    if d in active:
        active.remove(d)
    else:
        active.append(d)
    st.session_state.active_directions = active


def _signal_state(d: str) -> str:
    return st.session_state.get("signal_state", {}).get(d, "red")


def _corner_accents() -> str:
    return (
        f'<div style="position:absolute;top:4px;left:4px;width:8px;height:8px;'
        f'border-top:1px solid {C["gold"]};border-left:1px solid {C["gold"]};"></div>'
        f'<div style="position:absolute;bottom:4px;right:4px;width:8px;height:8px;'
        f'border-bottom:1px solid {C["gold"]};border-right:1px solid {C["gold"]};"></div>'
    )


def _direction_cell(d: str) -> None:
    meta = DIR_META[d]
    cfg = st.session_state.config[d]
    active = d in _get_active()
    selected = st.session_state.get("annotate_dir") == d
    sig = _signal_state(d)

    with st.container(border=True):
        st.markdown(
            f'<div style="position:relative;padding:6px 4px 10px;">'
            f'{_corner_accents()}'
            f'<div style="font-family:{F_DISPLAY};font-size:20px;letter-spacing:0.18em;color:{C["text"]};">'
            f'{meta["arrow"]} {meta["label"]}</div>'
            f'<div style="font-family:{F_BODY};font-size:10px;color:{C["text-dim"]};text-transform:uppercase;'
            f'letter-spacing:0.12em;margin-top:5px;">'
            f'{"● ACTIVE" if active else "○ DISABLED"} · SIGNAL {sig.upper()}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        if cfg["frame"] is not None:
            kind = (cfg["media_type"] or "media").upper()
            n_lanes = len([s for s in cfg["shapes"] if s["label"] == "lane"])
            has_xing = any(s["label"] == "zebra_crossing" for s in cfg["shapes"])
            st.caption(f"{kind} · {n_lanes} LANE(S) · {'CROSSING' if has_xing else 'NO CROSSING'}")
        else:
            st.caption("AWAITING MEDIA")

        if cfg["frame"] is not None:
            h, w = cfg["frame"].shape[:2]
            thumb = cv2.resize(cfg["frame"], (max(int(w * 90 / h), 1), 90))
            rotation = cfg.get("rotation", 0)
            if rotation == 90:
                thumb = cv2.rotate(thumb, cv2.ROTATE_90_CLOCKWISE)
            elif rotation == 180:
                thumb = cv2.rotate(thumb, cv2.ROTATE_180)
            elif rotation == 270 or rotation == -90:
                thumb = cv2.rotate(thumb, cv2.ROTATE_90_COUNTERCLOCKWISE)
            st.image(cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB), width="stretch")
            
            new_rot = st.selectbox("Feed Orientation", [0, 90, 180, 270], index=[0, 90, 180, 270].index(rotation if rotation != -90 else 270), key=f"rot_{d}", format_func=lambda x: f"{x}°", label_visibility="collapsed")
            if new_rot != rotation:
                st.session_state.config[d]["rotation"] = new_rot
                st.rerun()

        b1, b2 = st.columns(2)
        with b1:
            if st.button("◆ OPEN" if selected else "◆ ANNOTATE", key=f"anno_{d}",
                         use_container_width=True, type="primary" if selected else "secondary"):
                st.session_state.annotate_dir = d
                st.rerun()
        with b2:
            if st.button("DISABLE" if active else "ENABLE", key=f"act_{d}",
                         use_container_width=True):
                _toggle_direction(d)
                st.rerun()


def _center_cell() -> None:
    with st.container(border=True):
        st.markdown(
            f'<div style="position:relative;text-align:center;padding:26px 8px;">'
            f'{_corner_accents()}'
            f'<div style="width:14px;height:14px;transform:rotate(45deg);border:2px solid {C["gold"]};'
            f'margin:0 auto 12px;box-shadow:0 0 12px {C["gold"]};"></div>'
            f'<div style="font-family:{F_DISPLAY};font-size:18px;letter-spacing:0.2em;color:{C["gold"]};">JUNCTION</div>'
            f'<div style="font-family:{F_BODY};font-size:10px;color:{C["text-dim"]};text-transform:uppercase;'
            f'letter-spacing:0.12em;margin-top:6px;">Signalized Core · Adaptive</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _corner_cell() -> None:
    st.markdown(
        f'<div style="height:60px;background:repeating-linear-gradient(45deg,{C["surface"]} 0 1px,transparent 1px 9px);'
        f'border:1px solid rgba(212,175,55,0.12);"></div>',
        unsafe_allow_html=True,
    )


def setup_view() -> None:
    active = _get_active()

    st.markdown(
        f'''
        <div style="padding:24px 32px;margin-bottom:8px;background:{C["surface"]};
                    border:1px solid {C["border-h"]};position:relative;">
          <div style="position:absolute;top:4px;left:4px;width:12px;height:12px;border-top:1px solid {C["gold"]};border-left:1px solid {C["gold"]};"></div>
          <div style="position:absolute;bottom:4px;right:4px;width:12px;height:12px;border-bottom:1px solid {C["gold"]};border-right:1px solid {C["gold"]};"></div>
          <div style="font-family:{F_DISPLAY};font-size:28px;letter-spacing:0.2em;color:{C["gold"]};">INTERSECTION SETUP</div>
          <div style="font-family:{F_BODY};font-size:12px;color:{C["text-dim"]};text-transform:uppercase;letter-spacing:0.15em;margin-top:6px;">
            Top-down survey · {len(active)}-way junction · active: {', '.join(d.upper() for d in active) if active else 'none'}
          </div>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    r0a, r0b, r0c = st.columns([1, 1.6, 1])
    r1a, r1b, r1c = st.columns([1, 1.6, 1])
    r2a, r2b, r2c = st.columns([1, 1.6, 1])

    with r0a: _corner_cell()
    with r0b: _direction_cell("north")
    with r0c: _corner_cell()
    with r1a: _direction_cell("west")
    with r1b: _center_cell()
    with r1c: _direction_cell("east")
    with r2a: _corner_cell()
    with r2b: _direction_cell("south")
    with r2c: _corner_cell()

    # ── Layout Vault — export / import ────────────────────────────────────
    st.markdown(f'<div style="height:1px;border-top:2px double {C["border"]};margin:28px 0;"></div>',
                unsafe_allow_html=True)
    st.markdown("#### LAYOUT VAULT")
    st.caption("Export your annotated intersection once, then re-import it for the same footage — no re-drawing.")

    v1, v2 = st.columns(2)
    with v1:
        export = {d: st.session_state.config[d]["shapes"] for d in DIRECTIONS}
        st.download_button(
            "◆ EXPORT LAYOUT",
            json.dumps(export, default=str, indent=2),
            file_name="auta_intersection_layout.json",
            mime="application/json",
            use_container_width=True,
        )
    with v2:
        uploaded_layout = st.file_uploader(
            "Import layout", type=["json"], key="layout_upload", label_visibility="collapsed")
        if uploaded_layout is not None:
            if st.button("◆ APPLY IMPORTED LAYOUT", key="apply_layout", use_container_width=True):
                try:
                    data = json.loads(uploaded_layout.getvalue().decode("utf-8"))
                    for d in DIRECTIONS:
                        if d in data:
                            st.session_state.config[d]["shapes"] = [
                                {**s, "points": [tuple(p) for p in s.get("points", [])]}
                                for s in data[d]
                            ]
                    st.rerun()
                except Exception:
                    st.error("Could not parse that layout file.")
                    
    selected = st.session_state.get("annotate_dir")
    if selected:
        st.markdown(f'<div style="height:1px;border-top:2px double {C["border"]};margin:28px 0;"></div>',
                    unsafe_allow_html=True)
        annotation_panel(selected)
    else:
        st.markdown(
            f'<div style="font-family:{F_DISPLAY};font-size:13px;letter-spacing:0.15em;color:{C["gold"]};'
            f'text-align:center;padding:24px;background:{C["surface"]};border:1px dashed {C["border-h"]};margin-top:16px;">'
            f'SELECT A SECTOR TO BEGIN ANNOTATION</div>',
            unsafe_allow_html=True,
        )