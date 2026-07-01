"""
Pfago-Cleavage Cascade Concentration Calculator
------------------------------------------------
Flow: Sample ID -> Histamine input + Malachite Green input -> Calculate ->
two concentration outputs -> Generate report -> Other details (batch/machine/
background/calibration/history-by-user).

Root cause of the earlier visual bug: raw CSS was passed through
st.markdown(unsafe_allow_html=True). Streamlit runs that string through a
markdown parser first, and blank lines inside the <style> block caused the
parser to break out of "raw HTML" mode partway through, so half the CSS was
printed as literal page text. Fix: st.html() injects raw HTML/CSS directly,
with no markdown pass, so this can't happen again.
"""

import io
import math
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Pfago Concentration Calculator",
    page_icon="🧪",
    layout="centered",
)

CALIB_PASSWORD = "admin123"  # demo only — replace with st.secrets in production
LOG_COLUMNS = [
    "timestamp", "user", "sample_id", "substance", "batch_id", "machine_id",
    "y_raw", "y_background", "y_net", "concentration_x",
]

# ---- palette / type (kept simple & flat this time — no page-wide grid) ----
INK = "#12181B"
SURFACE = "#1B2328"
SURFACE_INSET = "#0E1315"
BORDER = "#2A363B"
GREEN = "#6EE7B7"     # Histamine accent
AMBER = "#F5A623"     # Malachite Green accent
TEXT = "#EDEFEE"
TEXT_DIM = "#8B9A9E"

DEFAULT_MODELS = {
    "Histamine": {"type": "log10", "m": 13780.0, "b": -20930.0, "units": "µM", "color": GREEN},
    "Malachite Green": {"type": "ln", "m": 3892.39, "b": -4664.89, "units": "µM", "color": AMBER},
}

# ---- session state ----
ss = st.session_state
ss.setdefault("models", {k: v.copy() for k, v in DEFAULT_MODELS.items()})
ss.setdefault("log", pd.DataFrame(columns=LOG_COLUMNS))
ss.setdefault("calib_unlocked", False)
ss.setdefault("results", None)  # dict of substance -> result dict, or None
# pre-register keys for widgets that render lower on the page but are needed
# earlier in the script (Streamlit keeps these across reruns once set)
ss.setdefault("batch_id", "")
ss.setdefault("machine_id", "")
ss.setdefault("bg_hist", 0.0)
ss.setdefault("bg_mg", 0.0)
ss.setdefault("use_bg_hist", False)
ss.setdefault("use_bg_mg", False)


def inject_style():
    st.html(f"""
    <style>
    [data-testid="stAppViewContainer"] {{ background-color: {INK}; }}
    [data-testid="stHeader"] {{ background-color: transparent; }}
    * {{ font-family: 'IBM Plex Sans', -apple-system, sans-serif; }}
    .mono {{ font-family: 'IBM Plex Mono', monospace; }}
    .nameplate {{ border: 1px solid {BORDER}; background: {SURFACE}; border-radius: 6px; padding: 16px 20px; margin-bottom: 14px; }}
    .nameplate .eyebrow {{ font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: .16em; color: {GREEN}; text-transform: uppercase; }}
    .nameplate h1 {{ font-size: 24px; font-weight: 600; margin: 4px 0 0 0; color: {TEXT}; }}
    .section-tag {{ font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: .12em; text-transform: uppercase; color: {TEXT_DIM}; border-left: 3px solid {GREEN}; padding-left: 8px; margin: 20px 0 8px 0; }}
    .readout {{ background: {SURFACE_INSET}; border: 1px solid {BORDER}; border-radius: 6px; padding: 14px 16px; margin-bottom: 8px; }}
    .readout .label {{ font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: .12em; text-transform: uppercase; color: {TEXT_DIM}; }}
    .readout .value {{ font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; font-size: 30px; font-weight: 600; line-height: 1.3; }}
    .readout .unit {{ font-family: 'IBM Plex Mono', monospace; font-size: 13px; color: {TEXT_DIM}; margin-left: 6px; }}
    .readout .error {{ font-family: 'IBM Plex Mono', monospace; font-size: 13px; color: #F2555A; }}
    [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input {{ background-color: {SURFACE_INSET} !important; border: 1px solid {BORDER} !important; border-radius: 4px !important; }}
    div.stButton > button, [data-testid="stDownloadButton"] button {{ background-color: {SURFACE}; color: {GREEN}; border: 1px solid {GREEN}; border-radius: 4px; font-family: 'IBM Plex Mono', monospace; }}
    div.stButton > button:hover, [data-testid="stDownloadButton"] button:hover {{ background-color: {GREEN}; color: {INK}; }}
    </style>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
    """)


