"""
Pfago-Cleavage Cascade — Analytical Concentration Calculator
Streamlit application for calculating Histamine and Malachite Green
concentrations from Pfago-cleavage fluorescent cascade signal data.
"""

import io
import json
import math
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# --------------------------------------------------------------------------
# Paths & constants
# --------------------------------------------------------------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CAL_FILE = os.path.join(APP_DIR, "calibration.json")
LOG_FILE = os.path.join(APP_DIR, "calculation_log.csv")

CAL_PASSWORD_DEFAULT = "pfago-admin"  # override via st.secrets["cal_password"] in production

LOG_COLUMNS = [
    "timestamp",
    "sample_id",
    "substance",
    "machine_id",
    "batch_id",
    "operator",
    "y_raw",
    "y_background",
    "y_net",
    "concentration",
    "unit",
    "slope_m",
    "intercept_b",
]

DEFAULT_CALIBRATION = {
    "Histamine": {
        "m": 13780.0,
        "b": -20930.0,
        "log_type": "log10",
        "unit": "ppm",
        "x_min": 0.01,
        "x_max": 100.0,
    },
    "Malachite Green": {
        "m": 3892.39,
        "b": -4664.89,
        "log_type": "ln",
        "unit": "ppb",
        "x_min": 0.001,
        "x_max": 50.0,
    },
}

# --------------------------------------------------------------------------
# Persistence helpers
# --------------------------------------------------------------------------
def load_calibration() -> dict:
    if os.path.exists(CAL_FILE):
        try:
            with open(CAL_FILE, "r") as f:
                data = json.load(f)
            # Ensure both substances & all keys are present (merge with defaults)
            merged = {}
            for substance, defaults in DEFAULT_CALIBRATION.items():
                merged[substance] = {**defaults, **data.get(substance, {})}
            return merged
        except (json.JSONDecodeError, OSError):
            return json.loads(json.dumps(DEFAULT_CALIBRATION))
    return json.loads(json.dumps(DEFAULT_CALIBRATION))


def save_calibration(cal: dict) -> None:
    try:
        with open(CAL_FILE, "w") as f:
            json.dump(cal, f, indent=2)
    except OSError:
        st.warning(
            "Could not write calibration.json to disk (read-only filesystem?). "
            "Changes will persist for this session only."
        )


def load_log() -> pd.DataFrame:
    if os.path.exists(LOG_FILE):
        try:
            df = pd.read_csv(LOG_FILE)
            for col in LOG_COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            return df[LOG_COLUMNS]
        except (pd.errors.EmptyDataError, OSError):
            return pd.DataFrame(columns=LOG_COLUMNS)
    return pd.DataFrame(columns=LOG_COLUMNS)


def append_log(row: dict) -> None:
    df = load_log()
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    try:
        df.to_csv(LOG_FILE, index=False)
    except OSError:
        pass
    st.session_state["log_df"] = df


# --------------------------------------------------------------------------
# Math
# --------------------------------------------------------------------------
def y_net_from_x(x: np.ndarray, m: float, b: float, log_type: str) -> np.ndarray:
    if log_type == "log10":
        return m * np.log10(x) + b
    return m * np.log(x) + b


def x_from_y_net(y_net: float, m: float, b: float, log_type: str) -> float:
    exponent = (y_net - b) / m
    if log_type == "log10":
        return 10 ** exponent
    return math.exp(exponent)


