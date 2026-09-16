// Layout probe (spec §8.2). Evaluated by Playwright with page.evaluate(PROBE_JS, args).
// Returns [{kind, section, detail}]. args = {ctaTexts: [...], fonts: [...]}
(args) => {
  const defects = [];
  const w = window.innerWidth, h = window.innerHeight;
  const de = document.documentElement;
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();

  function sectionOf(el) {
    if (!el || !el.closest) return 'page';
    const s = el.closest('[data-section]');
    if (s) return s.dataset.section;
    if (el.closest('header')) return 'header';
    if (el.closest('footer')) return 'footer';
    return 'page';
  }
  function effectiveBg(el) {
    let e = el;
    while (e) {
      const bg = getComputedStyle(e).backgroundColor;
      if (bg && bg !== 'transparent' && !/rgba\(\d+, \d+, \d+, 0\)/.test(bg)) return bg;
      if (e === de) break;
      e = e.parentElement;
    }
    return 'rgb(255, 255, 255)';
  }
  function lum(c) {
    const m = (c || '').match(/\d+(\.\d+)?/g);
    if (!m || m.length < 3) return null;
    const [r, g, b] = m.slice(0, 3).map(v => { v = parseFloat(v) / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }
  function contrast(a, b) {
    const la = lum(a), lb = lum(b);
    if (la === null || lb === null) return null;
    const hi = Math.max(la, lb), lo = Math.min(la, lb);
    return (hi + 0.05) / (lo + 0.05);
  }

  // The page has already been scrolled through by probe.py (see run_probe) before this
  // runs, so lazy/intersection-driven content has had its chance to appear.

  function isHidden(el, sec) {
    if (typeof el.checkVisibility === 'function') {
      return el.checkVisibility({ opacityProperty: true, visibilityProperty: true }) === false;
    }
    let e = el;
    while (e) {
      const cs = getComputedStyle(e);
      if (parseFloat(cs.opacity) === 0 || cs.visibility === 'hidden') return true;
      if (e === sec) break;
      e = e.parentElement;
    }
    return false;
  }

  for (const sec of document.querySelectorAll('[data-section]')) {
    const texts = [...sec.querySelectorAll('h1,h2,h3,h4,p,li,a,span')].filter(e => e.textContent.trim());
    if (!texts.length) continue;
    const hidden = texts.filter(e => isHidden(e, sec));
    if (hidden.length === texts.length) defects.push({ kind: 'hidden-content', section: sec.dataset.section, detail: `${texts.length} text elements at opacity 0 / hidden after scrolling the page` });
  }

  if (de.scrollWidth > w + 1) {
    let culprit = null;
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.right > w + 1) { culprit = el; break; }
    }
    defects.push({ kind: 'overflow', section: sectionOf(culprit), detail: `scrollWidth ${de.scrollWidth} > ${w}` + (culprit ? ` at <${culprit.tagName.toLowerCase()}>` : '') });
  }

  for (const sec of document.querySelectorAll('[data-section]')) {
    const r = sec.getBoundingClientRect();
    if (r.height < 40) defects.push({ kind: 'empty-section', section: sec.dataset.section, detail: `height ${Math.round(r.height)}px` });
  }

  const header = document.querySelector('header');
  if (header) {
    const link = header.querySelector('a');
    if (link) {
      const rect = link.getBoundingClientRect();
      const x = Math.min(w - 1, Math.max(0, rect.left + rect.width / 2));
      const y = Math.max(0, rect.top + rect.height / 2);
      const under = document.elementsFromPoint(x, y).find(e => !header.contains(e));
      const ratio = contrast(getComputedStyle(link).color, under ? effectiveBg(under) : effectiveBg(document.body));
      if (ratio !== null && ratio < 3) defects.push({ kind: 'header-contrast', section: 'header', detail: `ratio ${ratio.toFixed(2)} for first nav link` });
    }
  }

  for (const img of document.images) {
    if (img.src.includes('placehold.co') || !img.complete || !img.naturalWidth) continue;
    if (img.naturalWidth < img.clientWidth * 0.9) defects.push({ kind: 'upscaled-image', section: sectionOf(img), detail: `${img.naturalWidth}px source rendered at ${img.clientWidth}px` });
  }

  if (args.ctaTexts && args.ctaTexts.length) {
    const wanted = args.ctaTexts.map(norm);
    let found = false;
    for (const el of document.querySelectorAll('a, button')) {
      const r = el.getBoundingClientRect();
      if (wanted.includes(norm(el.textContent)) && r.height > 0 && r.top >= 0 && r.top < h) { found = true; break; }
    }
    if (!found) defects.push({ kind: 'cta-below-fold', section: 'hero', detail: 'no primary CTA inside the first viewport' });
  }

  for (const sec of document.querySelectorAll('[data-section]')) {
    const texts = [...sec.querySelectorAll('h1,h2,h3,h4,p')].map(e => ({ e, r: e.getBoundingClientRect() })).filter(t => t.r.height > 0 && t.r.width > 0);
    let reported = false;
    for (let i = 0; i < texts.length && !reported; i++) {
      for (let j = i + 1; j < texts.length; j++) {
        const a = texts[i], b = texts[j];
        if (a.e.contains(b.e) || b.e.contains(a.e)) continue;
        const ox = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
        const oy = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
        if (ox > 8 && oy > 8) { defects.push({ kind: 'overlapping-text', section: sec.dataset.section, detail: `<${a.e.tagName.toLowerCase()}> overlaps <${b.e.tagName.toLowerCase()}>` }); reported = true; break; }
      }
    }
  }

  const footer = document.querySelector('footer');
  if (footer) {
    window.scrollTo(0, de.scrollHeight);
    const fr = footer.getBoundingClientRect();
    for (const el of document.querySelectorAll('body *')) {
      if (footer.contains(el) || getComputedStyle(el).position !== 'fixed') continue;
      const r = el.getBoundingClientRect();
      if (r.width * r.height === 0) continue;
      const ox = Math.min(fr.right, r.right) - Math.max(fr.left, r.left);
      const oy = Math.min(fr.bottom, r.bottom) - Math.max(fr.top, r.top);
      if (ox > 0 && oy > 24) { defects.push({ kind: 'covered-footer', section: 'footer', detail: `fixed <${el.tagName.toLowerCase()}> covers ${Math.round(oy)}px of the footer` }); break; }
    }
    window.scrollTo(0, 0);
  }

  for (const fam of (args.fonts || [])) {
    if (!fam) continue;
    const loaded = [...document.fonts].some(f => f.family.replace(/["']/g, '').toLowerCase() === fam.toLowerCase() && f.status === 'loaded');
    if (!loaded) defects.push({ kind: 'font-not-loaded', section: 'head', detail: fam });
  }
  return defects;
}
