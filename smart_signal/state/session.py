"""
Session state module for Smart Signal — handles initialization of session state.
"""
from collections import defaultdict, deque
import streamlit as st
from config.constants import DIRECTIONS


import os
import cv2

def init_state() -> None:
    """Initialise all session-state keys once."""
    if "config" not in st.session_state:
        default_config = {}
        for d in DIRECTIONS:
            filename = f"{d}.mp4"
            if d == "east":
                filename = "East.mp4"
            filepath = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "footages", filename))
            
            media_bytes = None
            media_type = None
            frame = None
            
            if os.path.exists(filepath):
                cap = cv2.VideoCapture(filepath)
                ok, decoded = cap.read()
                cap.release()
                if ok:
                    media_bytes = filepath
                    media_type = "video"
                    frame = decoded
                    
            default_config[d] = {
                "media_bytes": media_bytes,
                "media_type": media_type,
                "frame": frame,
                "scale": 1.0,
                "shapes": [],
                "rotation": 0,
            }
        st.session_state.config = default_config
    if "track_history" not in st.session_state:
        st.session_state.track_history = defaultdict(lambda: deque(maxlen=15))
    if "signal_state" not in st.session_state:
        st.session_state.signal_state = {d: "red" for d in DIRECTIONS}
    if "wait_times" not in st.session_state:
        st.session_state.wait_times = {d: 0.0 for d in DIRECTIONS}
    if "last_run" not in st.session_state:
        st.session_state.last_run = None
    if "op_mode" not in st.session_state:
        st.session_state.op_mode = "AUTO"
    if "manual_dir" not in st.session_state:
        st.session_state.manual_dir = "north"