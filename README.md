# Pfago-Cascade Concentration Calculator

A mobile-friendly Streamlit app that converts Pfago-cleavage fluorescent
cascade signal (RFU) into Histamine or Malachite Green concentration,
with calibration management and a traceable calculation log.

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

It opens at `http://localhost:8501`. On your phone, open that same URL
from a device on the same network (or just deploy it — see below — and
open the public link on your Android browser; you can also "Add to Home
Screen" from Chrome for a PWA-like icon).

## Deploy for free — Streamlit Community Cloud

1. Create a **free** GitHub account if you don't have one, and a new
   **public or private repo** (e.g. `pfago-calculator`).
2. Push these files to the repo root:
   ```bash
   git init
   git add .
   git commit -m "Pfago cascade calculator"
   git branch -M main
   git remote add origin https://github.com/<your-username>/pfago-calculator.git
   git push -u origin main
   ```
3. Go to **https://share.streamlit.io** and sign in with GitHub (free).
4. Click **"Create app"** → select your repo, branch `main`, and set the
   main file path to `app.py`.
5. Click **Deploy**. In a minute or two you'll get a public URL like
   `https://pfago-calculator.streamlit.app` — this works great on mobile
   browsers, including Android, one-handed and vertically.
6. (Recommended) In the app's **Settings → Secrets** on Streamlit Cloud,
   set a real calibration password instead of the placeholder:
   ```toml
   cal_password = "your-real-password-here"
   ```
   The app reads this automatically via `st.secrets["cal_password"]`.

No credit card or paid tier is required for this — Streamlit Community
Cloud is free for public apps.

## Using the app

1. **Pick the substance** (Histamine or Malachite Green) — this loads
   its calibration curve (slope `m`, intercept `b`).
2. Enter a **Sample ID** — required before a calculation can run, so
   every result is traceable back to a specific sample.
3. Optionally fill in **run metadata** (machine ID, reagent batch ID,
   operator) for traceability.
4. Enter **Y_raw** (raw RFU from the instrument). Toggle background
   subtraction on/off and enter **Y_background** if using a blank/negative
   control.
5. Click **Calculate concentration**. The app:
   - blocks the calculation with a warning if Sample ID is missing
   - computes `Y_net = Y_raw − Y_background`
   - blocks the calculation with a clear warning if `Y_net ≤ 0`
   - solves for `x` using the substance-specific inverse formula
   - plots the calibration curve with your sample point marked
   - appends a full record (including Sample ID) to the traceability log
   - offers a **Download PDF report** button for that single sample
6. Download the full log any time as CSV from the **Traceability log**
   section, or re-download the last sample's PDF report from the
   **"📄 Report available"** panel above the calibration curve.

### PDF report contents

Each generated report includes:
- Sample ID, substance, timestamp, machine ID, batch ID, operator
- Raw RFU, background RFU, and corrected `Y_net`
- Calibration coefficients used (`m`, `b`, log type)
- Final concentration result with units
- A rendered calibration curve with the sample point marked
- The same machine/assay-specificity disclaimer shown in the app

## Calibration management

Open **"⚙️ Calibration management"**, enter the calibration password
(default `pfago-admin` — change this via Streamlit secrets before real
use), and adjust `m`, `b`, the log type (`log10` for Histamine-style
curves, `ln` for Malachite Green-style curves), the unit label, and the
chart's x-axis bounds. Settings are saved to `calibration.json` and
persist across sessions on the same deployment (see persistence note
below).

## Important: data persistence on Streamlit Community Cloud

Streamlit Community Cloud containers use an **ephemeral filesystem** —
`calibration.json` and `calculation_log.csv` can be reset when the app
redeploys or wakes from sleep after inactivity. For casual/lab-bench use
this is usually fine if you **download the CSV log regularly** using the
in-app download button.

For a production lab setting where permanent, always-on record-keeping
matters, swap the CSV logging for a persistent backend — the most
common free/low-cost options:
- **Google Sheets** via the `gspread` + `google-auth` libraries (a
  Streamlit Cloud secret holds the service account credentials)
- **Supabase** or another free-tier hosted Postgres database
- Any other database reachable from the deployed container

The app's `append_log()` / `load_log()` functions in `app.py` are the
only two functions you'd need to swap out — everything else stays the
same.

## Formulas implemented

**Histamine**
```
Y_net = 13780 · log10(x) − 20930
x = 10 ^ ((Y_net + 20930) / 13780)
```

**Malachite Green**
```
Y_net = 3892.39 · ln(x) − 4664.89
x = e ^ ((Y_net + 4664.89) / 3892.39)
```

Both are implemented generically in `x_from_y_net()` using the stored
`m`, `b`, and `log_type` for the selected substance, so adjusting
calibration coefficients in the UI immediately changes the math used
for every subsequent calculation and chart.

## Safety / scientific notes shown in-app

- A visible reminder that the calibration is specific to the machine
  and assay conditions it was derived from.
- Hard validation: `Y_net ≤ 0` is rejected before any log/exp is
  attempted (avoids the log domain error).
- Non-numeric input is impossible by construction (Streamlit's
  `number_input` only accepts numeric values), and all math is wrapped
  in `try/except` against overflow or domain errors.
