# Ratatoss UI Kit — Smoke Test Report

Date: 2026-11-18. Tested on Chromium headless with self-contained HTML injected into a browser page, avoiding environment navigation restrictions. **UI-only simulation**; no network transport, hash, scheduling, backend or security tests.

- [x] Desktop dark background
- [x] Desktop sidebar width
- [x] Initial simulated recipient count
- [x] Navigation peers
- [x] Navigation send
- [x] Navigation transfers
- [x] Navigation history
- [x] Navigation settings
- [x] Navigation overview
- [x] Light theme attribute
- [x] Light theme bg
- [x] Login modal visible
- [x] Login focus on name
- [x] Demo identity
- [x] 3 peers selected
- [x] 2 peers selected
- [x] Selected file name displayed
- [x] Start job enabled
- [x] Transfer page after start
- [x] Only selected graph recipients
- [x] No C graph node
- [x] Pause demo
- [x] Resume appears
- [x] C offline disabled if excluded
- [x] B/C/D graph nodes plus source
- [x] C offline status present
- [x] C restored
- [x] No JS errors
- [x] Horizontal scroll at 320px
- [x] Horizontal scroll at 390px
- [x] Mobile menu opens
- [x] Mobile navigation works
- [x] Horizontal scroll at 560px
- [x] Horizontal scroll at 768px
- [x] Horizontal scroll at 1024px
- [x] Horizontal scroll at 1280px

**Result:** 36/36 smoke checks passed.

**Not tested:** OS file handoff to Agent, Croc CLI, backend auth, real verified hashes, adaptive topology, production many-node graph, accessibility audit for WCAG AA, cross-browser matrix.
