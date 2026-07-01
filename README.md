# Pfago-Cleavage Concentration Calculator

## What changed in this version
- **Calibration password removed.** Slope/intercept for each substance are
  now directly editable at the bottom of the page — no unlock step.
- **Flattened "Other details."** Instead of one big collapsed panel, the
  page just has plain sections at the bottom: Background Signal,
  Calibration, History. Nothing extra hidden behind clicks.
- **History is now tied to the browser, not a typed-in name.** On first
  load the app sets a `pfago_uid` cookie in your browser (via a small
  inline script, since Streamlit's own API can read cookies but not set
  them) and reads it back with `st.context.cookies` on every load. History
  is filtered to rows logged from that cookie. No login, no manual ID.
  - This requires `streamlit>=1.37` (for `st.context`). If cookies are
    blocked or you're in private/incognito mode, a session-only ID is used
    as a fallback and history won't survive a full page reload — that's an
    inherent browser-storage limitation, not a bug in the app.

## Files
- `app.py`
- `requirements.txt`
- `.streamlit/config.toml` — base dark theme

## Deploy (free)
1. Push these files to a public GitHub repo (keep `.streamlit/config.toml`
   in its folder).
2. https://share.streamlit.io → sign in with GitHub → "New app" → point at
   the repo, main file `app.py` → Deploy.

## Notes
- Log storage is in-memory for the running app process — it resets if the
  app restarts/redeploys, and (because it's cookie- not account-based) a
  cleared-cookies visit looks like a new user. For real permanent,
  cross-restart storage, the next step would be a small database (Google
  Sheets API or Supabase both have free tiers) keyed on the same cookie —
  happy to wire that in if you want it.
- I still don't have network access in this environment, so I can't render
  the app myself before you see it. If anything's off, a screenshot gets
  it fixed fast.
