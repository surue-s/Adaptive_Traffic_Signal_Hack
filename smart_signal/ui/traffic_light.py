"""Reusable traffic-signal renderer (Art Deco housing with glowing lamps)."""

# Colors defined as: (bright_center, main_glow, off_base, off_shadow)
# Adapted to Gatsby aesthetic: Ruby Red, Golden Amber, Emerald Green
SIGNAL_COLORS = {
    "red":    ("#FF6B6B", "#D32F2F", "#2D0A0A", "#140505"), # Ruby
    "yellow": ("#FFDF00", "#D4AF37", "#332700", "#1A1400"), # Amber/Gold
    "green":  ("#50C878", "#008A4A", "#042110", "#020A05"), # Emerald
}

def effective_lamp(state: str, remaining: float = None) -> str:
    """Green flips to yellow in the last 3 seconds before a phase change."""
    if state == "green" and remaining is not None and remaining < 3.0:
        return "yellow"
    base = state.replace("flashing_", "")
    return state if base in SIGNAL_COLORS else "red"

def traffic_light_html(state: str, scale: float = 1.0, horizontal: bool = False) -> str:
    """Return HTML for a geometric Art Deco signal housing with vintage incandescent glow."""
    base_state = state.replace("flashing_", "")
    base_state = base_state if base_state in SIGNAL_COLORS else "red"
    is_flashing = "flashing_" in state
    
    # Calibrated base dimensions
    lamp = int(18 * scale)
    gap = int(10 * scale)
    pad = int(12 * scale)
    border_w = max(1, int(1.5 * scale))

    lamps_html = ""
    for name in ("red", "yellow", "green"):
        on = (name == base_state)
        bright, main, off_base, off_dark = SIGNAL_COLORS[name]
        
        anim = ""
        if on:
            # Art Deco glass glow: intense warm core, rich saturated halo
            bg = f"radial-gradient(circle at 50% 50%, {bright} 10%, {main} 60%, {off_dark} 100%)"
            glow = (
                f"box-shadow: "
                f"0 0 {int(12*scale)}px {int(2*scale)}px {main}AA, "
                f"0 0 {int(25*scale)}px {int(6*scale)}px {main}55, "
                f"inset 0 0 {int(4*scale)}px rgba(0,0,0,0.6);"
            )
            if is_flashing:
                anim = "animation: ss-flash 1s infinite alternate;"
        else:
            # Inactive dark jewel tone
            bg = f"linear-gradient(135deg, {off_base} 0%, {off_dark} 100%)"
            glow = (
                f"box-shadow: "
                f"inset 0 {int(3*scale)}px {int(6*scale)}px rgba(0,0,0,0.8), "
                f"0 {int(1*scale)}px 0px rgba(212,175,55,0.15);"
            )

        lamps_html += (
            f'<div style="width:{lamp}px; height:{lamp}px; border-radius:50%; '
            f'background:{bg}; {glow} '
            f'border: {border_w}px solid #D4AF37; '
            f'position: relative; {anim} '
            f'transition: background 0.2s ease, box-shadow 0.2s ease;">'
            f'</div>'
        )

    direction = "row" if horizontal else "column"
    
    # Geometric, sharp brass-and-obsidian casing
    return (
        f'<div style="display:inline-flex; flex-direction:{direction}; gap:{gap}px; '
        f'padding:{pad}px; '
        f'background: #141414; '
        f'border: {border_w}px solid #D4AF37; '
        f'border-radius: 0px; ' # Strict geometry
        f'position: relative; '
        f'box-shadow: 0 4px 15px rgba(212,175,55,0.15), inset 0 0 10px rgba(0,0,0,0.8);">'
        
        # Subtle deco corner accents
        f'<div style="position:absolute; top:2px; left:2px; width:4px; height:4px; background:#D4AF37;"></div>'
        f'<div style="position:absolute; bottom:2px; left:2px; width:4px; height:4px; background:#D4AF37;"></div>'
        f'<div style="position:absolute; top:2px; right:2px; width:4px; height:4px; background:#D4AF37;"></div>'
        f'<div style="position:absolute; bottom:2px; right:2px; width:4px; height:4px; background:#D4AF37;"></div>'
        
        f'{lamps_html}'
        f'</div>'
    )