def readout(label, value_html, unit="", color=TEXT, error=None):
    if error:
        st.html(f'<div class="readout"><div class="label">{label}</div><div class="error">{error}</div></div>')
    else:
        st.html(
            f'<div class="readout"><div class="label">{label}</div>'
            f'<div class="value" style="color:{color}">{value_html}<span class="unit">{unit}</span></div></div>'
        )


def forward_y(x, m, b, ftype):
    return m * math.log10(x) + b if ftype == "log10" else m * math.log(x) + b


def solve_x(y_net, m, b, ftype):
    exponent = (y_net - b) / m
    return 10 ** exponent if ftype == "log10" else math.exp(exponent)


def compute(substance, y_raw, y_bg):
    model = ss.models[substance]
    y_net = y_raw - y_bg
    if y_net <= 0:
        return {"y_raw": y_raw, "y_bg": y_bg, "y_net": y_net, "x": None,
                "error": "Invalid: Y_net must be > 0"}
    if model["m"] == 0:
        return {"y_raw": y_raw, "y_bg": y_bg, "y_net": y_net, "x": None,
                "error": "Invalid calibration: slope is 0"}
    try:
        x = solve_x(y_net, model["m"], model["b"], model["type"])
        if x <= 0 or math.isnan(x) or math.isinf(x):
            return {"y_raw": y_raw, "y_bg": y_bg, "y_net": y_net, "x": None,
                    "error": "Non-physical result"}
    except (ValueError, OverflowError, ZeroDivisionError) as e:
        return {"y_raw": y_raw, "y_bg": y_bg, "y_net": y_net, "x": None, "error": str(e)}
    return {"y_raw": y_raw, "y_bg": y_bg, "y_net": y_net, "x": x, "error": None}


# ============================================================ RENDER =====
inject_style()

st.html(
    '<div class="nameplate"><div class="eyebrow">Pfago · Cleavage Cascade Assay</div>'
    '<h1>Concentration Calculator</h1></div>'
)
st.warning(
    "Calibration curves are specific to the instrument, reagent lot, and assay "
    "conditions they were derived from. Re-calibrate before use elsewhere.",
    icon="⚠️",
)

st.html('<div class="section-tag">Sample</div>')
c1, c2 = st.columns(2)
sample_id = c1.text_input("Sample ID", placeholder="e.g. S-0142")
user_name = c2.text_input("Analyst / User ID", placeholder="e.g. jlu")

st.html('<div class="section-tag">Histamine</div>')
y_raw_hist = st.number_input("Raw Fluorescence — Y_raw (RFU)", value=0.0, format="%.4f", key="yraw_hist")

st.html('<div class="section-tag">Malachite Green</div>')
y_raw_mg = st.number_input("Raw Fluorescence — Y_raw (RFU)", value=0.0, format="%.4f", key="yraw_mg")

calc_clicked = st.button("▶ Calculate", use_container_width=True)

