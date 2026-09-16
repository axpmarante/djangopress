"""Shared design-DNA ledger: every concept ever generated, across all sites."""

import json
import os
import re
from pathlib import Path

DNA_KEYS = {
    'movement': 'movement', 'personality': 'personality', 'layout grammar': 'layout_grammar', 'hero': 'hero',
    'typography': 'typography', 'color': 'color', 'photography': 'photography', 'cropping': 'cropping',
    'graphic device': 'graphic_device', 'section transitions': 'section_transitions', 'geometry': 'geometry',
    'density': 'density', 'navigation': 'navigation', 'cta': 'cta', 'motion': 'motion', 'mobile behaviour': 'mobile',
}
DNA_LABELS = {v: k.capitalize() for k, v in DNA_KEYS.items()}
FIELD_RE = re.compile(r'^(CONCEPT NAME|REGISTER|CREATIVE PREMISE|BRAND IDEA):\s*(.*)$')
DNA_LINE_RE = re.compile(r'^-\s*([A-Za-z ]+?):\s*(.*)$')


def parse_brief(text):
    out = {'name': '', 'register': '', 'premise': '', 'brand_idea': '', 'dna': {}}
    for line in text.splitlines():
        m = FIELD_RE.match(line.strip())
        if m:
            key = {'CONCEPT NAME': 'name', 'REGISTER': 'register', 'CREATIVE PREMISE': 'premise', 'BRAND IDEA': 'brand_idea'}[m.group(1)]
            out[key] = m.group(2).strip()
            continue
        m = DNA_LINE_RE.match(line.strip())
        if m and m.group(1).strip().lower() in DNA_KEYS:
            out['dna'][DNA_KEYS[m.group(1).strip().lower()]] = m.group(2).strip()
    return out


def default_ledger_path():
    root = os.environ.get('DJANGOPRESS_SITES_ROOT') or str(Path.cwd().parent)
    return Path(root) / '.design-dna' / 'ledger.json'


def format_entries(entries):
    if not entries:
        return 'none yet'
    blocks = []
    for e in entries:
        lines = [f"{e['name']} ({e['site']}, {e['date']}, {'shipped' if e.get('shipped') else 'not shipped'}):"]
        for key in DNA_KEYS.values():
            if e['dna'].get(key):
                lines.append(f"  - {DNA_LABELS[key]}: {e['dna'][key]}")
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)


class Ledger:
    def __init__(self, path=None):
        self.path = Path(path) if path else default_ledger_path()

    def _load(self):
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text() or '[]')

    def _save(self, rows):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rows, ensure_ascii=False, indent=1))

    def read(self, vertical=None, limit=12):
        rows = [r for r in self._load() if vertical is None or r.get('vertical') == vertical]
        rows.sort(key=lambda r: r.get('date', ''), reverse=True)   # newest first …
        rows.sort(key=lambda r: not r.get('shipped', False))       # … shipped first (stable)
        return rows[:limit]

    def append(self, entry):
        rows = self._load()
        rows = [r for r in rows if not (r['site'] == entry['site'] and r['key'] == entry['key'])]
        rows.append(entry)
        self._save(rows)

    def mark_shipped(self, site, key):
        rows = self._load()
        for r in rows:
            if r['site'] == site:
                r['shipped'] = (r['key'] == key)
        self._save(rows)
