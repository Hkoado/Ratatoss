# QA Report — Ratatoss UI v1.2

Generated via automated Chromium + Playwright DOM interaction tests on the one-file offline demo. Not a security or accessibility certification.

- Checks: 45
- Passed: 45
- Failed: 0
- Viewports: 1440, 1024, 768, 390, 320 CSS pixels.
- Browser navigation tested using `page.set_content` on self-contained HTML; no API/Croc requests.
- Covered: theme, branding, shadow removal, responsive overflow, six modules, peer search, modal login, metadata file selection, transfer simulator, pause/resume, C offline/reconnect.

All listed checks passed.

The project source brief SHA-256 is separately audited by `scripts/build_preview.py --check`.
