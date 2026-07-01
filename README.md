# Pfago-Cascade Concentration Calculator

A compact, mobile-first Streamlit app that calculates **Histamine** (HEX
channel) and **Malachite Green** (FAM channel) concentrations from Pfago-
cleavage fluorescent cascade signal, side by side, in a single view with
no scrolling required on a phone. Every calculation produces a downloadable
PDF report.

## What's inside

```
pfago_app/
├── app.py                  # the application
├── requirements.txt        # dependencies
├── calibration.json        # created automatically on first calibration save
├── calculation_log.csv     # created automatically on first calculation
└── .streamlit/
    └── config.toml         # dark "lab instrument" theme
```

## Run it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy for free — Streamlit Community Cloud

1. Create a **free** GitHub account and a repo (e.g. `H-MG-Detection`).
2. Push these files to the repo root (`app.py`, `requirements.txt`,
   `README.md`, `.streamlit/config.toml`).
3. Go to **https://share.streamlit.io**, sign in with GitHub.
4. Click **"Create app"** → select your repo, branch `main`, main file
   `app.py` → **Deploy**.
5. You'll get a public URL like `https://h-mg-detection.streamlit.app`.
6. (Recommended) In **Settings → Secrets**, set a real calibration
   password:
   ```toml
   cal_password = "your-real-password-here"
   ```

## What's on screen (no scrolling needed on mobile)

1. **Other info** (collapsed dropdown) — Machine ID, Reagent Batch ID,
   Operator.
2. **Sample ID** — required before generating a report.
3. **Histamine — HEX channel**: Raw RFU + Background RFU.
4. **Malachite Green — FAM channel**: Raw RFU + Background RFU.
5. **Generate report** button — computes both concentrations, shows
   them directly on screen, and produces a downloadable PDF.

Below the fold (scroll down only if you want them): calibration
management, the traceability log, and a one-line explanation of what
the tool is for.

## The formulas

Both channels use the same model: the corrected signal `Y_net = Y_raw −
Y_background` was fit as a **linear regression against log10(concentration
in nM)**, i.e. `Y_net = m · log10(x) + b`. Solving for concentration:

```
x = 10 ^ ((Y_net − b) / m)
```

Current calibration (from lab-derived calibration curves):

| Channel | Target | m | b | R² | Unit |
|---|---|---|---|---|---|
| HEX | Histamine | 32355 | 44788 | 0.9328 | nM |
| FAM | Malachite Green | 41396 | 44245 | 0.9163 | nM |

These are editable in the **"⚙️ Calibration management"** panel
(password-protected) if the assay is re-calibrated on a new machine
or reagent batch.

## PDF report contents

Each generated report includes, for both channels:
- Sample ID, timestamp, machine/batch/operator metadata
- Raw RFU, background RFU, and corrected `Y_net`
- Calibration coefficients used (`m`, `b`, R²)
- Final concentration result
- The calibration curve with the sample point marked
- A written explanation of the formula and how the result was derived
- The machine/assay-specificity disclaimer

## Validation & error handling

- Sample ID is required — the app warns and blocks report generation
  if it's missing.
- If a channel's `Y_net ≤ 0`, that channel shows an inline warning
  ("Corrected signal must be greater than zero") instead of a result,
  while the other channel still calculates normally if valid.
- Non-numeric input is impossible by construction (Streamlit's
  `number_input` only accepts numbers), and all math is wrapped in
  `try/except` against overflow or domain errors.

## Important: data persistence on Streamlit Community Cloud

Streamlit Community Cloud containers use an **ephemeral filesystem** —
`calibration.json` and `calculation_log.csv` can reset when the app
redeploys or wakes from sleep after inactivity. Download the CSV log
regularly from the **Traceability log** panel. For guaranteed permanent
record-keeping, swap `append_log()` / `load_log()` in `app.py` for a
persistent backend (Google Sheets via `gspread`, a hosted database, etc.).
