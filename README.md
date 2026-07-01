# Pfago-Cleavage Concentration Calculator

A mobile-friendly Streamlit app that converts corrected fluorescence signal
(Y_net) into analyte concentration (x) for Histamine and Malachite Green,
using the Pfago-cleavage cascade calibration curves.

## Files
- `app.py` — the full application
- `requirements.txt` — dependencies

## Deploy for free (Streamlit Community Cloud)

1. Create a free GitHub account if you don't have one, and a new **public**
   repository (e.g. `pfago-calculator`).
2. Upload `app.py` and `requirements.txt` to that repository (drag-and-drop
   works fine on github.com — "Add file" → "Upload files").
3. Go to **https://share.streamlit.io** and sign in with GitHub.
4. Click **"New app"**, select your repo/branch, set the main file path to
   `app.py`, and click **Deploy**.
5. In a minute or two you'll get a public URL like
   `https://your-app-name.streamlit.app` — this works on any phone browser
   and can be "Added to Home Screen" on Android for an app-like icon (PWA-style).

No credit card or paid tier is required for this size of app.

## Design
The interface is styled like an instrument faceplate — the kind of look a
benchtop fluorometer or qPCR machine display has, not a generic web-app
theme:
- **Palette**: anodized-panel charcoal (`#12181B`) with an etched hairline
  grid, a fluorescence-green accent (`#6EE7B7`) for live signal and the
  calibration curve, and a "chart-recorder amber" (`#F5A623`) that marks
  your sample point and warnings — echoing an actual strip-chart pen.
- **Type**: IBM Plex Mono for all numeric readouts (tabular digits, like a
  digital instrument display) and IBM Plex Sans for labels/body text.
- **Signature element**: the glowing LCD-style readout boxes for Y_net and
  concentration — everything else stays quiet and functional around them.
- The Plotly chart is restyled to match (dark panel, etched gridlines,
  green curve, amber diamond marker for the sample).

Colors/fonts live at the top of `app.py` as named constants, so you can
retint the whole app (e.g. to match your lab's branding) by editing a
handful of hex values in one place. `.streamlit/config.toml` sets
Streamlit's own base theme to match.

## Using the app

1. **Sidebar → Calibration Management**: unlock with password (default
   demo password: `admin123` — change the `CALIB_PASSWORD` constant in
   `app.py` before real lab use, or better, move it into Streamlit's
   `st.secrets`) to adjust slope/intercept per reagent batch.
2. **Main page**: pick the substance, enter batch ID / machine ID, raw RFU,
   and (optionally) the background/blank signal.
3. The app computes `Y_net = Y_raw - Y_background`, validates it's > 0,
   solves for concentration `x`, and plots the calibration curve with your
   sample marked as a star.
4. Click **Save to log** to add the record to the session's traceability
   table, and **Export log as CSV** to download it permanently.

## Important notes
- The session log resets on app restart/new browser session. Export CSV
  regularly, or wire in a persistent store (Google Sheets API, Supabase,
  a database) if you need permanent cross-session storage — happy to help
  build that next if useful.
- The calibration curves are specific to the instrument and reagent batch
  they were derived from; re-derive slope/intercept when conditions change.
- Inputs are numeric-only by construction (Streamlit's `number_input`), and
  the app blocks any calculation where `Y_net <= 0` or where a log/ln
  operation would be undefined.
