"""
Pfago-Cleavage Cascade Concentration Calculator
------------------------------------------------
A Streamlit app for calculating Histamine / Malachite Green concentrations
from a Pfago-cleavage fluorescence cascade, with calibration management,
input validation, curve visualization, and CSV data logging.

Deploy: push this repo to GitHub and deploy on Streamlit Community Cloud
(https://streamlit.io/cloud). Entry point: app.py
"""

import io
import math
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ----------------------------------------------------------------------------
# PAGE CONFIG
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Pfago Concentration Calculator",
    page_icon="🧪",
    layout="centered",  # single-column, thumb-friendly on mobile
    initial_sidebar_state="collapsed",
)

CALIB_PASSWORD = "admin123"  # demo only — replace with st.secrets in production
LOG_COLUMNS = [
    "timestamp", "substance", "batch_id", "machine_id",
    "y_raw", "y_background", "y_net", "concentration_x",
    "slope_m", "intercept_b",
]

# ----------------------------------------------------------------------------
# DESIGN TOKENS — "instrument faceplate / chart-recorder" identity
# Panel ink & etched grid evoke an anodized instrument casing; the LCD
# readout and the amber "recorder pen" marker are the signature elements.
# ----------------------------------------------------------------------------
INK = "#12181B"          # main panel background
SURFACE = "#1B2328"      # raised card / section background
SURFACE_INSET = "#0E1315"  # recessed readout background
GRID = "#2A363B"         # etched hairline grid / dividers
EMISSION = "#6EE7B7"     # fluorescence-green accent (curve, glow, active state)
RECORDER_AMBER = "#F5A623"  # sample marker / warnings, chart-recorder ink
TEXT = "#EDEFEE"         # primary readout/label text
TEXT_DIM = "#8B9A9E"     # secondary/caption text
DANGER = "#F2555A"       # invalid-state red

# ----------------------------------------------------------------------------
# DEFAULT CALIBRATION MODELS
# ----------------------------------------------------------------------------
DEFAULT_MODELS = {
    "Histamine": {
        "type": "log10",       # Y_net = m*log10(x) + b
        "m": 13780.0,
        "b": -20930.0,
        "units": "µM",
        "x_range": (1e-3, 1e2),
    },
    "Malachite Green": {
        "type": "ln",           # Y_net = m*ln(x) + b
        "m": 3892.39,
        "b": -4664.89,
        "units": "µM",
        "x_range": (1e-3, 1e2),
    },
}

if "models" not in st.session_state:
    st.session_state.models = {k: v.copy() for k, v in DEFAULT_MODELS.items()}
if "log" not in st.session_state:
    st.session_state.log = pd.DataFrame(columns=LOG_COLUMNS)
if "calib_unlocked" not in st.session_state:
    st.session_state.calib_unlocked = False


