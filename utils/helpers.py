# utils/helpers.py — Shared constants, color helpers, and safe math utilities.

import numpy as np

# ── Coimbatore city centre coordinates ───────────────────────────────────────
CBE_LAT  = 11.0168
CBE_LON  = 76.9558
CBE_ZOOM = 14

# ── Traffic level thresholds ──────────────────────────────────────────────────
DENSITY_LOW    = 0.30   # < 30 % capacity → green
DENSITY_MED    = 0.65   # 30–65 % → yellow
# > 65 % → red

# ── Signal constants ──────────────────────────────────────────────────────────
MIN_GREEN  = 10   # seconds
MAX_GREEN  = 90   # seconds
DEFAULT_GREEN = 30
YELLOW_TIME   = 3   # seconds (fixed)

# ── Road speed defaults (km/h) ────────────────────────────────────────────────
SPEED_ARTERIAL    = 50
SPEED_COLLECTOR   = 40
SPEED_LOCAL       = 30

# ── Simulation step ───────────────────────────────────────────────────────────
SIM_DT = 10   # seconds per step


def density_color(density: float) -> str:
    """Return a Folium/HTML color string based on normalised density (0–1)."""
    if density < DENSITY_LOW:
        return "#00cc44"   # green
    elif density < DENSITY_MED:
        return "#ffaa00"   # yellow/amber
    else:
        return "#ff2222"   # red


def congestion_label(density: float) -> str:
    if density < DENSITY_LOW:
        return "Smooth"
    elif density < DENSITY_MED:
        return "Moderate"
    else:
        return "Heavy"


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b != 0 else default


def clamp(val: float, lo: float, hi: float) -> float:
    return float(np.clip(val, lo, hi))


def format_seconds(s: float) -> str:
    m = int(s) // 60
    sec = int(s) % 60
    return f"{m}m {sec:02d}s" if m else f"{sec}s"
