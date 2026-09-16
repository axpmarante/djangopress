"""Fill the director and builder prompt templates from the build packet (spec §6)."""

import json
from pathlib import Path

import djangopress

from djangopress.core.build.ledger import parse_brief
from djangopress.core.build.packet import VERTICALS

PROMPTS_DIR = Path(djangopress.__file__).parent / 'skills' / 'build-site' / 'prompts'
LABELS = 'ABCDEF'


def registers_for(n):
    if n == 3:
        regs = ['commercially safe', 'distinctive contemporary', 'strongly creative']
    elif n == 6:
        regs = ['commercially safe', 'distinctive contemporary', 'distinctive contemporary',
                'strongly creative', 'strongly creative', 'experimental']
    else:
        regs = ['commercially safe'] + ['distinctive contemporary' if i % 2 else 'strongly creative' for i in range(1, n - 1)]
        regs.append('experimental' if n >= 5 else 'strongly creative')
    return list(zip(LABELS[:n], regs[:n]))


def _fill(template, values):
    text = template
    for key, val in values.items():
        text = text.replace(f'[[{key}]]', str(val))
    return text


def _content_lines(packet):
    lines = []
    for page, groups in packet['content'].items():
        lines.append(f'Page: {page}')
        for flag, items in (('REQUIRED', groups['required']), ('optional', groups['optional'])):
            for item in items:
                line = f"- [{flag}] {item['id']} {item['kind']}: {item['text']}"
                if item.get('keywords'):
                    line += f" (keywords: {', '.join(item['keywords'])})"
                if item.get('href'):
                    line = f"- [{flag}] {item['id']} {item['kind']}: {item['text']} → {item['href']}"
                lines.append(line)
                for entry in item.get('items', []):
                    lines.append(f"    · {entry['name']} — {entry['price']} ({entry['category']})")
    return '\n'.join(lines)


def _facts_lines(packet):
    f = packet['facts']
    lines = [f"- Phone: {f.get('phone', '')}", f"- Email: {f.get('email', '')}", f"- Address: {f.get('address', '')}"]
    if f.get('maps_url'):
        lines.append(f"- Google Maps: {f['maps_url']}")
    for h in f.get('hours', []):
        lines.append(f'- Hours: {h}')
    for k, v in f.get('social', {}).items():
        lines.append(f'- {k.capitalize()}: {v}')
    return '\n'.join(lines)


def _images_lines(packet):
    rows = [f"- {k} — {v['url']} — max width {v.get('width') or 'unknown'}px — {v.get('alt', '')}" for k, v in packet['images']['map'].items()]
    return '\n'.join(rows) if rows else '(none — use placeholders everywhere)'


def _constraints_text(packet):
    c = packet['design_constraints']
    colors = ', '.join(c.get('brand_colors') or []) or 'none — choose freely'
    widths = ', '.join(f'{k} {v}px' for k, v in (c.get('image_max_widths') or {}).items()) or 'none stated'
    return '\n'.join([
        f'Brand colors (must appear, may be used sparingly): {colors}',
        f"Logo: {c.get('logo') or 'none'}",
        f"Avoid: {'; '.join(c.get('avoid') or []) or 'nothing specific'}",
        f"References (context only, never copy): {', '.join(c.get('references') or []) or 'none'}",
        f'Image constraints: {widths}',
    ])


def fill_director(packet, ledger_text, n):
    regs = registers_for(n)
    specialization = VERTICALS.get(packet['business']['type'], {}).get('specialization') or packet['business']['specialization']
    brief = '\n\n'.join([
        packet['business']['prose'],
        f"Audience and tone: {packet['business'].get('audience', '') or packet['business']['positioning']}",
        'Content the page must carry (ids are referenced in PAGE RHYTHM):',
        '\n'.join(f"- {i['id']} {i['kind']}: {i['text']}" for g in packet['content'].values() for i in g['required']),
        f"Header: {packet.get('header') or 'logo, links, one CTA, language switcher'}",
        f"Footer: {packet.get('footer') or 'contact, hours, social, privacy link, copyright'}",
    ])
    return _fill((PROMPTS_DIR / 'director.md').read_text(), {
        'SPECIALIZATION': specialization, 'BRIEF': brief,
        'DESIGN_CONSTRAINTS': _constraints_text(packet), 'N': n,
        'LABELS': ', '.join(l for l, _ in regs), 'REGISTERS': ' · '.join(f'{l} {r}' for l, r in regs),
        'FAMILIES': ', '.join(packet['families']), 'LEDGER': ledger_text or 'none yet',
    })


def fill_builder(packet, brief_text, output_path):
    return _fill((PROMPTS_DIR / 'builder.md').read_text(), {
        'OUTPUT_PATH': output_path, 'DESIGN': brief_text.strip(),
        'LANGUAGE_NAME': packet['site']['default_language_name'], 'SITE_NAME': packet['site']['name'],
        'CONTENT': _content_lines(packet), 'FACTS': _facts_lines(packet),
        'HEADER': packet.get('header') or 'logo, links, one CTA, language switcher',
        'FOOTER': packet.get('footer') or 'contact, hours, social, privacy link, copyright',
        'IMAGES': _images_lines(packet),
    })


def upsert_concept_index(index_path, key, brief_text):
    index_path = Path(index_path)
    rows = json.loads(index_path.read_text()) if index_path.exists() else []
    b = parse_brief(brief_text)
    entry = {'key': key, 'name': b['name'], 'register': b['register'], 'premise': b['premise'],
             'file': f'concept-{key}.html', 'status': 'pending'}
    rows = [r for r in rows if r['key'] != key] + [entry]
    rows.sort(key=lambda r: r['key'])
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    return entry