# --------------------------------------------------------------------------
# Report generation (PDF)
# --------------------------------------------------------------------------
def _render_curve_png(cal_params: dict, x_point: float, y_point: float) -> io.BytesIO:
    """Render the calibration curve + sample point as a PNG for the PDF report."""
    x_min, x_max = cal_params["x_min"], cal_params["x_max"]
    x_curve = np.logspace(np.log10(x_min), np.log10(x_max), 300)
    y_curve = y_net_from_x(x_curve, cal_params["m"], cal_params["b"], cal_params["log_type"])

    fig, ax = plt.subplots(figsize=(5.5, 3.2), dpi=200)
    ax.plot(x_curve, y_curve, color="#2A8C82", linewidth=1.8, label="Calibration curve")
    ax.scatter([x_point], [y_point], color="#C0392B", s=55, zorder=5, marker="D", label="Sample result")
    ax.set_xscale("log")
    ax.set_xlabel(f"Concentration ({cal_params['unit']}, log scale)", fontsize=8)
    ax.set_ylabel("Y_net (RFU)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(True, which="both", linestyle="--", linewidth=0.4, alpha=0.5)
    ax.legend(fontsize=7, loc="best")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_pdf_report(record: dict, cal_params: dict) -> bytes:
    """Build a single-sample lab report PDF and return it as bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Heading1"], fontSize=17, spaceAfter=2, textColor="#0F1720"
    )
    sub_style = ParagraphStyle(
        "ReportSub", parent=styles["Normal"], fontSize=9, textColor="#556270", spaceAfter=14
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading3"], fontSize=11, spaceBefore=14, spaceAfter=6, textColor="#0F1720"
    )
    note_style = ParagraphStyle(
        "Note", parent=styles["Normal"], fontSize=8, textColor="#7C8B99", leading=11
    )

    elements = []
    elements.append(Paragraph("Pfago-Cleavage Cascade — Analytical Report", title_style))
    elements.append(
        Paragraph(
            f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            sub_style,
        )
    )

    # --- Sample identification table ---
    elements.append(Paragraph("Sample identification", section_style))
    id_data = [
        ["Sample ID", record.get("sample_id") or "—"],
        ["Substance", record.get("substance", "—")],
        ["Analysis timestamp", record.get("timestamp", "—")],
        ["Machine ID", record.get("machine_id") or "—"],
        ["Reagent batch ID", record.get("batch_id") or "—"],
        ["Operator", record.get("operator") or "—"],
    ]
    id_table = Table(id_data, colWidths=[1.8 * inch, 4.0 * inch])
    id_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (-1, -1), "#0F1720"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, "#D8DEE4"),
            ]
        )
    )
    elements.append(id_table)

    # --- Signal & result table ---
    elements.append(Paragraph("Signal & result", section_style))
    result_data = [
        ["Y_raw (RFU)", f"{record['y_raw']:.4f}"],
        ["Y_background (RFU)", f"{record['y_background']:.4f}"],
        ["Y_net (RFU)", f"{record['y_net']:.4f}"],
        ["Calibration (m, b)", f"m = {cal_params['m']}, b = {cal_params['b']} ({cal_params['log_type']})"],
        ["Concentration (x)", f"{record['concentration']:.6g} {record['unit']}"],
    ]
    result_table = Table(result_data, colWidths=[1.8 * inch, 4.0 * inch])
    result_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (-1, -1), "#0F1720"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, "#D8DEE4"),
                ("BACKGROUND", (0, 4), (-1, 4), "#EAF7F5"),
            ]
        )
    )
    elements.append(result_table)

    # --- Chart ---
    elements.append(Paragraph("Calibration curve", section_style))
    chart_buf = _render_curve_png(cal_params, record["concentration"], record["y_net"])
    elements.append(Image(chart_buf, width=5.5 * inch, height=3.2 * inch))

    # --- Footer / disclaimer ---
    elements.append(Spacer(1, 16))
    elements.append(
        Paragraph(
            "This calibration is specific to the machine, reagent batch, and assay "
            "conditions under which it was derived. Results are only valid for RFU "
            "readings collected under matching instrument settings, reagent lot, and "
            "reaction conditions. This report is generated automatically from operator-"
            "entered values and should be reviewed by qualified laboratory personnel "
            "before use in downstream decisions.",
            note_style,
        )
    )

    doc.build(elements)
    buf.seek(0)
    return buf.getvalue()


# --------------------------------------------------------------------------
# Page setup & styling
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="Pfago-Cascade Calculator",
    page_icon="🧪",
    layout="centered",
    initial_sidebar_state="collapsed",
)

CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Space+Grotesk:wght@500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'JetBrains Mono', monospace; }
    h1, h2, h3 { font-family: 'Space Grotesk', sans-serif !important; letter-spacing: -0.01em; }

    .stApp { background: radial-gradient(circle at 20% -10%, #16232c 0%, #0F1720 55%); }

    .lab-header {
        display: flex; align-items: baseline; justify-content: space-between;
        border-bottom: 1px solid #24333f; padding-bottom: 10px; margin-bottom: 4px;
    }
    .lab-eyebrow {
        color: #4FD1C5; font-size: 0.75rem; letter-spacing: 0.18em;
        text-transform: uppercase; font-weight: 700;
    }
    .lab-title { font-size: 1.7rem; font-weight: 700; color: #E6EDF3; margin: 2px 0 0 0; }
    .lab-sub { color: #7C8B99; font-size: 0.85rem; margin-top: 4px; }

    .result-card {
        background: linear-gradient(155deg, #16232c 0%, #101a22 100%);
        border: 1px solid #24333f; border-radius: 10px; padding: 18px 20px;
        margin: 10px 0;
    }
    .result-label { color: #7C8B99; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.12em; }
    .result-value { color: #4FD1C5; font-size: 2.1rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; }
    .result-unit { color: #7C8B99; font-size: 1rem; margin-left: 4px; }

    .metric-row { display: flex; gap: 10px; }
    .metric-box {
        flex: 1; background: #131e27; border: 1px solid #24333f; border-radius: 8px;
        padding: 10px 12px;
    }
    .metric-box .k { color: #7C8B99; font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .metric-box .v { color: #E6EDF3; font-size: 1.05rem; font-weight: 600; }

    .warn-box {
        background: #2a1616; border: 1px solid #7a2e2e; border-radius: 8px;
        padding: 12px 14px; color: #ff9d9d; font-size: 0.9rem;
    }
    .info-box {
        background: #16222a; border: 1px solid #24333f; border-radius: 8px;
        padding: 10px 12px; color: #7C8B99; font-size: 0.78rem; line-height: 1.5;
    }

    .stButton>button {
        background: #4FD1C5; color: #0F1720; font-weight: 700; border: none;
        border-radius: 8px; padding: 0.6rem 1rem; width: 100%;
    }
    .stButton>button:hover { background: #6BE0D5; color: #0F1720; }

    div[data-testid="stExpander"] { border: 1px solid #24333f; border-radius: 8px; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Session state init
# --------------------------------------------------------------------------
if "calibration" not in st.session_state:
    st.session_state["calibration"] = load_calibration()
if "log_df" not in st.session_state:
    st.session_state["log_df"] = load_log()
if "cal_unlocked" not in st.session_state:
    st.session_state["cal_unlocked"] = False

cal_password = st.secrets.get("cal_password", CAL_PASSWORD_DEFAULT) if hasattr(st, "secrets") else CAL_PASSWORD_DEFAULT

# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------
st.markdown(
    """
    <div class="lab-header">
        <div>
            <div class="lab-eyebrow">Pfago · Cleavage Cascade</div>
            <div class="lab-title">Concentration Calculator</div>
            <div class="lab-sub">Fluorescence-to-concentration conversion &amp; traceability log</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.write("")

# --------------------------------------------------------------------------
# Substance & run metadata
# --------------------------------------------------------------------------
substance = st.selectbox("Substance", list(DEFAULT_CALIBRATION.keys()))
cal = st.session_state["calibration"][substance]

sample_id = st.text_input(
    "Sample ID",
    value="",
    placeholder="e.g. S-2026-0341",
    help="Unique identifier for this sample — carried through the log and the PDF report.",
)

with st.expander("Run metadata (batch, machine, operator)", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        machine_id = st.text_input("Machine ID", value="", placeholder="e.g. QPCR-04")
        batch_id = st.text_input("Pfago Reagent Batch ID", value="", placeholder="e.g. PF-2026-118")
    with col2:
        operator = st.text_input("Operator", value="", placeholder="Initials")

st.markdown(
    f"""<div class="info-box">
    This tool uses a fixed calibration for <b>{substance}</b>
    (slope m = {cal['m']}, intercept b = {cal['b']}), specific to the machine
    and assay conditions it was derived from. Results are only valid for
    RFU readings collected under matching instrument settings, reagent
    lot, and reaction conditions. Re-calibrate before use on a new
    machine or reagent batch.
    </div>""",
    unsafe_allow_html=True,
)
st.write("")

# --------------------------------------------------------------------------
# Signal inputs
# --------------------------------------------------------------------------
st.markdown("##### Signal input")

y_raw = st.number_input(
    "Raw Fluorescence — Y_raw (RFU)",
    value=0.0,
    step=100.0,
    format="%.4f",
    help="Raw signal reported directly by the fluorescence/PCR instrument.",
)

use_background = st.toggle("Subtract background / blank signal", value=True)

if use_background:
    y_background = st.number_input(
        "Background Noise — Y_background (RFU)",
        value=0.0,
        step=10.0,
        format="%.4f",
        help="Signal from the negative control / blank well.",
    )
else:
    y_background = 0.0

y_net = y_raw - y_background

calc_clicked = st.button("Calculate concentration", type="primary")

if calc_clicked and not sample_id.strip():
    st.markdown(
        '<div class="warn-box">⚠ Invalid Input: Sample ID is required for traceability.</div>',
        unsafe_allow_html=True,
    )
    calc_clicked = False

# --------------------------------------------------------------------------
# Validation + calculation
# --------------------------------------------------------------------------
def render_result(y_net_val, cal_params, substance_name):
    if not np.isfinite(y_net_val):
        st.markdown(
            '<div class="warn-box">⚠ Invalid Input: signal values must be numeric.</div>',
            unsafe_allow_html=True,
        )
        return None

    if y_net_val <= 0:
        st.markdown(
            '<div class="warn-box">⚠ Invalid Input: Corrected signal must be greater than zero.</div>',
            unsafe_allow_html=True,
        )
        return None

    try:
        x_result = x_from_y_net(y_net_val, cal_params["m"], cal_params["b"], cal_params["log_type"])
    except (ValueError, OverflowError, ZeroDivisionError):
        st.markdown(
            '<div class="warn-box">⚠ Invalid Input: could not resolve concentration — check calibration coefficients.</div>',
            unsafe_allow_html=True,
        )
        return None

    if not np.isfinite(x_result) or x_result <= 0:
        st.markdown(
            '<div class="warn-box">⚠ Result out of mathematical bounds (x must be &gt; 0). '
            "Check Y_net and calibration coefficients.</div>",
            unsafe_allow_html=True,
        )
        return None

    unit = cal_params["unit"]
    st.markdown(
        f"""
        <div class="result-card">
            <div class="result-label">Calculated Concentration</div>
            <span class="result-value">{x_result:.4g}</span><span class="result-unit">{unit}</span>
        </div>
        <div class="metric-row">
            <div class="metric-box"><div class="k">Y_raw</div><div class="v">{y_raw:.2f}</div></div>
            <div class="metric-box"><div class="k">Y_background</div><div class="v">{y_background:.2f}</div></div>
            <div class="metric-box"><div class="k">Y_net</div><div class="v">{y_net_val:.2f}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return x_result


x_result = None
if calc_clicked:
    x_result = render_result(y_net, cal, substance)

    if x_result is not None:
        log_row = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "sample_id": sample_id.strip(),
            "substance": substance,
            "machine_id": machine_id,
            "batch_id": batch_id,
            "operator": operator,
            "y_raw": y_raw,
            "y_background": y_background,
            "y_net": y_net,
            "concentration": x_result,
            "unit": cal["unit"],
            "slope_m": cal["m"],
            "intercept_b": cal["b"],
        }
        append_log(log_row)
        st.session_state["last_result"] = (x_result, y_net)
        st.session_state["last_record"] = log_row
        st.session_state["last_cal"] = cal

        pdf_bytes = generate_pdf_report(log_row, cal)
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in sample_id.strip()) or "sample"
        st.download_button(
            "📄 Download PDF report",
            data=pdf_bytes,
            file_name=f"pfago_report_{safe_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

# --------------------------------------------------------------------------
# Chart
# --------------------------------------------------------------------------
st.write("")
st.markdown("##### Calibration curve")

x_min, x_max = cal["x_min"], cal["x_max"]
x_curve = np.logspace(np.log10(x_min), np.log10(x_max), 300)
y_curve = y_net_from_x(x_curve, cal["m"], cal["b"], cal["log_type"])

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=x_curve,
        y=y_curve,
        mode="lines",
        name=f"{substance} calibration",
        line=dict(color="#4FD1C5", width=2.5),
    )
)

plotted_x = None
plotted_y = None
if x_result is not None:
    plotted_x, plotted_y = x_result, y_net
elif "last_result" in st.session_state:
    plotted_x, plotted_y = st.session_state["last_result"]

if plotted_x is not None and plotted_x > 0:
    fig.add_trace(
        go.Scatter(
            x=[plotted_x],
            y=[plotted_y],
            mode="markers",
            name="Sample result",
            marker=dict(color="#FF6B6B", size=13, symbol="diamond", line=dict(color="white", width=1)),
        )
    )

fig.update_layout(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    height=380,
    margin=dict(l=10, r=10, t=30, b=10),
    xaxis=dict(title=f"Concentration ({cal['unit']}, log scale)", type="log", gridcolor="#24333f"),
    yaxis=dict(title="Y_net (RFU)", gridcolor="#24333f"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    font=dict(family="JetBrains Mono, monospace", color="#E6EDF3", size=11),
)
st.plotly_chart(fig, use_container_width=True)

if calc_clicked is False and "last_record" in st.session_state:
    with st.expander(f"📄 Report available — Sample {st.session_state['last_record'].get('sample_id', '—')}"):
        st.caption("Re-download the PDF report for the most recent calculation this session.")
        pdf_bytes = generate_pdf_report(st.session_state["last_record"], st.session_state["last_cal"])
        safe_id = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in (st.session_state["last_record"].get("sample_id") or "sample")
        )
        st.download_button(
            "📄 Download PDF report",
            data=pdf_bytes,
            file_name=f"pfago_report_{safe_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf",
            use_container_width=True,
            key="repeat_pdf_download",
        )

# --------------------------------------------------------------------------
# Calibration management (password-gated)
# --------------------------------------------------------------------------
st.write("")
with st.expander("⚙️ Calibration management (authorized access)"):
    if not st.session_state["cal_unlocked"]:
        pw = st.text_input("Calibration password", type="password", key="cal_pw_input")
        if st.button("Unlock calibration settings"):
            if pw == cal_password:
                st.session_state["cal_unlocked"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    else:
        st.success("Calibration settings unlocked for this session.")
        edit_substance = st.selectbox(
            "Substance to edit", list(DEFAULT_CALIBRATION.keys()), key="edit_substance"
        )
        edit_cal = st.session_state["calibration"][edit_substance]

        new_m = st.number_input("Slope (m)", value=float(edit_cal["m"]), format="%.5f")
        new_b = st.number_input("Intercept (b)", value=float(edit_cal["b"]), format="%.5f")
        new_log_type = st.selectbox(
            "Log function",
            ["log10", "ln"],
            index=["log10", "ln"].index(edit_cal["log_type"]),
        )
        new_unit = st.text_input("Concentration unit", value=edit_cal["unit"])
        c1, c2 = st.columns(2)
        with c1:
            new_x_min = st.number_input("Chart x-min", value=float(edit_cal["x_min"]), format="%.5f")
        with c2:
            new_x_max = st.number_input("Chart x-max", value=float(edit_cal["x_max"]), format="%.5f")

        if st.button("Save calibration"):
            if new_m == 0:
                st.error("Slope (m) cannot be zero.")
            elif new_x_min <= 0 or new_x_max <= new_x_min:
                st.error("Chart bounds must satisfy 0 < x-min < x-max.")
            else:
                st.session_state["calibration"][edit_substance] = {
                    "m": new_m,
                    "b": new_b,
                    "log_type": new_log_type,
                    "unit": new_unit,
                    "x_min": new_x_min,
                    "x_max": new_x_max,
                }
                save_calibration(st.session_state["calibration"])
                st.success(f"Calibration for {edit_substance} updated.")

        if st.button("Reset to factory defaults"):
            st.session_state["calibration"] = json.loads(json.dumps(DEFAULT_CALIBRATION))
            save_calibration(st.session_state["calibration"])
            st.success("Calibration reset to factory defaults.")
            st.rerun()

        if st.button("Lock calibration settings"):
            st.session_state["cal_unlocked"] = False
            st.rerun()

# --------------------------------------------------------------------------
# Data log & traceability
# --------------------------------------------------------------------------
st.write("")
st.markdown("##### Traceability log")

log_df = st.session_state["log_df"]
if log_df.empty:
    st.markdown(
        '<div class="info-box">No calculations logged yet. Every calculation you run is '
        "recorded here with a timestamp, metadata, and full variable trail.</div>",
        unsafe_allow_html=True,
    )
else:
    st.dataframe(log_df.sort_values("timestamp", ascending=False), use_container_width=True, height=240)

    csv_buffer = io.StringIO()
    log_df.to_csv(csv_buffer, index=False)
    st.download_button(
        "Download full log (CSV)",
        data=csv_buffer.getvalue(),
        file_name=f"pfago_cascade_log_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    with st.expander("Clear log (authorized access)"):
        clear_pw = st.text_input("Password to clear log", type="password", key="clear_pw")
        if st.button("Clear all log entries", type="secondary"):
            if clear_pw == cal_password:
                empty_df = pd.DataFrame(columns=LOG_COLUMNS)
                st.session_state["log_df"] = empty_df
                try:
                    empty_df.to_csv(LOG_FILE, index=False)
                except OSError:
                    pass
                st.success("Log cleared.")
                st.rerun()
            else:
                st.error("Incorrect password.")

st.markdown(
    """
    <div class="info-box" style="margin-top:18px;">
    <b>Note on persistence:</b> when deployed on Streamlit Community Cloud, the container
    filesystem is ephemeral and may reset on redeploy or sleep/wake cycles. Download the CSV
    log regularly, or connect a persistent store (e.g. Google Sheets via <code>gspread</code>,
    or a hosted database) for permanent record-keeping in a production lab setting.
    </div>
    """,
    unsafe_allow_html=True,
)
