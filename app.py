"""
Pfago-Cleavage Cascade — Analytical Concentration Calculator
Simultaneous Histamine (HEX channel) & Malachite Green (FAM channel)
concentration calculator from Pfago-cleavage fluorescent cascade data.
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
    "machine_id",
    "batch_id",
    "operator",
    "hex_y_raw",
    "hex_y_background",
    "hex_y_net",
    "histamine_concentration",
    "histamine_unit",
    "histamine_slope",
    "histamine_intercept",
    "fam_y_raw",
    "fam_y_background",
    "fam_y_net",
    "malachite_green_concentration",
    "mg_unit",
    "mg_slope",
    "mg_intercept",
]

# Calibration derived from linear regression of Y_net (background-subtracted
# signal) against log10(concentration in nM), fitted from lab calibration
# curves for each fluorescence channel.
DEFAULT_CALIBRATION = {
    "Histamine": {
        "channel": "HEX",
        "m": 32355.0,
        "b": 44788.0,
        "log_type": "log10",
        "unit": "nM",
        "x_min": 0.05,
        "x_max": 30.0,
        "r_squared": 0.9328,
    },
    "Malachite Green": {
        "channel": "FAM",
        "m": 41396.0,
        "b": 44245.0,
        "log_type": "log10",
        "unit": "nM",
        "x_min": 0.05,
        "x_max": 30.0,
        "r_squared": 0.9163,
    },
}

SUBSTANCES = list(DEFAULT_CALIBRATION.keys())

# --------------------------------------------------------------------------
# Persistence helpers
# --------------------------------------------------------------------------
def load_calibration() -> dict:
    if os.path.exists(CAL_FILE):
        try:
            with open(CAL_FILE, "r") as f:
                data = json.load(f)
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
def y_net_from_x(x, m: float, b: float, log_type: str):
    if log_type == "log10":
        return m * np.log10(x) + b
    return m * np.log(x) + b


def x_from_y_net(y_net: float, m: float, b: float, log_type: str) -> float:
    exponent = (y_net - b) / m
    if log_type == "log10":
        return 10 ** exponent
    return math.exp(exponent)


def compute_channel(y_raw: float, y_background: float, cal_params: dict):
    """Returns (y_net, x_result, error_message) for one channel."""
    y_net = y_raw - y_background
    if not np.isfinite(y_net):
        return y_net, None, "Signal values must be numeric."
    if y_net <= 0:
        return y_net, None, "Corrected signal must be greater than zero."
    try:
        x = x_from_y_net(y_net, cal_params["m"], cal_params["b"], cal_params["log_type"])
    except (ValueError, OverflowError, ZeroDivisionError):
        return y_net, None, "Could not resolve concentration — check calibration."
    if not np.isfinite(x) or x <= 0:
        return y_net, None, "Result out of mathematical bounds (x must be > 0)."
    return y_net, x, None


# --------------------------------------------------------------------------
# Report generation (PDF)
# --------------------------------------------------------------------------
def _render_curve_png(cal_params: dict, x_point, y_point, title: str) -> io.BytesIO:
    x_min, x_max = cal_params["x_min"], cal_params["x_max"]
    x_curve = np.logspace(np.log10(x_min), np.log10(x_max), 300)
    y_curve = y_net_from_x(x_curve, cal_params["m"], cal_params["b"], cal_params["log_type"])

    fig, ax = plt.subplots(figsize=(5.3, 2.8), dpi=200)
    ax.plot(x_curve, y_curve, color="#2A8C82", linewidth=1.8, label="Calibration curve")
    if x_point is not None and x_point > 0:
        ax.scatter([x_point], [y_point], color="#C0392B", s=55, zorder=5, marker="D", label="Sample result")
    ax.set_xscale("log")
    ax.set_title(title, fontsize=9)
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


def generate_pdf_report(meta: dict, hex_data: dict, fam_data: dict, hex_cal: dict, fam_cal: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.55 * inch, bottomMargin=0.55 * inch,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("T", parent=styles["Heading1"], fontSize=16, spaceAfter=2, textColor="#0F1720")
    sub_style = ParagraphStyle("S", parent=styles["Normal"], fontSize=9, textColor="#556270", spaceAfter=12)
    section_style = ParagraphStyle("Sec", parent=styles["Heading3"], fontSize=11, spaceBefore=12, spaceAfter=5, textColor="#0F1720")
    note_style = ParagraphStyle("N", parent=styles["Normal"], fontSize=8, textColor="#7C8B99", leading=11)
    body_style = ParagraphStyle("B", parent=styles["Normal"], fontSize=9, textColor="#0F1720", leading=13)

    def fmt_conc(x, unit):
        return f"{x:.6g} {unit}" if x is not None else "Invalid (Y_net ≤ 0)"

    elements = []
    elements.append(Paragraph("Pfago-Cleavage Cascade — Analytical Report", title_style))
    elements.append(Paragraph(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", sub_style))

    elements.append(Paragraph("Sample identification", section_style))
    id_data = [
        ["Sample ID", meta.get("sample_id") or "—"],
        ["Analysis timestamp", meta.get("timestamp", "—")],
        ["Machine ID", meta.get("machine_id") or "—"],
        ["Reagent batch ID", meta.get("batch_id") or "—"],
        ["Operator", meta.get("operator") or "—"],
    ]
    id_table = Table(id_data, colWidths=[1.8 * inch, 4.2 * inch])
    id_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, "#D8DEE4"),
    ]))
    elements.append(id_table)

    for label, chan, data, cal in [
        ("Histamine (HEX channel)", "HEX", hex_data, hex_cal),
        ("Malachite Green (FAM channel)", "FAM", fam_data, fam_cal),
    ]:
        elements.append(Paragraph(label, section_style))
        rows = [
            ["Y_raw (RFU)", f"{data['y_raw']:.4f}"],
            ["Y_background (RFU)", f"{data['y_background']:.4f}"],
            ["Y_net (RFU)", f"{data['y_net']:.4f}"],
            ["Calibration (m, b)", f"m = {cal['m']}, b = {cal['b']} (log10 fit, R² = {cal['r_squared']})"],
            ["Concentration (x)", fmt_conc(data["x"], cal["unit"])],
        ]
        t = Table(rows, colWidths=[1.8 * inch, 4.2 * inch])
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, "#D8DEE4"),
            ("BACKGROUND", (0, 4), (-1, 4), "#EAF7F5"),
        ]))
        elements.append(t)
        chart_buf = _render_curve_png(cal, data["x"], data["y_net"], f"{label} calibration curve")
        elements.append(Image(chart_buf, width=5.3 * inch, height=2.8 * inch))
        elements.append(Spacer(1, 6))

    elements.append(Paragraph("How the concentration is calculated", section_style))
    elements.append(Paragraph(
        "For each channel, the corrected signal is first computed as "
        "Y_net = Y_raw − Y_background. Each channel's calibration curve was "
        "fit as a linear regression of Y_net against log10(concentration), "
        "of the form Y_net = m · log10(x) + b, where x is concentration in nM. "
        "Solving for x gives the concentration reported above: "
        "x = 10 ^ ((Y_net − b) / m). The Histamine (HEX) calibration used "
        f"m = {hex_cal['m']}, b = {hex_cal['b']} (R² = {hex_cal['r_squared']}); the "
        f"Malachite Green (FAM) calibration used m = {fam_cal['m']}, b = {fam_cal['b']} "
        f"(R² = {fam_cal['r_squared']}). If a channel's Y_net is zero or negative, "
        "the log is undefined and no concentration is reported for that channel.",
        body_style,
    ))

    elements.append(Spacer(1, 12))
    elements.append(Paragraph(
        "This calibration is specific to the machine, reagent batch, and assay "
        "conditions under which it was derived. Results are only valid for RFU "
        "readings collected under matching instrument settings, reagent lot, and "
        "reaction conditions. This report is generated automatically from operator-"
        "entered values and should be reviewed by qualified laboratory personnel "
        "before use in downstream decisions.",
        note_style,
    ))

    doc.build(elements)
    buf.seek(0)
    return buf.getvalue()


# --------------------------------------------------------------------------
# Page setup & styling (compact, mobile-first)
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
    h1, h2, h3, h4, h5 { font-family: 'Space Grotesk', sans-serif !important; letter-spacing: -0.01em; }

    .stApp { background: radial-gradient(circle at 20% -10%, #16232c 0%, #0F1720 55%); }
    .block-container { padding-top: 1.1rem !important; padding-bottom: 1rem !important; max-width: 640px; }
    div[data-testid="stVerticalBlock"] > div { gap: 0.35rem; }

    .lab-title { font-size: 1.3rem; font-weight: 700; color: #E6EDF3; margin: 0; }
    .lab-sub { color: #7C8B99; font-size: 0.72rem; margin: 0 0 6px 0; }

    .chan-header {
        font-size: 0.78rem; font-weight: 700; color: #4FD1C5;
        text-transform: uppercase; letter-spacing: 0.08em; margin: 6px 0 2px 0;
    }

    .result-card {
        background: linear-gradient(155deg, #16232c 0%, #101a22 100%);
        border: 1px solid #24333f; border-radius: 8px; padding: 10px 14px; margin: 4px 0 8px 0;
    }
    .result-label { color: #7C8B99; font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .result-value { color: #4FD1C5; font-size: 1.55rem; font-weight: 700; }
    .result-unit { color: #7C8B99; font-size: 0.85rem; margin-left: 3px; }
    .result-net { color: #7C8B99; font-size: 0.7rem; margin-top: 2px; }

    .warn-box {
        background: #2a1616; border: 1px solid #7a2e2e; border-radius: 8px;
        padding: 8px 12px; color: #ff9d9d; font-size: 0.78rem; margin: 4px 0 8px 0;
    }
    .info-box {
        background: #16222a; border: 1px solid #24333f; border-radius: 8px;
        padding: 8px 10px; color: #7C8B99; font-size: 0.7rem; line-height: 1.4;
    }

    .stButton>button {
        background: #4FD1C5; color: #0F1720; font-weight: 700; border: none;
        border-radius: 8px; padding: 0.5rem 1rem; width: 100%; font-size: 0.9rem;
    }
    .stButton>button:hover { background: #6BE0D5; color: #0F1720; }

    div[data-testid="stNumberInput"] label, div[data-testid="stTextInput"] label {
        font-size: 0.72rem !important; color: #9AA7B2 !important;
    }
    div[data-testid="stExpander"] { border: 1px solid #24333f; border-radius: 8px; margin: 4px 0; }
    hr { margin: 10px 0 !important; border-color: #24333f !important; }
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
hex_cal = st.session_state["calibration"]["Histamine"]
fam_cal = st.session_state["calibration"]["Malachite Green"]

# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------
st.markdown(
    '<div class="lab-title">🧪 Pfago-Cascade Calculator</div>'
    '<div class="lab-sub">Histamine (HEX) &amp; Malachite Green (FAM) concentration</div>',
    unsafe_allow_html=True,
)

with st.expander("Other info (machine, batch, operator)", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        machine_id = st.text_input("Machine ID", value="", placeholder="e.g. QPCR-04")
        batch_id = st.text_input("Reagent Batch ID", value="", placeholder="e.g. PF-2026-118")
    with c2:
        operator = st.text_input("Operator", value="", placeholder="Initials")

sample_id = st.text_input("Sample ID", value="", placeholder="e.g. S-2026-0341")

# --------------------------------------------------------------------------
# Signal inputs — both channels visible together, no substance selector
# --------------------------------------------------------------------------
st.markdown('<div class="chan-header">Histamine — HEX channel</div>', unsafe_allow_html=True)
h1, h2 = st.columns(2)
with h1:
    hex_raw = st.number_input("Raw RFU", value=0.0, step=100.0, format="%.2f", key="hex_raw")
with h2:
    hex_bg = st.number_input("Background RFU", value=0.0, step=10.0, format="%.2f", key="hex_bg")

st.markdown('<div class="chan-header">Malachite Green — FAM channel</div>', unsafe_allow_html=True)
f1, f2 = st.columns(2)
with f1:
    fam_raw = st.number_input("Raw RFU", value=0.0, step=100.0, format="%.2f", key="fam_raw")
with f2:
    fam_bg = st.number_input("Background RFU", value=0.0, step=10.0, format="%.2f", key="fam_bg")

generate_clicked = st.button("Generate report", type="primary")

# --------------------------------------------------------------------------
# Calculate + display + log + PDF
# --------------------------------------------------------------------------
def render_channel_result(name: str, unit: str, y_net, x, error):
    if error:
        st.markdown(f'<div class="warn-box">⚠ {name}: {error}</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            f"""<div class="result-card">
                <div class="result-label">{name}</div>
                <span class="result-value">{x:.4g}</span><span class="result-unit">{unit}</span>
                <div class="result-net">Y_net = {y_net:.2f} RFU</div>
            </div>""",
            unsafe_allow_html=True,
        )


if generate_clicked and not sample_id.strip():
    st.markdown('<div class="warn-box">⚠ Sample ID is required for traceability.</div>', unsafe_allow_html=True)
    generate_clicked = False

if generate_clicked:
    hex_y_net, hex_x, hex_err = compute_channel(hex_raw, hex_bg, hex_cal)
    fam_y_net, fam_x, fam_err = compute_channel(fam_raw, fam_bg, fam_cal)

    render_channel_result("Histamine (HEX)", hex_cal["unit"], hex_y_net, hex_x, hex_err)
    render_channel_result("Malachite Green (FAM)", fam_cal["unit"], fam_y_net, fam_x, fam_err)

    meta = {
        "sample_id": sample_id.strip(),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "machine_id": machine_id,
        "batch_id": batch_id,
        "operator": operator,
    }
    hex_data = {"y_raw": hex_raw, "y_background": hex_bg, "y_net": hex_y_net, "x": hex_x}
    fam_data = {"y_raw": fam_raw, "y_background": fam_bg, "y_net": fam_y_net, "x": fam_x}

    log_row = {
        "timestamp": meta["timestamp"],
        "sample_id": meta["sample_id"],
        "machine_id": machine_id,
        "batch_id": batch_id,
        "operator": operator,
        "hex_y_raw": hex_raw,
        "hex_y_background": hex_bg,
        "hex_y_net": hex_y_net,
        "histamine_concentration": hex_x if hex_x is not None else "",
        "histamine_unit": hex_cal["unit"],
        "histamine_slope": hex_cal["m"],
        "histamine_intercept": hex_cal["b"],
        "fam_y_raw": fam_raw,
        "fam_y_background": fam_bg,
        "fam_y_net": fam_y_net,
        "malachite_green_concentration": fam_x if fam_x is not None else "",
        "mg_unit": fam_cal["unit"],
        "mg_slope": fam_cal["m"],
        "mg_intercept": fam_cal["b"],
    }
    append_log(log_row)
    st.session_state["last_meta"] = meta
    st.session_state["last_hex"] = hex_data
    st.session_state["last_fam"] = fam_data

    pdf_bytes = generate_pdf_report(meta, hex_data, fam_data, hex_cal, fam_cal)
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in sample_id.strip()) or "sample"
    st.download_button(
        "📄 Download PDF report",
        data=pdf_bytes,
        file_name=f"pfago_report_{safe_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
elif "last_meta" in st.session_state:
    with st.expander(f"📄 Last report — Sample {st.session_state['last_meta'].get('sample_id', '—')}"):
        pdf_bytes = generate_pdf_report(
            st.session_state["last_meta"], st.session_state["last_hex"], st.session_state["last_fam"], hex_cal, fam_cal
        )
        safe_id = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in (st.session_state["last_meta"].get("sample_id") or "sample")
        )
        st.download_button(
            "📄 Re-download PDF report", data=pdf_bytes,
            file_name=f"pfago_report_{safe_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf", use_container_width=True, key="repeat_pdf",
        )

# --------------------------------------------------------------------------
# Calibration management (password-gated, collapsed, below the fold)
# --------------------------------------------------------------------------
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
        st.success("Unlocked for this session.")
        edit_substance = st.selectbox("Substance to edit", SUBSTANCES, key="edit_substance")
        edit_cal = st.session_state["calibration"][edit_substance]

        new_m = st.number_input("Slope (m)", value=float(edit_cal["m"]), format="%.5f")
        new_b = st.number_input("Intercept (b)", value=float(edit_cal["b"]), format="%.5f")
        new_unit = st.text_input("Concentration unit", value=edit_cal["unit"])
        c1, c2 = st.columns(2)
        with c1:
            new_x_min = st.number_input("Chart x-min", value=float(edit_cal["x_min"]), format="%.5f")
        with c2:
            new_x_max = st.number_input("Chart x-max", value=float(edit_cal["x_max"]), format="%.5f")
        new_r2 = st.number_input("R² (reference only)", value=float(edit_cal.get("r_squared", 0.0)), format="%.4f")

        if st.button("Save calibration"):
            if new_m == 0:
                st.error("Slope (m) cannot be zero.")
            elif new_x_min <= 0 or new_x_max <= new_x_min:
                st.error("Chart bounds must satisfy 0 < x-min < x-max.")
            else:
                st.session_state["calibration"][edit_substance] = {
                    **edit_cal,
                    "m": new_m, "b": new_b, "unit": new_unit,
                    "x_min": new_x_min, "x_max": new_x_max, "r_squared": new_r2,
                }
                save_calibration(st.session_state["calibration"])
                st.success(f"Calibration for {edit_substance} updated.")

        if st.button("Reset to factory defaults"):
            st.session_state["calibration"] = json.loads(json.dumps(DEFAULT_CALIBRATION))
            save_calibration(st.session_state["calibration"])
            st.success("Reset to factory defaults.")
            st.rerun()

        if st.button("Lock calibration settings"):
            st.session_state["cal_unlocked"] = False
            st.rerun()

# --------------------------------------------------------------------------
# Traceability log
# --------------------------------------------------------------------------
with st.expander("🗂️ Traceability log"):
    log_df = st.session_state["log_df"]
    if log_df.empty:
        st.caption("No calculations logged yet.")
    else:
        st.dataframe(log_df.sort_values("timestamp", ascending=False), use_container_width=True, height=220)
        csv_buffer = io.StringIO()
        log_df.to_csv(csv_buffer, index=False)
        st.download_button(
            "Download full log (CSV)", data=csv_buffer.getvalue(),
            file_name=f"pfago_cascade_log_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv", use_container_width=True,
        )
        clear_pw = st.text_input("Password to clear log", type="password", key="clear_pw")
        if st.button("Clear all log entries"):
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

# --------------------------------------------------------------------------
# Footer
# --------------------------------------------------------------------------
st.markdown(
    """<div class="info-box" style="margin-top:8px;">
    This tool converts Pfago-cleavage cascade fluorescence signal into
    Histamine and Malachite Green concentration using lab-derived calibration
    curves. Calibration is specific to the originating machine and assay
    conditions — re-calibrate for new machines or reagent batches.
    </div>""",
    unsafe_allow_html=True,
)
