#!/usr/bin/env python3
"""Offline Ratatoss UI packer and token audit, Python stdlib only.

Usage (from Ratatoss_UI_Kit/):
    python scripts/build_preview.py
    python scripts/build_preview.py --check

Bundled preview is generated from index.html + tokens.css + styles.css + app.js.
This script does NOT alter the protected original project brief.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRIEF = ROOT / 'docs' / 'SOURCE_RATATOSS_BRIEF_v1.2.md'
SHA_FILE = ROOT / 'docs' / 'SOURCE_SHA256.txt'


def get_tokens(css: str) -> dict:
    scopes: dict[str, dict] = {}
    for key, selector in [('global', ':root'), ('dark', 'body[data-theme="dark"]'), ('light', 'body[data-theme="light"]')]:
        start = css.find(selector + ' {')
        if start == -1:
            raise ValueError('Missing token scope: ' + selector)
        content = css[css.index('{', start) + 1: css.index('\n}', start)]
        scopes[key] = {}
        for line in content.splitlines():
            m = re.match(r'\s*(--[-\w]+):\s*(.+);\s*$', line)
            if m:
                scopes[key][m.group(1)] = m.group(2).strip()
    return {'meta': {'name': 'Ratatoss UI', 'version': '1.2.0', 'status': 'UI-design proposal, not source product requirement'},
            'global': scopes['global'], 'themes': {'dark': scopes['dark'], 'light': scopes['light']}}


def build() -> tuple[str, str]:
    tokens = (ROOT / 'tokens.css').read_text('utf-8')
    components = (ROOT / 'styles.css').read_text('utf-8')
    app = (ROOT / 'app.js').read_text('utf-8')
    logo_uri = 'data:image/webp;base64,' + base64.b64encode((ROOT / 'assets' / 'ratatoss-logo.webp').read_bytes()).decode('ascii')
    icon_uri = 'data:image/png;base64,' + base64.b64encode((ROOT / 'assets' / 'ratatoss-favicon.png').read_bytes()).decode('ascii')
    # Embed the uploaded brand mark into the portable, offline one-file demo.
    app = app.replace('assets/ratatoss-logo.webp', logo_uri)
    preview = (f'<!doctype html>\n<html lang="vi"><head><meta charset="utf-8">'
               f'<meta name="viewport" content="width=device-width,initial-scale=1">'
               f'<meta name="theme-color" content="#0e1014">'
               f'<meta name="description" content="Ratatoss — standalone offline UI demo, mock data only">'
               f'<title>Ratatoss — Editable UI Demo</title><link rel="icon" href="{icon_uri}">'
               f'<style>\n{tokens}\n{components}\n</style></head>'
               f'<body data-theme="dark"><div id="app"></div>'
               f'<noscript>Enable JavaScript for interactive demo.</noscript>'
               f'<script>\n{app}\n</script></body></html>')
    return preview, json.dumps(get_tokens(tokens), ensure_ascii=False, indent=2) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Only verify that generated files and tokens match sources')
    args = parser.parse_args()
    tokens = (ROOT / 'tokens.css').read_text('utf-8')
    styles = (ROOT / 'styles.css').read_text('utf-8')
    refs = set(re.findall(r'var\((--[-\w]+)', tokens + styles))
    declarations = set(re.findall(r'(--[-\w]+)\s*:', tokens + styles))
    missing = refs - declarations
    if missing:
        print('ERROR: undefined CSS variables:', ', '.join(sorted(missing)))
        return 1
    # Immutable source requirement: compare with bundled recorded digest.
    expected_hash = SHA_FILE.read_text('utf-8').strip().split()[0]
    actual_hash = hashlib.sha256(BRIEF.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        print('ERROR: source brief has changed. Restore the original, do not overwrite it.')
        return 2
    preview, tokens_json = build()
    expected_outputs = {ROOT / 'Ratatoss_UI_Preview.html': preview,
                        ROOT / 'design-tokens.json': tokens_json}
    if args.check:
        out_of_date = [str(path.relative_to(ROOT)) for path, content in expected_outputs.items()
                       if not path.exists() or path.read_text('utf-8') != content]
        if out_of_date:
            print('STALE GENERATED FILES:', ', '.join(out_of_date))
            print('Regenerate: python scripts/build_preview.py')
            return 3
        print(f'OK: {len(refs)} referenced variables defined; source brief hash unchanged; preview and JSON in sync.')
        return 0
    for path, content in expected_outputs.items():
        path.write_text(content, encoding='utf-8')
        print('Built:', path.relative_to(ROOT), f'({len(content):,} chars)')
    print('Source brief SHA-256 unchanged:', actual_hash)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
