"""Fill the director and builder prompt templates from the build packet (spec §6)."""

import json
from pathlib import Path

import djangopress

from djangopress.core.build.ledger import parse_brief
from djangopress.core.build.packet import VERTICALS

PROMPTS_DIR = Path(djangopress.__file__).parent / 'skills' / 'build-site' / 'prompts'
LABELS = 'ABCDEF'


CONVENTIONAL_REGISTERS = [
    "conventional, template-grade: the sector's canonical structure executed with restraint",
    'the same canonical structure with one distinctive idea',
    'a second conventional variation on a different axis (light/dark, photography-led/type-led, warm/cool)',
    'canonical, dark variation',
    'canonical, type-led variation',
    'one bolder take, still usable',
]

AVOID_CONVENTIONAL = (
    'ALWAYS AVOID: stock photography, glass cards, gradient backgrounds, black + gold, lorem ipsum, invented\n'
    'numbers or testimonials, decorative icon fonts, more than one accent colour.\n'
    "ALLOWED in this mode (they are the sector's conventions): service cards with line icons, 3- and 4-column\n"
    'grids, centred section headings with labels, a top utility bar, coloured CTA bands, photo/text\n'
    'alternation, stat tiles with real numbers, rounded cards with soft shadows.'
)

AVOID_BOLD = (
    'Avoid repeating common AI-generated landing page patterns: text left / image right hero,\n'
    'floating glass card over hero, endless rounded cards, identical 3-column grids,\n'
    'gradient-heavy backgrounds, generic luxury black + gold, SaaS-style feature cards,\n'
    'excessive pills, excessive shadows, identical centered headings, repeating alternating\n'
    'text/image sections. Use these only when clearly justified by the concept.'
)

TASTE_LINE = (
    'The bar is taste, not novelty: real photography shown large, generous spacing, one accent colour,\n'
    'restrained typography, nothing invented. A visitor must recognise the sector\'s conventions instantly\n'
    'and think "this one is better made".'
)

DIVERSITY_BOLD = (
    '==================================================\n'
    'CORE OBJECTIVE\n'
    '==================================================\n\n'
    'Every concept must be appropriate for the same business, but must feel as though it was\n'
    'created by a different high-level creative studio. Do not generate minor variations of the\n'
    'same aesthetic. Do not simply change colors, fonts or the hero image. The underlying visual\n'
    'system must change.\n\n'
    '==================================================\n'
    'DIVERSITY REQUIREMENT\n'
    '==================================================\n\n'
    'The concepts must have high visual distance from one another. For every pair of concepts,\n'
    'change at least 7 of the 16 Design DNA dimensions. Never allow two concepts to share all of:\n'
    'same hero architecture, same layout grammar, same typography class, same dominant color\n'
    'logic, same graphic device. If two concepts begin to feel visually similar, redesign one\n'
    'before returning the result.\n\n'
    '==================================================\n'
    'FINAL CHECK\n'
    '==================================================\n\n'
    'Before outputting, compare all concepts internally. If any two could plausibly be\n'
    'variants of the same template, redesign one. Do not output that internal analysis.'
)


def _label_list(labels):
    """'A' / 'A and B' / 'A, B, C, D and E' — an Oxford-less "and" join."""
    labels = list(labels)
    if not labels:
        return ''
    if len(labels) == 1:
        return labels[0]
    return ', '.join(labels[:-1]) + ' and ' + labels[-1]


def _diversity_conventional(labels):
    labels = list(labels) or ['A', 'B', 'C']
    required, last = labels[:-1], labels[-1]
    required_text = _label_list(required) or last
    return (
        '==================================================\n'
        'CORE OBJECTIVE\n'
        '==================================================\n\n'
        "Every concept is a well-made version of the sector's canonical site.\n\n"
        '==================================================\n'
        'DIVERSITY REQUIREMENT\n'
        '==================================================\n\n'
        f'{required_text} keep the same section order and components; they must differ on at least 5 of\n'
        'the 16 Design DNA dimensions among these — visual personality, hero architecture (within\n'
        'the canonical hero), typographic system, color logic, photography style, cropping,\n'
        'graphic device, geometry, density, navigation style, CTA style, motion, mobile behaviour.\n'
        f'{last} may reorder or merge sections but keeps every component. Never two concepts that differ\n'
        'only in hue.\n\n'
        '==================================================\n'
        'FINAL CHECK\n'
        '==================================================\n\n'
        'FINAL CHECK: if two concepts differ only in hue or hero photo, redesign one; do not make\n'
        'them structurally different on purpose.'
    )