# ----------------------------------------------------------------------------
# STYLE INJECTION
# ----------------------------------------------------------------------------
def inject_style():
    st.markdown(
        f"""
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
        html, body, [data-testid="stAppViewContainer"], [data-testid="stAppViewContainer"] > .main {{
            background-color: {INK};
            background-image:
                linear-gradient(90deg, {GRID} 1px, transparent 1px),
                linear-gradient(180deg, {GRID} 1px, transparent 1px);
            background-size: 28px 28px;
            background-attachment: fixed;
            color: {TEXT};
            font-family: 'IBM Plex Sans', sans-serif;
        }}
        [data-testid="stHeader"] {{ background-color: transparent; }}
        [data-testid="stSidebar"] {{
            background-color: {SURFACE};
            border-right: 1px solid {GRID};
        }}
        [data-testid="stSidebar"] * {{ color: {TEXT} !important; }}

        /* Nameplate header */
        .nameplate {{
            border: 1px solid {GRID};
            background: linear-gradient(180deg, {SURFACE} 0%, {INK} 100%);
            border-radius: 4px;
            padding: 18px 20px;
            margin-bottom: 6px;
        }}
        .nameplate .eyebrow {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 11px;
            letter-spacing: 0.18em;
            color: {EMISSION};
            text-transform: uppercase;
        }}
        .nameplate h1 {{
            font-family: 'IBM Plex Sans', sans-serif;
            font-weight: 600;
            font-size: 26px;
            margin: 4px 0 2px 0;
            color: {TEXT};
        }}
        .nameplate .sub {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 12px;
            color: {TEXT_DIM};
        }}

        /* Section labels styled like panel section tags */
        .panel-tag {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 11px;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: {TEXT_DIM};
            border-left: 3px solid {EMISSION};
            padding-left: 8px;
            margin: 22px 0 10px 0;
        }}

        /* Text inputs / number inputs styled as recessed fields */
        [data-testid="stTextInput"] input,
        [data-testid="stNumberInput"] input,
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
            background-color: {SURFACE_INSET} !important;
            color: {TEXT} !important;
            border: 1px solid {GRID} !important;
            border-radius: 3px !important;
            font-family: 'IBM Plex Mono', monospace !important;
        }}
        label, .stMarkdown, p, span {{ color: {TEXT}; }}

        /* Buttons — instrument switches */
        div.stButton > button, [data-testid="stDownloadButton"] button {{
            background-color: {SURFACE};
            color: {EMISSION};
            border: 1px solid {EMISSION};
            border-radius: 3px;
            font-family: 'IBM Plex Mono', monospace;
            letter-spacing: 0.04em;
            font-weight: 500;
            transition: all 0.15s ease;
        }}
        div.stButton > button:hover, [data-testid="stDownloadButton"] button:hover {{
            background-color: {EMISSION};
            color: {INK};
            border-color: {EMISSION};
        }}

        /* LCD readout — the signature element */
        .readout-row {{ display: flex; gap: 14px; flex-wrap: wrap; }}
        .readout {{
            flex: 1 1 220px;
            background: {SURFACE_INSET};
            border: 1px solid {GRID};
            border-radius: 4px;
            padding: 14px 18px 16px 18px;
        }}
        .readout .label {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 11px;
            letter-spacing: 0.14em;
            color: {TEXT_DIM};
            text-transform: uppercase;
        }}
        .readout .value {{
            font-family: 'IBM Plex Mono', monospace;
            font-variant-numeric: tabular-nums;
            font-size: 34px;
            font-weight: 600;
            color: {EMISSION};
            text-shadow: 0 0 14px rgba(110, 231, 183, 0.45);
            line-height: 1.25;
        }}
        .readout .value.amber {{
            color: {RECORDER_AMBER};
            text-shadow: 0 0 14px rgba(245, 166, 35, 0.45);
        }}
        .readout .unit {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 14px;
            color: {TEXT_DIM};
            margin-left: 6px;
        }}

        hr {{ border-color: {GRID}; }}

        [data-testid="stMetricValue"] {{
            font-family: 'IBM Plex Mono', monospace;
            color: {EMISSION};
        }}

        .footnote {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 11px;
            color: {TEXT_DIM};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def readout(label, value_str, unit="", amber=False):
    cls = "value amber" if amber else "value"
    st.markdown(
        f"""
        <div class="readout">
            <div class="label">{label}</div>
            <div class="{cls}">{value_str}<span class="unit">{unit}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------------------
# MATH HELPERS
# ----------------------------------------------------------------------------
def forward_y(x, m, b, ftype):
    if ftype == "log10":
        return m * math.log10(x) + b
    return m * math.log(x) + b


def solve_x(y_net, m, b, ftype):
    exponent = (y_net - b) / m
    if ftype == "log10":
        return 10 ** exponent
    return math.exp(exponent)


# ----------------------------------------------------------------------------
# RENDER
# ----------------------------------------------------------------------------
inject_style()

st.markdown(
    """
    <div class="nameplate">
        <div class="eyebrow">Pfago · Cleavage Cascade Assay</div>
        <h1>Concentration Calculator</h1>
        <div class="sub">Y_NET → [x] · log-linear calibration readout</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.warning(
    "⚠️ **Machine & assay specific.** These calibration curves are only valid for the "
    "instrument, reagent lot, and assay conditions they were derived from. Re-calibrate "
    "before use on a different machine or reagent batch.",
    icon="⚠️",
)

# ----------------------------------------------------------------------------
# SIDEBAR — CALIBRATION MANAGEMENT
# ----------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="panel-tag">Calibration Panel</div>', unsafe_allow_html=True)

    if not st.session_state.calib_unlocked:
        pw = st.text_input("Enter calibration password", type="password")
        if st.button("Unlock"):
            if pw == CALIB_PASSWORD:
                st.session_state.calib_unlocked = True
                st.success("Calibration unlocked.")
                st.rerun()
            else:
                st.error("Incorrect password.")
    else:
        st.success("Calibration unlocked ✅")
        if st.button("Lock again"):
            st.session_state.calib_unlocked = False
            st.rerun()

        st.divider()
        for substance, model in st.session_state.models.items():
            st.subheader(substance)
            new_m = st.number_input(
                f"Slope (m) — {substance}", value=float(model["m"]),
                key=f"m_{substance}", format="%.4f",
            )
            new_b = st.number_input(
                f"Intercept (b) — {substance}", value=float(model["b"]),
                key=f"b_{substance}", format="%.4f",
            )
            if new_m == 0:
                st.error("Slope cannot be zero — reverting to previous value.")
            else:
                st.session_state.models[substance]["m"] = new_m
                st.session_state.models[substance]["b"] = new_b

        if st.button("Reset to factory defaults"):
            st.session_state.models = {k: v.copy() for k, v in DEFAULT_MODELS.items()}
            st.rerun()

    st.divider()
    st.caption(
        "Calibration edits apply for this session. For permanent batch-specific "
        "coefficients, update `DEFAULT_MODELS` in the source or connect a database."
    )

# ----------------------------------------------------------------------------
# MAIN FORM — SAMPLE INPUT
# ----------------------------------------------------------------------------
st.markdown('<div class="panel-tag">1 · Sample &amp; Signal Input</div>', unsafe_allow_html=True)

substance = st.selectbox("Substance", list(st.session_state.models.keys()))
model = st.session_state.models[substance]

col1, col2 = st.columns(2)
with col1:
    batch_id = st.text_input("Pfago Reagent Batch ID", placeholder="e.g. B-2026-014")
with col2:
    machine_id = st.text_input("Machine ID", placeholder="e.g. QPCR-03")

y_raw = st.number_input(
    "Raw Fluorescence — Y_raw (RFU)", value=0.0, format="%.4f",
    help="Raw signal reading directly from the fluorescence/PCR instrument.",
)

use_background = st.toggle("Subtract background / blank signal", value=True)
y_background = 0.0
if use_background:
    y_background = st.number_input(
        "Background / Blank Signal — Y_background (RFU)", value=0.0, format="%.4f",
        help="Signal from the negative control / blank well.",
    )

y_net = y_raw - y_background

st.markdown('<div class="panel-tag">Corrected Signal</div>', unsafe_allow_html=True)
readout("Y_NET", f"{y_net:,.4f}", unit="RFU")

# ----------------------------------------------------------------------------
# VALIDATION
# ----------------------------------------------------------------------------
valid = True
if y_net <= 0:
    st.error("🚫 Invalid Input: Corrected signal must be greater than zero.")
    valid = False

if model["m"] == 0:
    st.error("🚫 Invalid calibration: slope (m) cannot be zero.")
    valid = False

# ----------------------------------------------------------------------------
# CALCULATION
# ----------------------------------------------------------------------------
st.markdown('<div class="panel-tag">2 · Result</div>', unsafe_allow_html=True)

x_result = None
if valid:
    try:
        x_result = solve_x(y_net, model["m"], model["b"], model["type"])
        if x_result <= 0 or math.isnan(x_result) or math.isinf(x_result):
            st.error("🚫 Calculation produced a non-physical result (x ≤ 0 or undefined). "
                      "Check inputs and calibration coefficients.")
            x_result = None
    except (ValueError, OverflowError, ZeroDivisionError) as e:
        st.error(f"🚫 Calculation error: {e}")
        x_result = None

if x_result is not None:
    readout("Concentration [x]", f"{x_result:,.6g}", unit=model["units"], amber=True)
    st.write("")

    # ---- Plotly curve, styled to match the panel ----
    x_lo, x_hi = model["x_range"]
    x_lo = min(x_lo, x_result / 10) if x_result > 0 else x_lo
    x_hi = max(x_hi, x_result * 10)
    x_vals = [x_lo * (x_hi / x_lo) ** (i / 200) for i in range(201)]
    y_vals = [forward_y(xv, model["m"], model["b"], model["type"]) for xv in x_vals]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x_vals, y=y_vals, mode="lines", name="Calibration curve",
        line=dict(color=EMISSION, width=2.5),
    ))
    fig.add_trace(go.Scatter(
        x=[x_result], y=[y_net], mode="markers", name="Sample result",
        marker=dict(color=RECORDER_AMBER, size=13, symbol="diamond",
                    line=dict(color=INK, width=1.5)),
    ))
    fig.update_xaxes(
        type="log", title="Concentration (x)", gridcolor=GRID, zerolinecolor=GRID,
        color=TEXT_DIM, tickfont=dict(family="IBM Plex Mono, monospace", size=11),
    )
    fig.update_yaxes(
        title="Y_net (RFU)", gridcolor=GRID, zerolinecolor=GRID, color=TEXT_DIM,
        tickfont=dict(family="IBM Plex Mono, monospace", size=11),
    )
    fig.update_layout(
        title=dict(text=f"{substance} · Calibration Curve",
                    font=dict(family="IBM Plex Mono, monospace", size=14, color=TEXT)),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE_INSET,
        font=dict(family="IBM Plex Sans, sans-serif", color=TEXT),
        margin=dict(l=10, r=10, t=44, b=10),
        height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(family="IBM Plex Mono, monospace", size=11)),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ---- Log entry ----
    if st.button("💾 Save to log", use_container_width=True):
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "substance": substance,
            "batch_id": batch_id,
            "machine_id": machine_id,
            "y_raw": y_raw,
            "y_background": y_background,
            "y_net": y_net,
            "concentration_x": x_result,
            "slope_m": model["m"],
            "intercept_b": model["b"],
        }
        st.session_state.log = pd.concat(
            [st.session_state.log, pd.DataFrame([entry])], ignore_index=True
        )
        st.toast("Entry saved to session log.", icon="✅")

# ----------------------------------------------------------------------------
# LOG / TRACEABILITY
# ----------------------------------------------------------------------------
st.markdown('<div class="panel-tag">3 · Data Log &amp; Traceability</div>', unsafe_allow_html=True)

if st.session_state.log.empty:
    st.info("No entries logged yet this session.")
else:
    st.dataframe(st.session_state.log, use_container_width=True, hide_index=True)

    csv_buffer = io.StringIO()
    st.session_state.log.to_csv(csv_buffer, index=False)
    st.download_button(
        "⬇️ Export log as CSV",
        data=csv_buffer.getvalue(),
        file_name=f"pfago_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    if st.button("Clear session log", use_container_width=True):
        st.session_state.log = pd.DataFrame(columns=LOG_COLUMNS)
        st.rerun()

st.markdown(
    """
    <p class="footnote">
    Session log resets on app restart. Export CSV after each session, or wire in a
    persistent store (Google Sheets, Supabase) for permanent cross-session storage.
    </p>
    """,
    unsafe_allow_html=True,
)
