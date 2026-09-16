You are building the complete home page of a real website as ONE standalone HTML document.
Write it to [[OUTPUT_PATH]] and report only that path.

==================================================
THE DESIGN (follow exactly)
==================================================

[[DESIGN]]

==================================================
THE CONTENT (facts — never invent, never alter)
==================================================

Language of all text: [[LANGUAGE_NAME]].
Site name: [[SITE_NAME]].

[[CONTENT]]

Facts:
[[FACTS]]

Header must provide: [[HEADER]]
Footer must provide: [[FOOTER]]

Every item marked REQUIRED must appear on the page, verbatim where it is a name, price,
number, address, label or link target. You decide where and how; the design decides the
order. Do not invent prices, addresses, awards, reviews, dish names or phone numbers.

==================================================
IMAGES
==================================================

Available photos (use the URL as src; never render wider than the width limit):
[[IMAGES]]

For any image slot without a photo, use
  <img src="https://placehold.co/1200x800?text=Label" data-image-name="<ascii-key>"
       data-image-prompt="<one-line description of the photo needed>" alt="…">
Never use any other external image URL.

==================================================
DOCUMENT CONTRACT (the importer relies on this)
==================================================

- A complete document: <!DOCTYPE html> … </html>. It must be finished; end with </html>.
- <head>: <title>, <meta name="description">, <script src="https://cdn.tailwindcss.com"></script>,
  one <script> that sets tailwind.config, one <style> block, Google Fonts <link> tags.
  Optional: <script src="https://unpkg.com/lucide@latest"></script>.
- <body>: exactly one <header>, one <main>, one <footer>, then at most one <script> block.
- Inside <main>, only <section> elements, each with an English id in lowercase-hyphen form
  (id="hero", id="chefs-table"). Nothing outside a <section>. Never use <header>, <nav>,
  <footer>, <html>, <head> or <body> anywhere inside <main> — for a quote's attribution, a
  card's caption or a section's top bar use <div>, <p> or <span>.
- Inside <header>, one <nav>; place <div data-slot="language-switcher"></div> where the
  language switcher goes. Mobile menu with Alpine.js (x-data / x-show / @click).
- Internal links: href="#section-id" for anchors; page links (href="/x/") ONLY to these pages: [[PAGES]] — every other navigation item is an anchor to one of your own section ids. No language prefix, the importer adds it. External links, mailto:, tel: as normal.
- Tailwind utility classes and the tailwind.config theme only; arbitrary values (bg-[#…])
  are fine. No <style> outside <head>. No inline style="" except for background-image.
- Do not use {{ or {% anywhere.
- Decorative overlays with no text (gradients, tints) get class pointer-events-none.
- An image repeated for a marquee/loop: the copies get aria-hidden="true" alt="".
- Editable text lives in h1–h6, p, span, a, li, td, th, label, button, blockquote.
- Mobile-first; every section must work at 390px with no horizontal overflow.
- Real text only, no lorem ipsum, no template variables.
- Everything is visible without JavaScript and without scrolling: never hide content behind a
  scroll reveal (no opacity-0 / translate + x-intersect / IntersectionObserver reveals).
  Motion may move things; it never hides them. Counters show their final number in the HTML.
- Header anchor links point to your own English section ids (href="#services"), whatever the
  label's language.

==================================================
AVOID GENERIC AI DESIGN
==================================================

Avoid repeating common AI-generated landing page patterns: text left / image right hero,
floating glass card over hero, endless rounded cards, identical 3-column grids,
gradient-heavy backgrounds, generic luxury black + gold, SaaS-style feature cards,
excessive pills, excessive shadows, identical centered headings, repeating alternating
text/image sections. Use these only when clearly justified by the concept.
Also avoid the three items under this concept's own AVOID.
