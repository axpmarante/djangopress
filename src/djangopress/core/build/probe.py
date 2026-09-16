"""Run probe.js in Chromium at several widths (spec §8.2). Playwright is optional."""

from pathlib import Path

PROBE_JS = (Path(__file__).with_name('probe.js')).read_text()


def run_probe(url, widths=(390, 834, 1440), *, cta_texts=(), fonts=(), screenshot_path=None, screenshot_width=390):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {'available': False, 'defects': []}
    defects, page_errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for w in widths:
                page = browser.new_page(viewport={'width': w, 'height': 900})
                page.on('pageerror', lambda e: page_errors.append(str(e)))
                page.goto(url, wait_until='networkidle', timeout=60000)
                page.evaluate('() => document.fonts.ready')
                for d in page.evaluate(PROBE_JS, {'ctaTexts': list(cta_texts), 'fonts': list(fonts)}):
                    d['width'] = w
                    defects.append(d)
                if screenshot_path and w == screenshot_width:
                    Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(screenshot_path), full_page=True)
                page.close()
        finally:
            browser.close()
    for err in dict.fromkeys(page_errors):
        defects.append({'kind': 'console-error', 'section': 'page', 'detail': err[:200], 'width': 0})
    return {'available': True, 'defects': defects}
