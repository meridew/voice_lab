# Voice Lab — working agreements

- **Do not screenshot pages or click through UIs to verify them.** Open the page in the in-app browser pane
  so Daniel can look at it himself, and say that you have. Non-visual checks (console errors, an import or
  build check) are fine.
- **Icons over labels.** Buttons and tabs are icon-only with a tooltip wherever the icon is obvious.
- **Clean and simple.** One page, one waveform, over one library of originals and augmented clips tagged Voice
  or SFX. Shared components (`app/static/lab.js`), no explanatory text fodder, no progress overlays that repaint
  the page, a library modal with a fixed height.
- **Stack.** FastAPI (`app/server.py`) serves `app/static/` and a small JSON API; the page is WaveSurfer.js,
  Tailwind (CDN) and Lucide with vanilla glue; effects run live in Web Audio and render offline in the browser;
  Seed-VC and exports run on the server. Gradio is gone.
- Long jobs run in the background with a stated estimate; never leave Daniel waiting in silence.
- **Checks.** `scripts/check.sh` (ruff, API in-process) before handing over; `scripts/convert-check.sh` when the
  model path changed. One-off experiment scripts do not stay in the tree; record the numbers and delete. Unused
  code goes too: git history keeps it.