if calc_clicked:
    bg_h = ss.bg_hist if ss.use_bg_hist else 0.0
    bg_m = ss.bg_mg if ss.use_bg_mg else 0.0
    ss.results = {
        "Histamine": compute("Histamine", y_raw_hist, bg_h),
        "Malachite Green": compute("Malachite Green", y_raw_mg, bg_m),
    }
    rows = []
    ts = datetime.now().isoformat(timespec="seconds")
    for substance, r in ss.results.items():
        if r["x"] is not None:
            rows.append({
                "timestamp": ts, "user": user_name, "sample_id": sample_id,
                "substance": substance, "batch_id": ss.batch_id, "machine_id": ss.machine_id,
                "y_raw": r["y_raw"], "y_background": r["y_bg"], "y_net": r["y_net"],
                "concentration_x": r["x"],
            })
    if rows:
        ss.log = pd.concat([ss.log, pd.DataFrame(rows)], ignore_index=True)
        st.toast("Saved to history.", icon="✅")

st.html('<div class="section-tag">Result</div>')
rc1, rc2 = st.columns(2)
with rc1:
    if ss.results is None:
        readout("Histamine — x", "—", unit=ss.models["Histamine"]["units"], color=GREEN)
    else:
        r = ss.results["Histamine"]
        if r["x"] is None:
            readout("Histamine — x", "", error=r["error"])
        else:
            readout("Histamine — x", f"{r['x']:,.6g}", unit=ss.models["Histamine"]["units"], color=GREEN)
with rc2:
    if ss.results is None:
        readout("Malachite Green — x", "—", unit=ss.models["Malachite Green"]["units"], color=AMBER)
    else:
        r = ss.results["Malachite Green"]
        if r["x"] is None:
            readout("Malachite Green — x", "", error=r["error"])
        else:
            readout("Malachite Green — x", f"{r['x']:,.6g}", unit=ss.models["Malachite Green"]["units"], color=AMBER)

# ---- optional curve view ----
if ss.results is not None:
    valid_subs = [s for s, r in ss.results.items() if r["x"] is not None]
    if valid_subs:
        with st.expander("View calibration curve"):
            pick = st.radio("Substance", valid_subs, horizontal=True) if len(valid_subs) > 1 else valid_subs[0]
            model = ss.models[pick]
            r = ss.results[pick]
            x_lo, x_hi = 1e-3, max(1e2, r["x"] * 10)
            x_lo = min(x_lo, r["x"] / 10)
            x_vals = [x_lo * (x_hi / x_lo) ** (i / 200) for i in range(201)]
            y_vals = [forward_y(xv, model["m"], model["b"], model["type"]) for xv in x_vals]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=x_vals, y=y_vals, mode="lines", name="Curve",
                                      line=dict(color=model["color"], width=2.5)))
            fig.add_trace(go.Scatter(x=[r["x"]], y=[r["y_net"]], mode="markers", name="Sample",
                                      marker=dict(color=AMBER if pick == "Histamine" else GREEN, size=13, symbol="diamond")))
            fig.update_xaxes(type="log", title="Concentration (x)", gridcolor=BORDER, color=TEXT_DIM)
            fig.update_yaxes(title="Y_net (RFU)", gridcolor=BORDER, color=TEXT_DIM)
            fig.update_layout(paper_bgcolor=SURFACE, plot_bgcolor=SURFACE_INSET,
                               font=dict(family="IBM Plex Sans, sans-serif", color=TEXT),
                               margin=dict(l=10, r=10, t=30, b=10), height=340)
            st.plotly_chart(fig, use_container_width=True)

