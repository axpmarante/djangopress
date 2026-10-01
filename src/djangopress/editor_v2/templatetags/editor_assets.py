"""Pin every editor ES module to a version of its content with an import map.

editor.js is loaded with a ?v= version, but the modules it imports are fetched by
plain relative URLs, so a browser could combine cached old modules with new ones
(and the editor then fails to start). The import map rewrites each module URL to
a versioned one: the hashed file in production (ManifestStaticFilesStorage), or
?v=<content hash> in development. A module whose content didn't change keeps its
URL, so only changed files are fetched again."""
import hashlib
import json
from pathlib import Path

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.safestring import mark_safe

register = template.Library()

JS_ROOT = Path(__file__).resolve().parent.parent / 'static' / 'editor_v2' / 'js'
_cache = {'stamp': None, 'map': {}}


def module_map():
    """{plain module URL: versioned URL} for every .js file under editor_v2/js."""
    files = sorted(JS_ROOT.rglob('*.js'))
    stamp = tuple((str(f), f.stat().st_mtime_ns) for f in files)
    if stamp == _cache['stamp']:
        return _cache['map']
    imports = {}
    base = settings.STATIC_URL.rstrip('/') + '/'
    for path in files:
        rel = 'editor_v2/js/' + path.relative_to(JS_ROOT).as_posix()
        plain = base + rel
        try:
            versioned = static(rel)
        except ValueError:          # not in the manifest (collectstatic not run for it)
            versioned = plain
        if versioned == plain:
            versioned = f'{plain}?v={hashlib.md5(path.read_bytes()).hexdigest()[:10]}'
        imports[plain] = versioned
    _cache.update(stamp=stamp, map=imports)
    return imports


@register.simple_tag
def editor_importmap():
    data = json.dumps({'imports': module_map()}, separators=(',', ':')).replace('</', '<\\/')
    return mark_safe(f'<script type="importmap">{data}</script>')
