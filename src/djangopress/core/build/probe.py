"""Run probe.js in Chromium at several widths (spec §8.2). Playwright is optional."""

from pathlib import Path

SCROLL_STEP = 450


def _probe_js():
    return (Path(__file__).with_name('probe.js')).read_text()


def run_probe(url, widths=(390, 834, 1440), *, cta_texts=(), fonts=(), screenshot_path=None, screenshot_width=390):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {'available': False, 'defects': []}
    probe_js = _probe_js()
    defects, page_errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for w in widths:
                page = browser.new_page(viewport={'width': w, 'height': 900})
                page.on('pageerror', lambda e: page_errors.append(str(e)))
                page.goto(url, wait_until='networkidle', timeout=60000)
                page.evaluate('() => document.fonts.ready')
                # Scroll the whole page first so lazy/intersection-driven content has had
                # its chance to appear — done here (not inside probe.js) so each step
                # actually yields to the browser between scrolls.
                scroll_height = page.evaluate('() => document.documentElement.scrollHeight')
                y = 0
                while y < scroll_height:
                    page.evaluate('y => window.scrollTo(0, y)', y)
                    page.wait_for_timeout(50)
                    y += SCROLL_STEP
                page.evaluate('() => window.scrollTo(0, 0)')
                for d in page.evaluate(probe_js, {'ctaTexts': list(cta_texts), 'fonts': list(fonts)}):
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