# ---- generate report ----
report_ready = ss.results is not None and any(r["x"] is not None for r in ss.results.values())
if report_ready:
    lines = [
        "PFAGO-CLEAVAGE CASCADE ASSAY — ANALYSIS REPORT",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Sample ID: {sample_id or '—'}",
        f"Analyst: {user_name or '—'}",
        f"Batch ID: {ss.batch_id or '—'}    Machine ID: {ss.machine_id or '—'}",
        "-" * 50,
    ]
    for substance, r in ss.results.items():
        lines.append(f"{substance}:")
        lines.append(f"  Y_raw = {r['y_raw']:.4f} RFU   Y_background = {r['y_bg']:.4f} RFU")
        lines.append(f"  Y_net = {r['y_net']:.4f} RFU")
        if r["x"] is not None:
            lines.append(f"  Concentration x = {r['x']:.6g} {ss.models[substance]['units']}")
        else:
            lines.append(f"  Concentration x = INVALID ({r['error']})")
        lines.append("")
    report_text = "\n".join(lines)
    st.download_button("📄 Generate Report", data=report_text,
                        file_name=f"pfago_report_{(sample_id or 'sample')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                        mime="text/plain", use_container_width=True)
else:
    st.button("📄 Generate Report", disabled=True, use_container_width=True,
               help="Run Calculate with at least one valid result first.")

# ---- other details ----
with st.expander("Other details"):
    st.html('<div class="section-tag">Batch &amp; Machine</div>')
    oc1, oc2 = st.columns(2)
    ss.batch_id = oc1.text_input("Pfago Reagent Batch ID", value=ss.batch_id)
    ss.machine_id = oc2.text_input("Machine ID", value=ss.machine_id)

    st.html('<div class="section-tag">Background Signal</div>')
    bc1, bc2 = st.columns(2)
    with bc1:
        ss.use_bg_hist = st.checkbox("Subtract background — Histamine", value=ss.use_bg_hist)
        if ss.use_bg_hist:
            ss.bg_hist = st.number_input("Y_background — Histamine (RFU)", value=ss.bg_hist, format="%.4f", key="bgnum_hist")
    with bc2:
        ss.use_bg_mg = st.checkbox("Subtract background — Malachite Green", value=ss.use_bg_mg)
        if ss.use_bg_mg:
            ss.bg_mg = st.number_input("Y_background — Malachite Green (RFU)", value=ss.bg_mg, format="%.4f", key="bgnum_mg")

    st.html('<div class="section-tag">Calibration (advanced)</div>')
    if not ss.calib_unlocked:
        pw = st.text_input("Calibration password", type="password", key="calib_pw")
        if st.button("Unlock calibration"):
            if pw == CALIB_PASSWORD:
                ss.calib_unlocked = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    else:
        st.success("Calibration unlocked")
        for substance, model in ss.models.items():
            mc1, mc2 = st.columns(2)
            new_m = mc1.number_input(f"Slope (m) — {substance}", value=float(model["m"]), key=f"m_{substance}")
            new_b = mc2.number_input(f"Intercept (b) — {substance}", value=float(model["b"]), key=f"b_{substance}")
            if new_m != 0:
                ss.models[substance]["m"] = new_m
                ss.models[substance]["b"] = new_b
        if st.button("Reset calibration to defaults"):
            ss.models = {k: v.copy() for k, v in DEFAULT_MODELS.items()}
            st.rerun()
        if st.button("Lock calibration"):
            ss.calib_unlocked = False
            st.rerun()

    st.html('<div class="section-tag">History</div>')
    my_log = ss.log[ss.log["user"] == user_name] if user_name else ss.log.iloc[0:0]
    if user_name == "":
        st.info("Enter an Analyst / User ID above to view your history.")
    elif my_log.empty:
        st.info("No entries logged yet for this user.")
    else:
        st.dataframe(my_log, use_container_width=True, hide_index=True)
        buf = io.StringIO()
        my_log.to_csv(buf, index=False)
        st.download_button("⬇️ Export my history as CSV", data=buf.getvalue(),
                            file_name=f"pfago_history_{user_name}.csv", mime="text/csv",
                            use_container_width=True)
    if st.button("Clear all history (all users)"):
        ss.log = pd.DataFrame(columns=LOG_COLUMNS)
        st.rerun()
