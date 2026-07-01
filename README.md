# Pfago-Cleavage Concentration Calculator

## What changed in this version
- **Fixed the broken CSS.** The old version injected styles through
  `st.markdown(..., unsafe_allow_html=True)`, which runs the string through
  Streamlit's markdown parser first. Blank lines inside the `<style>` block
  made that parser drop out of "raw HTML" mode partway through, so half the
  CSS printed as literal text on the page. This version uses `st.html()`,
  which injects raw HTML/CSS directly with no markdown pass — that bug
  class is no longer possible. (Requires `streamlit>=1.37`.)
- **Removed the sidebar.** Everything lives in the main page now.
- **Removed the substance dropdown.** Histamine and Malachite Green each
  get their own always-visible input box; Calculate computes both at once.
- **Restructured the flow** to: Sample ID + Analyst ID → Histamine input →
  Malachite Green input → Calculate → two result boxes → Generate Report →
  "Other details" (batch/machine ID, background signal, calibration,
  history).
- **History is now tied to the Analyst / User ID** field — the "Other
  details" panel only shows and exports rows logged under the ID currently
  entered at the top.

## Files
- `app.py` — the app
- `requirements.txt`
- `.streamlit/config.toml` — base dark theme

## Deploy (free)
1. Push these files to a public GitHub repo (root of the repo, keep the
   `.streamlit/config.toml` path).
2. Go to https://share.streamlit.io, sign in with GitHub, "New app", point
   it at the repo with main file `app.py`, Deploy.

## Notes
- Calibration is password-gated inside "Other details" (demo password
  `admin123` — change `CALIB_PASSWORD` in `app.py`, or better, move it to
  `st.secrets` before real lab use).
- History storage is in-memory for the running app session — it resets if
  the app restarts/redeploys. If you need permanent storage across
  restarts, the next step is wiring in a database (Google Sheets API or
  Supabase are both free-tier options) — say the word and I'll build that.
- I have not been able to render this Streamlit app myself in this
  environment (no network access), so please screenshot again after
  redeploying if anything still looks off — I'd rather fix it in one more
  precise pass than guess.