def diversity_block(mode, labels=None):
    labels = labels or list(LABELS[:3])
    return _diversity_conventional(labels) if mode == 'conventional' else DIVERSITY_BOLD


def _mode(packet):
    return 'bold' if (packet.get('design_constraints') or {}).get('mode') == 'bold' else 'conventional'


def registers_for(n, mode='conventional'):
    if mode == 'conventional':
        regs = CONVENTIONAL_REGISTERS[:n]
        while len(regs) < n:
            regs.append(CONVENTIONAL_REGISTERS[2])
    elif n == 3:
        regs = ['commercially safe', 'distinctive contemporary', 'strongly creative']
    elif n == 6:
        regs = ['commercially safe', 'distinctive contemporary', 'distinctive contemporary',
                'strongly creative', 'strongly creative', 'experimental']
    else:
        regs = ['commercially safe'] + ['distinctive contemporary' if i % 2 else 'strongly creative' for i in range(1, n - 1)]
        regs.append('experimental' if n >= 5 else 'strongly creative')
    return list(zip(LABELS[:n], regs[:n]))


def avoid_block(mode):
    return AVOID_CONVENTIONAL if mode == 'conventional' else AVOID_BOLD


def structure_block(packet, mode, labels=None):
    vertical = packet['business'].get('type', '')
    structure = packet['business'].get('structure') or VERTICALS.get(vertical, {}).get('structure', '')
    if mode == 'conventional':
        labels = list(labels) or ['A', 'B', 'C']
        required, last = labels[:-1], labels[-1]
        required_text = _label_list(required) or last
        head = f'CANONICAL STRUCTURE (required for {required_text}; {last} may vary the order but keeps the components)'
        body = f'{structure}\n\n{TASTE_LINE}'
    else:
        head = 'CANONICAL STRUCTURE (for reference — the concepts may leave it)'
        body = structure
    return '\n'.join(['=' * 50, head, '=' * 50, '', body])


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


def _pages_text(packet):
    slugs = [p['slug'] for p in packet['pages'] if p['slug'] != 'home']
    return ', '.join(f'/{s}/' for s in slugs) if slugs else 'none — use anchors only'


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
        f"Direction from the operator (a steer, not a template — see DIVERSITY): "
        f"{c.get('direction') or 'none — roam freely'}",
        f"Avoid: {'; '.join(c.get('avoid') or []) or 'nothing specific'}",
        (f"References chosen by the operator (structure and register to adapt, never copy): {', '.join(c['references'])}"
         if c.get('references') else 'References: none'),
        f'Image constraints: {widths}',
    ])


def fill_director(packet, ledger_text, n):
    mode = _mode(packet)
    regs = registers_for(n, mode)
    labels = [l for l, _ in regs]
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
        'STRUCTURE_BLOCK': structure_block(packet, mode, labels), 'AVOID_BLOCK': avoid_block(mode),
        'DIVERSITY_BLOCK': diversity_block(mode, labels),
    })


def fill_builder(packet, brief_text, output_path):
    form = packet.get('form') or {}
    fields = form.get('fields') or ['name', 'email', 'message']
    service_options = form.get('service_options') or []
    return _fill((PROMPTS_DIR / 'builder.md').read_text(), {
        'OUTPUT_PATH': output_path, 'DESIGN': brief_text.strip(),
        'LANGUAGE_NAME': packet['site']['default_language_name'], 'SITE_NAME': packet['site']['name'],
        'CONTENT': _content_lines(packet), 'FACTS': _facts_lines(packet),
        'HEADER': packet.get('header') or 'logo, links, one CTA, language switcher',
        'FOOTER': packet.get('footer') or 'contact, hours, social, privacy link, copyright',
        'IMAGES': _images_lines(packet),
        'PAGES': _pages_text(packet),
        'FORM_ACTION': form.get('action') or '/forms/contact/submit/',
        'FORM_FIELDS': ', '.join(fields),
        'FORM_SERVICE_OPTIONS': ' / '.join(service_options) if service_options else 'none',
        'AVOID_BLOCK': avoid_block(_mode(packet)),
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
